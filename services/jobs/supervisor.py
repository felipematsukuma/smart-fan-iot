"""Exclusive, inherited process lock plus SQL fencing for heavy laboratory work."""

import hashlib
import importlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from smartfan_common.contracts_v2 import (
    JobProgressV2,
    JobRequestedV2,
    ModelAvailableV2,
    parse_event_v2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.lab_config import LabConfig
from smartfan_common.local_llm import MODEL
from smartfan_common.reliability.amqp import authenticated_publisher
from smartfan_common.reliability.leases import ResourceLeases, ResourceToken
from smartfan_common.reliability.store import (
    Delivery,
    DurableStore,
    LostLease,
    Outbound,
)
from smartfan_common.routing_v2 import routing_key_v2
from smartfan_common.training_config import TRAINING_FAILURE_REASONS, TrainingTask
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .generate import canonical, digest_file

fcntl: Any = importlib.import_module("fcntl") if os.name == "posix" else None


@dataclass
class Work:
    delivery: Delivery
    job: dict
    config: LabConfig | TrainingTask
    token: ResourceToken
    path: Path
    process: subprocess.Popen
    renewed: float
    renew_attempt: float
    processed: int = 0
    forced_reason: str | None = None


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


class Supervisor:
    def __init__(self, store: DurableStore, root: Path, quota: int = 4 * 1024**3):
        if store.owner != "jobs-worker" or fcntl is None:
            raise RuntimeError("Laboratory requires the Linux jobs-worker container")
        self.store = store
        self.root = root
        self.quota = quota
        self.instance = str(uuid4())
        self.leases = ResourceLeases(store.engine, "jobs-worker")
        root.mkdir(parents=True, exist_ok=True)
        self.lock = (root / ".supervisor.lock").open("a+b")
        try:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise RuntimeError(
                "Previous supervisor/child still owns artifact lock"
            ) from None
        self.work: Work | None = None
        self._mutex = threading.RLock()
        self._stop = threading.Event()
        self._watchdog = threading.Thread(
            target=self._watch, daemon=True, name="heavy-work-watchdog"
        )
        self._watchdog.start()

    def _watch(self) -> None:
        while not self._stop.wait(0.25):
            with self._mutex:
                work = self.work
                if (
                    work
                    and work.process.poll() is None
                    and time.monotonic() - work.renewed >= 18
                ):
                    work.forced_reason = "resource_renewal_lost"
                    stop_process(work.process)

    def recover(self) -> None:
        if self.work is not None:
            stop_process(self.work.process)
        # Acquiring the SAME never-unlinked inode proves every prior parent/child
        # holding its inherited FD stopped, even across PID namespaces/containers.
        with self.store.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT holder_service,owner_instance_id,generation,state FROM transport.resource_leases WHERE resource='heavy'"
                )
            ).first()
        if row and row[0] == "jobs-worker" and row[3] != "released":
            token = ResourceToken("heavy", str(row[1]), "jobs-worker", row[2])
            if not self.leases.release_after_confirmed_stop(token):
                raise LostLease("Cannot reconcile stopped child")
        with self.store.transaction() as conn:
            rows = conn.execute(
                text(
                    "UPDATE app.jobs SET status='queued',worker_instance=NULL,resource_generation=NULL,reason_code='worker_restarted',updated_at=clock_timestamp() WHERE status='running' RETURNING id,dataset_id,kind"
                )
            ).all()
            for row in rows:
                conn.execute(
                    text(
                        "UPDATE app.datasets SET status='queued' WHERE id=:id AND status='running' AND :kind='generate'"
                    ),
                    {"id": row[1], "kind": row[2]},
                )
                conn.execute(
                    text(
                        "UPDATE app.models SET status='queued' WHERE job_id=:id AND status='running'"
                    ),
                    {"id": row[0]},
                )
                conn.execute(
                    text(
                        "UPDATE transport.inbox SET state='pending',generation=generation+1,leased_until=NULL,available_at=clock_timestamp(),dependency_failure=true WHERE owner='jobs-worker' AND event_id=:id AND state='working'"
                    ),
                    {"id": row[0]},
                )
            conn.execute(
                text(
                    "UPDATE transport.inbox SET state='pending',generation=generation+1,leased_until=NULL,available_at=clock_timestamp(),dependency_failure=true WHERE owner='jobs-worker' AND state='working' AND event_id IN (SELECT id FROM app.jobs WHERE status='queued')"
                )
            )
        with self._mutex:
            self.work = None

    def receive(
        self, raw: bytes, route: str, user_id: str | None, message_id: str | None
    ) -> None:
        try:
            event = parse_event_v2(raw)
            if (
                not isinstance(event, JobRequestedV2)
                or event.tipo not in ("job.generate", "job.train")
                or not authenticated_publisher(event, user_id)
                or event.id != message_id
                or route != event.tipo
                or event.id != event.conteudo.job_id
            ):
                raise ValueError("Invalid generation request")
            with self.store.transaction() as conn:
                row = conn.execute(
                    text(
                        "SELECT dataset_id,event_sha256,kind FROM app.jobs WHERE id=:id"
                    ),
                    {"id": event.id},
                ).first()
                if (
                    row is None
                    or str(row[0]) != event.conteudo.dataset_id
                    or row[1] != payload_sha256(raw)
                    or event.conteudo.config_version != 1
                    or row[2] != event.tipo.split(".")[1]
                ):
                    raise ValueError("Request differs from committed configuration")
                self.store.receive(event.id, raw, route, connection=conn)
        except ValueError:
            self.store.quarantine(raw, route[:256], "invalid_job_request")

    def emit(
        self, conn, job: dict, status: str, processed: int, reason: str | None = None
    ) -> None:
        event = JobProgressV2.model_validate(
            {
                "id": str(uuid4()),
                "schema_version": "2.1",
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "tipo": "job.progress",
                "dispositivo": None,
                "correlation_id": str(job["correlation_id"]),
                "metadata": {"producer": "jobs-worker", "causation_id": str(job["id"])},
                "conteudo": {
                    "job_id": str(job["id"]),
                    "kind": job["kind"],
                    "status": status,
                    "processed": processed,
                    "total": job["total"],
                    "reason_code": reason,
                },
            }
        )
        exchange, route = routing_key_v2(event)
        self.store.enqueue(
            Outbound(event.id, serialize_event_v2(event), exchange, route),
            connection=conn,
        )

    def guard_sql(self, conn, work: Work) -> None:
        owned = conn.execute(
            text(
                "SELECT 1 FROM transport.resource_leases WHERE resource='heavy' AND holder_service='jobs-worker' AND owner_instance_id=:owner AND generation=:generation AND state='active' AND expires_at>clock_timestamp() FOR UPDATE"
            ),
            {"owner": self.instance, "generation": work.token.generation},
        ).first()
        if owned is None:
            raise LostLease("Heavy resource lease expired")
        self.store._owned(conn, work.delivery)

    @staticmethod
    def heartbeat(path: Path) -> None:
        temporary = path / "heartbeat.tmp"
        temporary.write_bytes(canonical({"renewed_monotonic": time.monotonic()}))
        os.replace(temporary, path / "heartbeat.json")

    def unload_model(self) -> None:
        import urllib.request

        request = urllib.request.Request(
            "http://ollama:11434/api/generate",
            data=json.dumps(
                {"model": MODEL, "keep_alive": 0, "stream": False}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            response.read(65536)
        with urllib.request.urlopen(
            "http://ollama:11434/api/ps", timeout=3
        ) as response:
            loaded = json.loads(response.read(65536)).get("models", [])
        if loaded:
            raise RuntimeError("LLM unload not confirmed")

    def start(self) -> None:
        delivery = self.store.claim("inbox")
        if delivery is None:
            return
        event = parse_event_v2(delivery.payload)
        if not isinstance(event, JobRequestedV2):
            self.store.retry(delivery, "invalid_job_request", permanent=True)
            return
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT j.*,CASE WHEN j.kind='generate' THEN d.configuration ELSE t.configuration END AS configuration,CASE WHEN j.kind='generate' THEN d.configuration_sha256 ELSE t.configuration_sha256 END AS configuration_sha256 FROM app.jobs j JOIN app.datasets d ON d.id=j.dataset_id LEFT JOIN app.training_requests t ON t.job_id=j.id WHERE j.id=:id"
                    ),
                    {"id": event.conteudo.job_id},
                )
                .mappings()
                .one()
            )
        job = dict(row)
        if job["status"] in ("completed", "failed", "cancelled"):
            self.store.finish(delivery)
            return
        if job["cancel_requested"]:
            self.terminal(
                delivery, job, "cancelled", "cancel_requested", job["processed"]
            )
            return
        try:
            config: LabConfig | TrainingTask = (
                LabConfig.model_validate(job["configuration"])
                if job["kind"] == "generate"
                else TrainingTask.model_validate(job["configuration"])
            )
        except ValueError:
            self.terminal(delivery, job, "failed", "configuration_changed", 0)
            return
        if (
            hashlib.sha256(canonical(config.model_dump())).hexdigest()
            != job["configuration_sha256"]
        ):
            self.terminal(delivery, job, "failed", "configuration_changed", 0)
            return
        if job["attempts"] >= 3:
            self.terminal(delivery, job, "failed", "job_attempts_exhausted", 0)
            return
        token = self.leases.acquire(self.instance, job["kind"])
        if token is None:
            self.store.retry(delivery, "resource_busy", dependency_failure=True)
            return
        process = None
        try:
            used = sum(
                item.stat().st_size
                for item in self.root.rglob("*")
                if item.is_file() and not item.is_symlink()
            )
            if (
                used + config.estimated_bytes > self.quota
                or shutil.disk_usage(self.root).free
                < config.estimated_bytes + 512 * 1024**2
            ):
                raise RuntimeError("artifact_quota")
            self.unload_model()
            if not self.leases.valid(token):
                raise LostLease("Resource lease lost before spawn")
            path = self.root / "work" / f"{job['id']}-{uuid4()}"
            path.mkdir(parents=True, exist_ok=False)
            (path / "config.json").write_bytes(canonical(config.model_dump()))
            self.heartbeat(path)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "services.jobs.generate"
                    if job["kind"] == "generate"
                    else "services.jobs.train",
                    str(path),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                pass_fds=(self.lock.fileno(),),
                env={
                    **os.environ,
                    "OPENBLAS_NUM_THREADS": "1",
                    "OMP_NUM_THREADS": "1",
                    "MKL_NUM_THREADS": "1",
                },
            )
            now = time.monotonic()
            work = Work(delivery, job, config, token, path, process, now, now)
            with self._mutex:
                self.work = work
            with self.store.transaction() as conn:
                self.guard_sql(conn, work)
                conn.execute(
                    text(
                        "UPDATE app.jobs SET status='running',processed=0,worker_instance=:worker,resource_generation=:generation,attempts=attempts+1,reason_code=NULL,updated_at=clock_timestamp() WHERE id=:id"
                    ),
                    {
                        "id": job["id"],
                        "worker": self.instance,
                        "generation": token.generation,
                    },
                )
                conn.execute(
                    text(
                        "UPDATE app.datasets SET status='running' WHERE id=:id AND :kind='generate'"
                    ),
                    {"id": job["dataset_id"], "kind": job["kind"]},
                )
                conn.execute(
                    text("UPDATE app.models SET status='running' WHERE job_id=:id"),
                    {"id": job["id"]},
                )
                self.emit(conn, job, "running", 0)
        except (OSError, RuntimeError) as error:
            if process is not None:
                stop_process(process)
            if self.work is None:
                if str(error) == "artifact_quota":
                    self.terminal(delivery, job, "failed", "artifact_quota", 0)
                else:
                    self.store.retry(
                        delivery,
                        "resource_preparation_unavailable",
                        dependency_failure=True,
                    )
                self.leases.release_after_confirmed_stop(token)
                return
            self.work.forced_reason = "worker_interrupted"
            raise
        except BaseException:
            if process is not None:
                stop_process(process)
            if self.work is not None:
                self.work.forced_reason = "worker_interrupted"
            else:
                self.leases.release_after_confirmed_stop(token)
            raise

    def maintain(self, work: Work) -> None:
        now = time.monotonic()
        if now - work.renew_attempt >= 5:
            work.renew_attempt = now
            if not self.leases.renew(work.token) or not self.store.renew(work.delivery):
                work.forced_reason = "resource_renewal_lost"
                stop_process(work.process)
                raise LostLease("Renewal rejected")
            work.renewed = time.monotonic()
            self.heartbeat(work.path)

    def terminal(
        self,
        delivery: Delivery,
        job: dict,
        status: str,
        reason: str | None,
        processed: int,
        work: Work | None = None,
        manifest: dict | None = None,
    ) -> None:
        def effects(conn):
            if work is not None and status == "completed":
                self.guard_sql(conn, work)
            row = conn.execute(
                text("SELECT cancel_requested FROM app.jobs WHERE id=:id FOR UPDATE"),
                {"id": job["id"]},
            ).first()
            if row is None:
                raise LostLease("Job disappeared")
            final = "cancelled" if row[0] and status == "completed" else status
            conn.execute(
                text(
                    "UPDATE app.jobs SET status=:status,processed=:processed,reason_code=:reason,updated_at=clock_timestamp() WHERE id=:id"
                ),
                {
                    "id": job["id"],
                    "status": final,
                    "processed": processed,
                    "reason": reason,
                },
            )
            conn.execute(
                text(
                    "UPDATE app.datasets SET status=:status,sha256=:hash,manifest=CAST(:manifest AS jsonb),completed_at=CASE WHEN :status='completed' THEN clock_timestamp() ELSE NULL END WHERE id=:id AND :kind='generate'"
                ),
                {
                    "id": job["dataset_id"],
                    "kind": job["kind"],
                    "status": final,
                    "hash": manifest["sha256"]
                    if manifest and final == "completed"
                    else None,
                    "manifest": json.dumps(manifest)
                    if manifest and final == "completed"
                    else None,
                },
            )
            if job["kind"] == "train":
                complete = manifest is not None and final == "completed"
                conn.execute(
                    text(
                        "UPDATE app.models SET status=:status,artifact_sha256=:hash,manifest=CAST(:manifest AS jsonb),report=CAST(:report AS jsonb) WHERE job_id=:id"
                    ),
                    {
                        "id": job["id"],
                        "status": final,
                        "hash": manifest["sha256"]
                        if manifest is not None and complete
                        else None,
                        "manifest": json.dumps(manifest) if complete else None,
                        "report": json.dumps(manifest["content"]["report"])
                        if manifest is not None and complete
                        else None,
                    },
                )
            self.emit(conn, job, final, processed, reason)
            conn.execute(
                text(
                    "INSERT INTO app.audit(id,actor_user_id,action,entity_type,entity_id,correlation_id,details,outcome) VALUES(:audit,NULL,:action,'job',:id,:correlation,CAST(:details AS jsonb),:outcome)"
                ),
                {
                    "audit": str(uuid4()),
                    "action": "job." + final,
                    "id": str(job["id"]),
                    "correlation": str(job["correlation_id"]),
                    "details": json.dumps({"processed": processed, "reason": reason}),
                    "outcome": "success" if final == "completed" else final,
                },
            )

        self.store.finish(delivery, effects=effects)

    def verify(self, path: Path, config: LabConfig | TrainingTask, work: Work) -> dict:
        raw = (path / "manifest.json").read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Invalid manifest size")
        manifest = json.loads(raw)
        content = manifest["content"]
        if isinstance(config, TrainingTask):
            if (
                content["task"] != config.model_dump()
                or content["model_version"] != config.model_version
                or manifest["sha256"] != hashlib.sha256(canonical(content)).hexdigest()
            ):
                raise ValueError("Training manifest differs")
            expected = {
                "bundle.joblib",
                "report.json",
                "model-card.md",
                "benchmark/manifest.json",
            } | {
                "benchmark/" + name
                for name in (
                    "readings.npy",
                    "timestamp_seconds.npy",
                    "equipment_index.npy",
                    "compressor_on.npy",
                    "condenser_fan_on.npy",
                    "health_score.npy",
                    "rul_calendar_hours.npy",
                    "censored.npy",
                    "outliers.npy",
                )
            }
            if set(content["files"]) != expected:
                raise ValueError("Unexpected model artifact files")
            for filename, digest in content["files"].items():

                def check_training():
                    self.maintain(work)
                    return work.forced_reason is not None

                if digest_file(path / filename, check_training) != digest:
                    raise ValueError("Model artifact changed")
            return manifest
        if (
            content["rows"] != config.total
            or content["configuration"] != config.model_dump(exclude={"block_size"})
            or manifest["sha256"] != hashlib.sha256(canonical(content)).hexdigest()
        ):
            raise ValueError("Manifest does not match configuration")
        expected = {
            "readings.npy",
            "timestamp_seconds.npy",
            "equipment_index.npy",
            "compressor_on.npy",
            "condenser_fan_on.npy",
            "health_score.npy",
            "rul_calendar_hours.npy",
            "censored.npy",
            "outliers.npy",
        }
        if set(content["files"]) != expected:
            raise ValueError("Unexpected artifact files")

        def check():
            self.maintain(work)
            return work.forced_reason is not None

        for filename, digest in content["files"].items():
            if digest_file(path / filename, check) != digest:
                raise ValueError("Artifact hash differs")
        return manifest

    def enqueue_activation(self) -> None:
        with self.store.transaction() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT n.*,m.artifact_sha256,m.report FROM app.activation_notifications n JOIN app.models m ON m.version=n.version WHERE n.state='pending' AND m.approved AND m.status='completed' ORDER BY n.revision LIMIT 1 FOR UPDATE OF n SKIP LOCKED"
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return
            selected = conn.execute(
                text(
                    "SELECT desired_version,activation_revision FROM app.model_selection WHERE singleton"
                )
            ).one()
            if selected[0] != row["version"] or selected[1] != row["revision"]:
                conn.execute(
                    text(
                        "UPDATE app.activation_notifications SET state='superseded' WHERE id=:id"
                    ),
                    {"id": row["id"]},
                )
                return
            event = ModelAvailableV2.model_validate(
                {
                    "id": str(row["id"]),
                    "schema_version": "2.1",
                    "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "tipo": "model.available",
                    "dispositivo": None,
                    "correlation_id": str(row["correlation_id"]),
                    "metadata": {"producer": "jobs-worker", "causation_id": None},
                    "conteudo": {
                        "model_version": row["version"],
                        "feature_version": row["report"]["feature_version"],
                        "dataset_id": row["report"]["dataset_id"],
                        "sha256": row["artifact_sha256"],
                    },
                }
            )
            exchange, route = routing_key_v2(event)
            self.store.enqueue(
                Outbound(event.id, serialize_event_v2(event), exchange, route),
                connection=conn,
            )
            conn.execute(
                text(
                    "UPDATE app.activation_notifications SET state='enqueued' WHERE id=:id"
                ),
                {"id": row["id"]},
            )

    def tick(self) -> None:
        work = self.work
        if work is None:
            self.start()
            return
        self.maintain(work)
        with self.store.engine.connect() as conn:
            cancel = conn.execute(
                text("SELECT cancel_requested FROM app.jobs WHERE id=:id"),
                {"id": work.job["id"]},
            ).scalar_one()
        if cancel:
            work.forced_reason = "cancel_requested"
            (work.path / "cancel.requested").touch()
            stop_process(work.process)
        if work.process.poll() is None:
            try:
                raw = (work.path / "progress.json").read_bytes()
                if len(raw) > 1024:
                    raise ValueError("Invalid progress")
                value = json.loads(raw)
                processed = value["processed"]
                if (
                    type(processed) is not int
                    or not work.processed <= processed <= work.config.total
                ):
                    raise ValueError("Invalid progress")
                if processed != work.processed:
                    with self.store.transaction() as conn:
                        self.guard_sql(conn, work)
                        conn.execute(
                            text(
                                "UPDATE app.jobs SET processed=:processed,updated_at=clock_timestamp() WHERE id=:id"
                            ),
                            {"id": work.job["id"], "processed": processed},
                        )
                        self.emit(conn, work.job, "running", processed)
                    work.processed = processed
            except FileNotFoundError:
                pass
            return
        status = "cancelled" if cancel or work.process.returncode == 2 else "failed"
        reason: str | None = work.forced_reason or "child_failed"
        if (
            reason == "child_failed"
            and work.job["kind"] == "train"
            and (work.path / "error.json").exists()
        ):
            raw = (work.path / "error.json").read_bytes()
            if (
                len(raw) <= 1024
                and json.loads(raw).get("reason") in TRAINING_FAILURE_REASONS
            ):
                reason = json.loads(raw)["reason"]
        manifest = None
        if work.process.returncode == 0 and not cancel and work.forced_reason is None:
            manifest = self.verify(work.path, work.config, work)
            destination = (
                self.root / "models" / work.config.model_version
                if isinstance(work.config, TrainingTask)
                else self.root / "datasets" / str(work.job["dataset_id"])
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                existing = self.verify(destination, work.config, work)
                if existing["sha256"] != manifest["sha256"]:
                    raise ValueError("Existing dataset differs")
            else:
                os.replace(work.path, destination)
                work.path = destination
            status = "completed"
            reason = None
            work.processed = work.config.total
        self.terminal(
            work.delivery, work.job, status, reason, work.processed, work, manifest
        )
        if not self.leases.release_after_confirmed_stop(work.token):
            raise LostLease("Cannot release stopped child")
        with self._mutex:
            self.work = None

    def close(self) -> None:
        self._stop.set()
        self._watchdog.join(timeout=2)
        with self._mutex:
            if self.work is not None:
                stop_process(self.work.process)
                # Failure to reach PG leaves recovery fenced; next lock owner proves stop.
                try:
                    self.leases.release_after_confirmed_stop(self.work.token)
                except SQLAlchemyError:
                    logging.getLogger("jobs-worker").warning(
                        "recovery_deferred", extra={"event": "recovery_deferred"}
                    )
        self.lock.close()
