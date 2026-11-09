"""Durable lab requests, real subprocess generation and CPU ownership fences."""
# ruff: noqa: F811

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import parse_event_v2
from smartfan_common.lab_config import LabConfig
from smartfan_common.reliability.leases import ResourceLeases
from smartfan_common.reliability.store import DurableStore, LostLease
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_api_integration import api, headers, login  # noqa:F401
from test_reliability_integration import database, reset_disposable_rows  # noqa:F401

from services.jobs.supervisor import Supervisor

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists() or os.name != "posix",
    reason="Requires isolated Linux PG and process locks",
)


def create(api, config=None, key=None):
    client, _, _, _ = api
    token = login(api)
    response = client.post(
        "/api/v1/lab/jobs",
        headers={**headers(token), "Idempotency-Key": key or str(uuid4())},
        json=config or {"days": 0.01, "equipment_count": 3},
    )
    assert response.status_code == 202
    return response.json(), token


def accept(supervisor, job, engines):
    with engines["api"].connect() as conn:
        raw = bytes(
            conn.execute(
                text(
                    "SELECT payload FROM transport.outbox WHERE owner='api' AND event_id=:id"
                ),
                {"id": job["id"]},
            ).scalar_one()
        )
    supervisor.receive(raw, "job.generate", "api", job["id"])


def test_config_and_outbox_are_immutable_idempotent_and_admin_only(api, database):
    client, _, _, _ = api
    admin, engines = database
    key = str(uuid4())
    job, token = create(api, key=key)
    again = client.post(
        "/api/v1/lab/jobs",
        headers={**headers(token), "Idempotency-Key": key},
        json={"days": 0.01, "equipment_count": 3},
    )
    assert again.status_code == 202 and again.json()["id"] == job["id"]
    assert (
        client.post(
            "/api/v1/lab/jobs",
            headers={**headers(token), "Idempotency-Key": key},
            json={"days": 0.02, "equipment_count": 3},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/lab/estimate", headers=headers(token), json={"days": 365}
        ).status_code
        == 422
    )
    for name in ["operador", "visualizador"]:
        other = login(api, name)
        assert (
            client.get("/api/v1/lab/defaults", headers=headers(other)).status_code
            == 403
        )
        assert client.get("/api/v1/jobs", headers=headers(other)).status_code == 403
        assert (
            client.post(
                "/api/v1/lab/jobs",
                headers={**headers(other), "Idempotency-Key": "forbidden"},
                json={},
            ).status_code
            == 403
        )
    with pytest.raises(DBAPIError), engines["api"].begin() as conn:
        conn.execute(
            text("UPDATE app.datasets SET configuration=configuration WHERE id=:id"),
            {"id": job["dataset_id"]},
        )
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.datasets WHERE id=:id"),
                {"id": job["dataset_id"]},
            ).scalar_one()
            == 1
        )
    assert (
        client.get(
            "/api/v1/datasets/" + job["dataset_id"] + "/preview", headers=headers(token)
        ).status_code
        == 409
    )


def test_supervisor_runs_real_child_and_emits_only_label_free_progress(
    api, database, tmp_path, monkeypatch
):
    client, _, _, _ = api
    admin, engines = database
    job, token = create(api)
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    monkeypatch.setattr(
        supervisor, "unload_model", lambda: None
    )  # Isolated child test; real unload is exercised by Compose job.
    try:
        supervisor.recover()
        accept(supervisor, job, engines)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            supervisor.tick()
            if supervisor.work is None:
                result = client.get(
                    "/api/v1/jobs/" + job["id"], headers=headers(token)
                ).json()
                if result["status"] == "completed":
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("Real subprocess did not complete")
        dataset = client.get(
            "/api/v1/datasets/" + job["dataset_id"], headers=headers(token)
        ).json()
        assert (
            dataset["status"] == "completed"
            and dataset["rows"] == LabConfig(days=0.01, equipment_count=3).total
        )
        assert (tmp_path / "datasets" / job["dataset_id"] / "manifest.json").exists()
        assert dataset["manifest"]["content"]["truth_scope"] == "lab_only"
        with admin.connect() as conn:
            messages = conn.execute(
                text(
                    "SELECT payload FROM transport.outbox WHERE owner='jobs-worker' AND routing_key='job.progress'"
                )
            ).all()
            assert messages
            for row in messages:
                event = parse_event_v2(bytes(row[0]))
                assert set(event.conteudo.model_dump()) == {
                    "job_id",
                    "kind",
                    "status",
                    "processed",
                    "total",
                    "reason_code",
                }
            assert (
                conn.execute(
                    text(
                        "SELECT state FROM transport.resource_leases WHERE resource='heavy'"
                    )
                ).scalar_one()
                == "released"
            )
    finally:
        supervisor.close()


