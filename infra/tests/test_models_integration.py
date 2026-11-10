"""Registry permissions and promotion fences; metrics fixtures do not certify ML quality."""
# ruff: noqa: F811

import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import ModelAvailableV2, parse_event_v2
from smartfan_common.features import FEATURE_VERSION
from smartfan_common.lab_config import LabConfig
from smartfan_common.reliability.store import DurableStore
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_api_integration import api, headers, login  # noqa:F401
from test_reliability_integration import database, reset_disposable_rows  # noqa:F401

from services.jobs.generate import canonical, generate
from services.jobs.supervisor import Supervisor

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated PG and Linux subprocesses",
)


@pytest.fixture(autouse=True)
def reset_models(database):
    admin, _ = database
    with admin.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE app.model_activations,app.inference_results,app.drift_states,app.predictive_states,app.alerts,app.activation_notifications,app.model_selection,app.models,app.training_requests,app.jobs,app.datasets"
            )
        )
        conn.execute(text("INSERT INTO app.model_selection(singleton) VALUES(true)"))


def source_dataset(database, root=None):
    admin, _ = database
    identity = str(uuid4())
    config = LabConfig(days=0.1, equipment_count=30)
    manifest = (
        generate(config, root / "datasets" / identity)
        if root
        else {"sha256": "a" * 64, "content": {}}
    )
    import hashlib

    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app.datasets(id,configuration,configuration_sha256,rows,status,sha256,manifest,actor_user_id) VALUES(:id,CAST(:config AS jsonb),:config_hash,:rows,'completed',:hash,CAST(:manifest AS jsonb),:actor)"
            ),
            {
                "id": identity,
                "config": canonical(config.model_dump()).decode(),
                "config_hash": hashlib.sha256(
                    canonical(config.model_dump())
                ).hexdigest(),
                "rows": config.total,
                "hash": manifest["sha256"],
                "manifest": json.dumps(manifest),
                "actor": str(uuid4()),
            },
        )
    return identity


def request_training(api, dataset, key=None):
    client, _, _, _ = api
    token = login(api)
    response = client.post(
        "/api/v1/training/jobs",
        headers={**headers(token), "Idempotency-Key": key or str(uuid4())},
        json={
            "dataset_id": dataset,
            "max_feature_rows": 6000,
            "benchmark_feature_rows": 3000,
            "importance_rows": 100,
        },
    )
    assert response.status_code == 202
    models = client.get("/api/v1/models", headers=headers(token)).json()["items"]
    model = next(item for item in models if item["job_id"] == response.json()["id"])
    return model, token


def fixture_metrics(database, version, dataset, good=True):
    _, engines = database
    metrics = {
        "mae": 1 if good else 3,
        "rmse": 1 if good else 3,
        "r2": 0.8,
        "count": 200,
        "reason": None,
    }
    baseline = {"mae": 2, "rmse": 2, "r2": 0.2, "count": 200, "reason": None}
    report = {
        "dataset_id": dataset,
        "feature_version": FEATURE_VERSION,
        "active_reference_version": None,
        "targets": {
            name: {
                "test": metrics,
                "benchmark": metrics,
                "benchmark_baseline": baseline,
                "benchmark_active": None,
                "per_mode": {},
            }
            for name in ["health_score", "rul_calendar_hours"]
        },
    }
    with engines["jobs-worker"].begin() as conn:
        conn.execute(
            text(
                "UPDATE app.models SET status='completed',artifact_sha256=:hash,report=CAST(:report AS jsonb),manifest=CAST(:manifest AS jsonb) WHERE version=:version"
            ),
            {
                "version": version,
                "hash": "c" * 64,
                "report": json.dumps(report),
                "manifest": json.dumps(
                    {"content": {"files": {"bundle.joblib": "b" * 64}}}
                ),
            },
        )


