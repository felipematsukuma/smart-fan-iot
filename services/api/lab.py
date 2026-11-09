"""Laboratory requests commit immutable config and queued event in one transaction."""

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from smartfan_common.contracts_v2 import (
    JobRequestedV2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.lab_config import LabConfig
from smartfan_common.reliability.store import DurableStore, Outbound
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text

from .auth import Principal, audit
from .errors import Problem

JOB_COLUMNS = "id,dataset_id,kind,status,processed,total,cancel_requested,reason_code,attempts,created_at,updated_at"


def preview(path: Path, dataset: dict, limit: int) -> dict:
    import numpy as np

    try:
        readings = np.load(path / "readings.npy", mmap_mode="r", allow_pickle=False)
        health = np.load(path / "health_score.npy", mmap_mode="r", allow_pickle=False)
        rul = np.load(
            path / "rul_calendar_hours.npy", mmap_mode="r", allow_pickle=False
        )
        groups = np.load(
            path / "equipment_index.npy", mmap_mode="r", allow_pickle=False
        )
        stamps = np.load(
            path / "timestamp_seconds.npy", mmap_mode="r", allow_pickle=False
        )
        channels = dataset["manifest"]["content"]["channels"]
        if readings.shape != (
            dataset["rows"],
            len(channels),
        ) or readings.dtype != np.dtype("<f4"):
            raise ValueError("Invalid artifact shape")
        indices = np.linspace(
            0, dataset["rows"] - 1, num=min(limit, dataset["rows"]), dtype=int
        )

        def number(value):
            return float(value) if math.isfinite(value) else None

        rows = [
            {
                "equipment_index": int(groups[index]),
                "timestamp_seconds": float(stamps[index]),
                "readings": [number(value) for value in readings[index]],
                "truth_health_score": number(health[index]),
                "truth_rul_calendar_hours": number(rul[index]),
            }
            for index in indices
        ]
        return {
            "scope": "lab_only",
            "channels": channels,
            "rows": rows,
            "note": "Verdade sintética exclusiva do laboratório; não transmitida por MQTT/WebSocket.",
        }
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise Problem(
            503,
            "artifact_unavailable",
            "Artefato temporariamente indisponível ou inválido.",
        ) from None


class Lab:
    def __init__(self, store: DurableStore):
        self.store = store

    def create(
        self, config: LabConfig, principal: Principal, key: str, correlation: str
    ) -> dict:
        raw_config = json.dumps(
            config.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        digest = hashlib.sha256(raw_config.encode()).hexdigest()
        with self.store.transaction() as conn:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": "lab-request:" + principal.id + ":" + key},
            )
            previous = conn.execute(
                text(
                    "SELECT id,request_hash FROM app.jobs WHERE actor_user_id=:actor AND idempotency_key=:key"
                ),
                {"actor": principal.id, "key": key},
            ).first()
            if previous:
                if previous[1] != digest:
                    raise Problem(
                        409,
                        "idempotency_conflict",
                        "Chave já utilizada com outra configuração.",
                    )
                job_id = str(previous[0])
            else:
                # Bound queued jobs before creating any dataset or outbox payload.
                conn.execute(text("SELECT pg_advisory_xact_lock(734121)"))
                if (
                    conn.execute(
                        text(
                            "SELECT count(*) FROM app.jobs WHERE status IN ('queued','running')"
                        )
                    ).scalar_one()
                    >= 10
                ):
                    raise Problem(
                        409, "job_queue_full", "Limite de dez jobs pendentes atingido."
                    )
                job_id = str(uuid4())
                dataset_id = str(uuid4())
                now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                event = JobRequestedV2.model_validate(
                    {
                        "id": job_id,
                        "schema_version": "2.1",
                        "timestamp": now,
                        "tipo": "job.generate",
                        "dispositivo": None,
                        "correlation_id": correlation,
                        "metadata": {"producer": "api", "causation_id": None},
                        "conteudo": {
                            "job_id": job_id,
                            "dataset_id": dataset_id,
                            "config_version": 1,
                        },
                    }
                )
                raw = serialize_event_v2(event)
                conn.execute(
                    text(
                        "INSERT INTO app.datasets(id,configuration,configuration_sha256,rows,status,actor_user_id) VALUES(:id,CAST(:config AS jsonb),:hash,:rows,'queued',:actor)"
                    ),
                    {
                        "id": dataset_id,
                        "config": raw_config,
                        "hash": digest,
                        "rows": config.total,
                        "actor": principal.id,
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO app.jobs(id,dataset_id,kind,actor_user_id,idempotency_key,request_hash,event_sha256,correlation_id,total) VALUES(:id,:dataset,'generate',:actor,:key,:hash,:event_hash,:correlation,:total)"
                    ),
                    {
                        "id": job_id,
                        "dataset": dataset_id,
                        "actor": principal.id,
                        "key": key,
                        "hash": digest,
                        "event_hash": payload_sha256(raw),
                        "correlation": correlation,
                        "total": config.total,
                    },
                )
                exchange, route = routing_key_v2(event)
                self.store.enqueue(
                    Outbound(event.id, raw, exchange, route), connection=conn
                )
                audit(
                    conn,
                    principal.id,
                    "dataset.requested",
                    "dataset",
                    dataset_id,
                    correlation,
                    {
                        "job_id": job_id,
                        "rows": config.total,
                        "configuration_sha256": digest,
                    },
                )
        return self.job(UUID(job_id))

    def job(self, identity: UUID) -> dict:
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    text("SELECT " + JOB_COLUMNS + " FROM app.jobs WHERE id=:id"),
                    {"id": str(identity)},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Problem(404, "job_not_found", "Job não encontrado.")
        return dict(row)

    def jobs(self, before: UUID | None, limit: int) -> dict:
        with self.store.engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT "
                        + JOB_COLUMNS
                        + " FROM app.jobs WHERE (:before IS NULL OR (created_at,id)<(SELECT created_at,id FROM app.jobs WHERE id=CAST(:before AS uuid))) ORDER BY created_at DESC,id DESC LIMIT :limit"
                    ),
                    {"before": str(before) if before else None, "limit": limit + 1},
                )
                .mappings()
                .all()
            )
        return {
            "items": [dict(row) for row in rows[:limit]],
            "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
        }

    def cancel(self, identity: UUID, principal: Principal, correlation: str) -> dict:
        with self.store.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT status,cancel_requested FROM app.jobs WHERE id=:id FOR UPDATE"
                ),
                {"id": str(identity)},
            ).first()
            if row is None:
                raise Problem(404, "job_not_found", "Job não encontrado.")
            if row[0] in ("completed", "failed", "cancelled"):
                return self.job(identity)
            conn.execute(
                text("UPDATE app.jobs SET cancel_requested=true WHERE id=:id"),
                {"id": str(identity)},
            )
            if not row[1]:
                audit(
                    conn,
                    principal.id,
                    "job.cancel_requested",
                    "job",
                    str(identity),
                    correlation,
                )
        return self.job(identity)

    def dataset(self, identity: UUID) -> dict:
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT id,configuration,rows,status,sha256,manifest,created_at,completed_at FROM app.datasets WHERE id=:id"
                    ),
                    {"id": str(identity)},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Problem(404, "dataset_not_found", "Dataset não encontrado.")
        return dict(row)