def test_queued_cancellation_publishes_no_complete_dataset(api, database, tmp_path):
    client, _, _, _ = api
    _, engines = database
    job, token = create(api)
    response = client.post(
        "/api/v1/jobs/" + job["id"] + "/cancel", headers=headers(token)
    )
    assert response.status_code == 202 and response.json()["cancel_requested"]
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    try:
        supervisor.recover()
        accept(supervisor, job, engines)
        supervisor.tick()
        result = client.get("/api/v1/jobs/" + job["id"], headers=headers(token)).json()
        assert result["status"] == "cancelled" and supervisor.work is None
        assert not (tmp_path / "datasets" / job["dataset_id"]).exists()
        assert (
            client.get(
                "/api/v1/datasets/" + job["dataset_id"] + "/preview",
                headers=headers(token),
            ).status_code
            == 409
        )
    finally:
        supervisor.close()


def test_running_cancellation_confirms_child_stop_before_resource_handover(
    api, database, tmp_path, monkeypatch
):
    client, _, _, _ = api
    _, engines = database
    job, token = create(api, {"days": 0.1, "equipment_count": 100, "block_size": 100})
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    monkeypatch.setattr(supervisor, "unload_model", lambda: None)
    try:
        supervisor.recover()
        accept(supervisor, job, engines)
        supervisor.tick()
        assert supervisor.work is not None
        child = supervisor.work.process
        client.post("/api/v1/jobs/" + job["id"] + "/cancel", headers=headers(token))
        supervisor.tick()
        assert child.poll() is not None and supervisor.work is None
        assert (
            client.get("/api/v1/jobs/" + job["id"], headers=headers(token)).json()[
                "status"
            ]
            == "cancelled"
        )
        assert (
            client.get(
                "/api/v1/datasets/" + job["dataset_id"], headers=headers(token)
            ).json()["manifest"]
            is None
        )
    finally:
        supervisor.close()


def test_expiry_alone_cannot_hand_over_resource_until_process_stop_is_proven(
    api, database, tmp_path, monkeypatch
):
    _, _, _, _ = api
    admin, engines = database
    job, _ = create(api, {"days": 0.1, "equipment_count": 100, "block_size": 100})
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    monkeypatch.setattr(supervisor, "unload_model", lambda: None)
    chat = ResourceLeases(engines["api"], "api")
    try:
        supervisor.recover()
        accept(supervisor, job, engines)
        supervisor.tick()
        work = supervisor.work
        assert work is not None
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE transport.resource_leases SET expires_at=clock_timestamp()-interval '1 second'"
                )
            )
        assert chat.acquire(str(uuid4()), "chat") is None
        work.renew_attempt = time.monotonic() - 6
        with pytest.raises(LostLease):
            supervisor.maintain(work)
        assert work.process.poll() is not None
        assert chat.acquire(str(uuid4()), "chat") is None
        supervisor.recover()
        token = chat.acquire(str(uuid4()), "chat")
        assert token is not None
        assert chat.release_after_confirmed_stop(token)  # No chat process was started.
    finally:
        supervisor.close()


def test_inherited_lock_blocks_new_supervisor_until_prior_child_stopped(
    database, tmp_path
):
    _, engines = database
    store = DurableStore(engines["jobs-worker"], "jobs-worker")
    first = Supervisor(store, tmp_path)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time;time.sleep(30)"],
        pass_fds=(first.lock.fileno(),),
    )
    try:
        first._stop.set()
        first._watchdog.join(timeout=2)
        first.lock.close()  # Simulate parent loss while child holds inherited description.
        with pytest.raises(RuntimeError):
            Supervisor(store, tmp_path)
        child.terminate()
        child.wait(timeout=2)
        second = Supervisor(store, tmp_path)
        second.close()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=2)
        first.close()


def test_child_exits_when_parent_heartbeat_is_older_than_renewal_budget(tmp_path):
    (tmp_path / "config.json").write_text(
        LabConfig(days=0.01, equipment_count=3).model_dump_json()
    )
    (tmp_path / "heartbeat.json").write_text(
        json.dumps({"renewed_monotonic": time.monotonic() - 20})
    )
    child = subprocess.Popen(
        [sys.executable, "-m", "services.jobs.generate", str(tmp_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert child.wait(timeout=5) == 3
    assert not (tmp_path / "manifest.json").exists()