def test_train_request_is_idempotent_and_only_admin_can_read_or_change_models(
    api, database
):
    client, _, _, _ = api
    _, engines = database
    dataset = source_dataset(database)
    key = str(uuid4())
    model, token = request_training(api, dataset, key)
    repeated = client.post(
        "/api/v1/training/jobs",
        headers={**headers(token), "Idempotency-Key": key},
        json={
            "dataset_id": dataset,
            "max_feature_rows": 6000,
            "benchmark_feature_rows": 3000,
            "importance_rows": 100,
        },
    )
    assert repeated.json()["id"] == model["job_id"]
    for username in ["operador", "visualizador"]:
        other = login(api, username)
        assert client.get("/api/v1/models", headers=headers(other)).status_code == 403
        assert (
            client.post(
                "/api/v1/training/jobs",
                headers={**headers(other), "Idempotency-Key": str(uuid4())},
                json={"dataset_id": dataset},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/models/" + model["version"] + "/promote",
                headers=headers(other),
                json={"request_id": str(uuid4()), "expected_revision": 0},
            ).status_code
            == 403
        )
    with pytest.raises(DBAPIError), engines["api"].begin() as conn:
        conn.execute(
            text("UPDATE app.models SET report=report WHERE version=:version"),
            {"version": model["version"]},
        )
    with pytest.raises(DBAPIError), engines["jobs-worker"].begin() as conn:
        conn.execute(
            text("UPDATE app.models SET approved=true WHERE version=:version"),
            {"version": model["version"]},
        )
    with pytest.raises(DBAPIError), engines["api"].begin() as conn:
        conn.execute(
            text("UPDATE app.model_selection SET active_version=:version"),
            {"version": model["version"]},
        )


def test_underperforming_candidate_never_changes_desired_selection(api, database):
    client, _, _, _ = api
    dataset = source_dataset(database)
    model, token = request_training(api, dataset)
    fixture_metrics(database, model["version"], dataset, good=False)
    response = client.post(
        "/api/v1/models/" + model["version"] + "/promote",
        headers=headers(token),
        json={"request_id": str(uuid4()), "expected_revision": 0},
    )
    assert response.status_code == 409
    selection = client.get("/api/v1/models", headers=headers(token)).json()["selection"]
    assert (
        selection["desired_version"] is None
        and selection["active_version"] is None
        and selection["activation_revision"] == 0
    )


def test_promotion_is_atomic_idempotent_and_only_worker_notifies_without_fake_activation(
    api, database, tmp_path
):
    client, _, _, _ = api
    admin, engines = database
    dataset = source_dataset(database)
    model, token = request_training(api, dataset)
    fixture_metrics(database, model["version"], dataset)
    body = {"request_id": str(uuid4()), "expected_revision": 0}
    path = "/api/v1/models/" + model["version"] + "/promote"
    first = client.post(path, headers=headers(token), json=body)
    assert first.status_code == 202 and first.json()["active_version"] is None
    assert (
        client.post(path, headers=headers(token), json=body).json()["status"]
        == "already_requested"
    )
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    try:
        supervisor.enqueue_activation()
        supervisor.enqueue_activation()
    finally:
        supervisor.close()
    with admin.connect() as conn:
        events = conn.execute(
            text(
                "SELECT payload FROM transport.outbox WHERE owner='jobs-worker' AND routing_key='model.available'"
            )
        ).all()
        assert (
            len(events) == 1
            and parse_event_v2(bytes(events[0][0])).metadata.producer == "jobs-worker"
        )
        selected = conn.execute(
            text(
                "SELECT desired_version,active_version,activation_revision FROM app.model_selection"
            )
        ).one()
        assert (
            selected[0] == model["version"] and selected[1] is None and selected[2] == 1
        )


def test_late_notification_is_superseded_and_cannot_change_current_selection(
    api, database, tmp_path
):
    client, _, _, _ = api
    admin, engines = database
    dataset = source_dataset(database)
    first, token = request_training(api, dataset)
    second, _ = request_training(api, dataset)
    for model in (first, second):
        fixture_metrics(database, model["version"], dataset)
    assert (
        client.post(
            "/api/v1/models/" + first["version"] + "/promote",
            headers=headers(token),
            json={"request_id": str(uuid4()), "expected_revision": 0},
        ).status_code
        == 202
    )
    assert (
        client.post(
            "/api/v1/models/" + second["version"] + "/promote",
            headers=headers(token),
            json={"request_id": str(uuid4()), "expected_revision": 1},
        ).status_code
        == 202
    )
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    try:
        supervisor.enqueue_activation()
        supervisor.enqueue_activation()
    finally:
        supervisor.close()
    with admin.connect() as conn:
        states = conn.execute(
            text(
                "SELECT version,state FROM app.activation_notifications ORDER BY revision"
            )
        ).all()
        assert states[0][1] == "superseded" and states[1][1] == "enqueued"
        payload = conn.execute(
            text(
                "SELECT payload FROM transport.outbox WHERE owner='jobs-worker' AND routing_key='model.available'"
            )
        ).scalar_one()
        event = parse_event_v2(bytes(payload))
        assert (
            isinstance(event, ModelAvailableV2)
            and event.conteudo.model_version == second["version"]
        )


def test_changed_active_reference_requires_new_comparable_evaluation(api, database):
    client, _, _, _ = api
    admin, _ = database
    dataset = source_dataset(database)
    first, token = request_training(api, dataset)
    candidate, _ = request_training(api, dataset)
    for model in (first, candidate):
        fixture_metrics(database, model["version"], dataset)
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE app.models SET approved=true WHERE version=:version"),
            {"version": first["version"]},
        )
        conn.execute(
            text("UPDATE app.model_selection SET active_version=:version"),
            {"version": first["version"]},
        )
    response = client.post(
        "/api/v1/models/" + candidate["version"] + "/promote",
        headers=headers(token),
        json={"request_id": str(uuid4()), "expected_revision": 0},
    )
    assert (
        response.status_code == 409
        and "active_reference_changed" in response.json()["title"]
    )


def test_cancelled_training_keeps_source_dataset_complete(api, database, tmp_path):
    client, _, _, _ = api
    _, engines = database
    dataset = source_dataset(database)
    model, token = request_training(api, dataset)
    client.post("/api/v1/jobs/" + model["job_id"] + "/cancel", headers=headers(token))
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    try:
        with engines["api"].connect() as conn:
            raw = bytes(
                conn.execute(
                    text(
                        "SELECT payload FROM transport.outbox WHERE owner='api' AND event_id=:id"
                    ),
                    {"id": model["job_id"]},
                ).scalar_one()
            )
        supervisor.receive(raw, "job.train", "api", model["job_id"])
        supervisor.tick()
        assert (
            client.get(
                "/api/v1/jobs/" + model["job_id"], headers=headers(token)
            ).json()["status"]
            == "cancelled"
        )
        source = client.get(
            "/api/v1/datasets/" + dataset, headers=headers(token)
        ).json()
        assert source["status"] == "completed" and source["sha256"] == "a" * 64
    finally:
        supervisor.close()


def test_real_training_child_registers_artifacts_without_approving_them(
    api, database, tmp_path, monkeypatch
):
    client, _, _, _ = api
    _, engines = database
    dataset = source_dataset(database, tmp_path)
    model, token = request_training(api, dataset)
    supervisor = Supervisor(
        DurableStore(engines["jobs-worker"], "jobs-worker"), tmp_path
    )
    monkeypatch.setattr(supervisor, "unload_model", lambda: None)
    try:
        with engines["api"].connect() as conn:
            raw = bytes(
                conn.execute(
                    text(
                        "SELECT payload FROM transport.outbox WHERE owner='api' AND event_id=:id"
                    ),
                    {"id": model["job_id"]},
                ).scalar_one()
            )
        supervisor.receive(raw, "job.train", "api", model["job_id"])
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            supervisor.tick()
            if supervisor.work is None:
                result = client.get(
                    "/api/v1/models/" + model["version"], headers=headers(token)
                ).json()
                if result["status"] in ("completed", "failed", "cancelled"):
                    break
            time.sleep(0.1)
        else:
            raise AssertionError("Training child did not finish")
        assert result["status"] == "completed" and result["approved"] is False
        assert set(result["report"]["targets"]) == {
            "health_score",
            "rul_calendar_hours",
        }
        assert (tmp_path / "models" / model["version"] / "bundle.joblib").exists()
        assert (
            client.get("/api/v1/datasets/" + dataset, headers=headers(token)).json()[
                "status"
            ]
            == "completed"
        )
    finally:
        supervisor.close()
