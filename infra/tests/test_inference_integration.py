"""Deterministic signed fixtures isolate activation/transactions; runtime test uses trained models."""
# ruff: noqa: F811

import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pytest
from sklearn.dummy import DummyRegressor
from smartfan_common.contracts_v2 import (
    FrameReadyV2,
    TelemetryPersistedV2,
    parse_event_v2,
    serialize_event_v2,
)
from smartfan_common.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    FeatureConfig,
    FeatureSample,
)
from smartfan_common.predictive import PredictiveRule
from smartfan_common.reliability.store import DurableStore
from sqlalchemy import text
from test_api_integration import api, headers, login  # noqa:F401
from test_models_integration import request_training, reset_models, source_dataset  # noqa:F401
from test_reliability_integration import database, reset_disposable_rows  # noqa:F401

from services.control.worker import Controller
from services.gateway.bridge import GatewayBridge
from services.inference.models import ModelRuntime
from services.inference.window import Windows
from services.inference.worker import Inference
from services.jobs.generate import canonical
from services.simulator.device import SimulatorDevice
from services.simulator.physics import PlantConfig

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated real PG",
)


@pytest.fixture(autouse=True)
def reset_predictive_rules(reset_models, database):
    # Only the disposable database: rule edits must not leak across test cases.
    with database[0].begin() as conn:
        conn.execute(text("TRUNCATE app.predictive_rule_versions"))
        conn.execute(
            text(
                "UPDATE app.predictive_rules SET revision=1,configuration=CAST(:config AS jsonb)"
            ),
            {"config": PredictiveRule().model_dump_json()},
        )
        conn.execute(
            text(
                "INSERT INTO app.predictive_rule_versions(device_id,revision,configuration) SELECT device_id,revision,configuration FROM app.predictive_rules"
            )
        )


def model_fixture(api, database, root, health=80.0, rul=100.0, active=None):
    from dataclasses import asdict

    _, _, _, _ = api
    _, engines = database
    dataset = source_dataset(database)
    model, token = request_training(api, dataset)
    version = model["version"]
    path = root / "models" / version
    path.mkdir(parents=True)
    X = np.zeros((4, len(FEATURE_NAMES)))
    bundle = {
        "models": {
            "health_score": DummyRegressor().fit(X, np.full(4, health)),
            "rul_calendar_hours": DummyRegressor().fit(X, np.full(4, rul)),
        },
        "feature_names": list(FEATURE_NAMES),
        "feature_version": FEATURE_VERSION,
        "feature_config": asdict(FeatureConfig()),
        "rul_unit": "calendar_hours",
        "model_version": version,
        "drift_low": np.full(len(FEATURE_NAMES), -1e9),
        "drift_high": np.full(len(FEATURE_NAMES), 1e9),
    }
    joblib.dump(bundle, path / "bundle.joblib")
    metrics = {"mae": 1.0, "rmse": 1.0, "r2": 0.8, "count": 200, "reason": None}
    baseline = {"mae": 3.0, "rmse": 3.0, "r2": 0.1, "count": 200, "reason": None}
    active_metrics = (
        {"mae": 2.0, "rmse": 2.0, "r2": 0.5, "count": 200, "reason": None}
        if active
        else None
    )
    report = {
        "dataset_id": dataset,
        "feature_version": FEATURE_VERSION,
        "active_reference_version": active,
        "targets": {
            target: {
                "test": metrics,
                "benchmark": metrics,
                "benchmark_baseline": baseline,
                "benchmark_active": active_metrics,
                "per_mode": {},
            }
            for target in ("health_score", "rul_calendar_hours")
        },
    }
    content = {
        "report": report,
        "model_version": version,
        "feature_version": FEATURE_VERSION,
        "rul_unit": "calendar_hours",
        "files": {
            "bundle.joblib": hashlib.sha256(
                (path / "bundle.joblib").read_bytes()
            ).hexdigest()
        },
    }
    manifest = {
        "content": content,
        "sha256": hashlib.sha256(canonical(content)).hexdigest(),
    }
    with engines["jobs-worker"].begin() as conn:
        conn.execute(
            text(
                "UPDATE app.models SET status='completed',artifact_sha256=:hash,manifest=CAST(:manifest AS jsonb),report=CAST(:report AS jsonb) WHERE version=:version"
            ),
            {
                "version": version,
                "hash": manifest["sha256"],
                "manifest": json.dumps(manifest),
                "report": json.dumps(report),
            },
        )
    return version, token


def loaded_version(runtime):
    current = runtime.current
    assert current is not None
    return current.version


def promote(api, version, token, revision):
    response = api[0].post(
        "/api/v1/models/" + version + "/promote",
        headers=headers(token),
        json={"request_id": str(uuid4()), "expected_revision": revision},
    )
    assert response.status_code == 202


def test_notification_without_approval_cannot_activate_and_bad_hash_keeps_old(
    api, database, tmp_path
):
    _, engines = database
    version, token = model_fixture(api, database, tmp_path)
    runtime = ModelRuntime(DurableStore(engines["inference"], "inference"), tmp_path)
    assert (
        runtime.synchronize(expected_version=version) is False
        and runtime.current is None
    )
    promote(api, version, token, 0)
    assert runtime.synchronize() and loaded_version(runtime) == version
    bad, token = model_fixture(api, database, tmp_path, active=version)
    promote(api, bad, token, 1)
    (tmp_path / "models" / bad / "bundle.joblib").write_bytes(b"corrupted fixture")
    assert runtime.synchronize() is False and loaded_version(runtime) == version
    assert runtime.last_error == "model_artifact_invalid"


def test_revalidate_desired_revision_after_load_prevents_late_swap(
    api, database, tmp_path
):
    _, engines = database
    first, token = model_fixture(api, database, tmp_path)
    promote(api, first, token, 0)
    runtime = ModelRuntime(DurableStore(engines["inference"], "inference"), tmp_path)
    assert runtime.synchronize()
    second, token = model_fixture(api, database, tmp_path, active=first)
    third, _ = model_fixture(api, database, tmp_path, active=first)
    promote(api, second, token, 1)
    assert not runtime.synchronize(before_swap=lambda: promote(api, third, token, 2))
    assert loaded_version(runtime) == first
    assert runtime.synchronize() and loaded_version(runtime) == third
    with engines["inference"].connect() as conn:
        assert list(
            conn.execute(
                text("SELECT revision FROM app.model_activations ORDER BY revision")
            ).scalars()
        ) == [1, 3]


def test_revoked_approval_stops_serving_active_model(api, database, tmp_path):
    admin, engines = database
    version, token = model_fixture(api, database, tmp_path)
    promote(api, version, token, 0)
    runtime = ModelRuntime(DurableStore(engines["inference"], "inference"), tmp_path)
    assert runtime.synchronize() and loaded_version(runtime) == version
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE app.models SET approved=false WHERE version=:version"),
            {"version": version},
        )
    assert not runtime.synchronize() and runtime.current is None
    with engines["inference"].connect() as conn:
        assert (
            conn.execute(
                text("SELECT active_version FROM app.model_selection WHERE singleton")
            ).scalar_one()
            is None
        )


def test_predictive_rule_permissions_revision_and_audit(api, database):
    client = api[0]
    path = "/api/v1/devices/ac_01/predictive-rule"
    assert client.get(path).status_code == 401
    token = login(api)
    current = client.get(path, headers=headers(token)).json()
    configuration = {**current["configuration"], "bad_samples": 4}
    body = {"expected_revision": current["revision"], "configuration": configuration}
    for name in ("operador", "visualizador"):
        other = login(api, name)
        assert client.get(path, headers=headers(other)).status_code == 200
        assert client.patch(path, headers=headers(other), json=body).status_code == 403
        assert client.get("/api/v1/alerts", headers=headers(other)).status_code == 200
    updated = client.patch(path, headers=headers(token), json=body)
    assert updated.status_code == 200
    assert updated.json()["revision"] == current["revision"] + 1
    assert client.patch(path, headers=headers(token), json=body).status_code == 409
    with database[0].connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM app.audit WHERE action='predictive_rule.updated'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text(
                    "SELECT configuration->>'bad_samples' FROM app.predictive_rule_versions WHERE device_id='ac_01' AND revision=:revision"
                ),
                {"revision": current["revision"] + 1},
            ).scalar_one()
            == "4"
        )


def test_unknown_commit_outcome_never_serves_unconfirmed_pointer_and_reconciles_once(
    api, database, tmp_path, monkeypatch
):
    admin, engines = database
    first, token = model_fixture(api, database, tmp_path)
    promote(api, first, token, 0)
    store = DurableStore(engines["inference"], "inference")
    runtime = ModelRuntime(store, tmp_path)
    assert runtime.synchronize()
    second, token = model_fixture(api, database, tmp_path, active=first)
    promote(api, second, token, 1)
    original = store.transaction

    @contextmanager
    def uncertain(*args, **kwargs):
        with original(*args, **kwargs) as conn:
            yield conn
        raise OSError("Injected lost COMMIT response")

    monkeypatch.setattr(store, "transaction", uncertain)
    with pytest.raises(OSError):
        runtime.synchronize()
    assert runtime.synchronized is False and loaded_version(runtime) == first
    monkeypatch.setattr(store, "transaction", original)
    assert runtime.synchronize() and loaded_version(runtime) == second
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.model_activations")
            ).scalar_one()
            == 2
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.audit WHERE action='model.activated'")
            ).scalar_one()
            == 2
        )


def persisted_fixture(device, gateway, now):
    raw = device.sample(now)
    sample = parse_event_v2(raw)
    gateway.receive_device("devices/ac_01/telemetry", raw)
    observed = gateway.store.received_at(sample.id)
    data = sample.model_dump()
    data.update(id=str(uuid4()), tipo="telemetry.persisted")
    data["metadata"].update(
        producer="writer",
        causation_id=sample.id,
        observed_at=observed.isoformat().replace("+00:00", "Z"),
    )
    data["conteudo"]["source_event_id"] = sample.id
    return TelemetryPersistedV2.model_validate(data)


def test_source_results_are_idempotent_and_old_input_never_gets_new_clock(
    api, database, tmp_path
):
    _, engines = database
    device = SimulatorDevice(tmp_path / "source.sqlite3", PlantConfig())
    gateway = GatewayBridge(DurableStore(engines["gateway"], "gateway"))
    store = DurableStore(engines["inference"], "inference")
    runtime = ModelRuntime(store, tmp_path)
    worker = Inference(store, runtime, Windows(None))
    now = datetime.now(UTC)
    current = persisted_fixture(device, gateway, now)
    raw = serialize_event_v2(current)
    worker.receive(raw, "persisted.quarto.hvac.ac_01", "writer", current.id)
    delivery = store.claim()
    assert delivery is not None
    worker.process(delivery)
    worker.receive(raw, "persisted.quarto.hvac.ac_01", "writer", current.id)
    assert store.claim() is None
    with engines["inference"].connect() as conn:
        frame = parse_event_v2(
            bytes(
                conn.execute(
                    text("SELECT frame_payload FROM app.inference_results")
                ).scalar_one()
            )
        )
        assert (
            isinstance(frame, FrameReadyV2)
            and frame.timestamp == current.timestamp
            and frame.conteudo.insight.status == "model_unavailable"
        )
    old = persisted_fixture(device, gateway, now - timedelta(seconds=10))
    worker.receive(
        serialize_event_v2(old), "persisted.quarto.hvac.ac_01", "writer", old.id
    )
    with engines["inference"].connect() as conn:
        row = conn.execute(
            text(
                "SELECT state,payload,reason_code FROM transport.inbox WHERE owner='inference' AND event_id=:id"
            ),
            {"id": old.id},
        ).one()
        assert (
            row[0] == "completed"
            and row[1] is None
            and row[2] == "stale_prediction_source"
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.inference_results")
            ).scalar_one()
            == 1
        )
    device.close()


def test_persistent_hysteresis_keeps_alarm_through_unavailable_and_model_change(
    api, database, tmp_path
):
    admin, engines = database
    version, token = model_fixture(api, database, tmp_path, health=10, rul=10)
    promote(api, version, token, 0)
    runtime = ModelRuntime(DurableStore(engines["inference"], "inference"), tmp_path)
    assert runtime.synchronize()
    device = SimulatorDevice(tmp_path / "alerts.sqlite3", PlantConfig())
    gateway = GatewayBridge(DurableStore(engines["gateway"], "gateway"))
    with device._transaction() as conn:
        state = device._state(conn)
        state.compressor_on = state.condenser_fan_on = True
        device._save(conn, state)
        conn.execute("UPDATE metadata SET value='1000' WHERE key='sequence'")
    windows = Windows(None)
    windows.restored.add(("ac_01", device.boot_id))
    now = datetime.now(UTC)
    for index in range(31):
        windows.window.push_sample(
            FeatureSample(
                "ac_01",
                device.boot_id,
                index,
                (now - timedelta(seconds=62 - index * 2)).timestamp(),
                True,
                (4.0, 55.0, 1.0, 27.0, 32.0),
            )
        )
    worker = Inference(runtime.store, runtime, windows)
    control = Controller(DurableStore(engines["control"], "control"))

    def step(index, available=True):
        event = persisted_fixture(
            device, gateway, now + timedelta(microseconds=index * 1000)
        )
        if not available:
            runtime.synchronized = False
        worker.receive(
            serialize_event_v2(event), "persisted.quarto.hvac.ac_01", "writer", event.id
        )
        delivery = runtime.store.claim()
        assert delivery is not None
        worker.process(delivery)
        runtime.synchronized = True
        with engines["inference"].connect() as conn:
            raw = bytes(
                conn.execute(
                    text(
                        "SELECT insight_payload FROM app.inference_results WHERE source_event_id=:id"
                    ),
                    {"id": event.conteudo.source_event_id},
                ).scalar_one()
            )
        insight = parse_event_v2(raw)
        control.receive(raw, "insight.ac_01", "inference", insight.id)

    # Fixture times remain in the actual past; no live clock acceleration is used.
    now -= timedelta(seconds=1)
    for index in range(3):
        step(index)
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.alerts WHERE status='active'")
            ).scalar_one()
            == 1
        )
    step(3, False)
    healthy, token = model_fixture(
        api, database, tmp_path, health=90, rul=100, active=version
    )
    promote(api, healthy, token, 1)
    assert runtime.synchronize()
    for index in range(4, 13):
        step(index)
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.alerts WHERE status='active'")
            ).scalar_one()
            == 1
        )
    step(13)
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.alerts WHERE status='cleared'")
            ).scalar_one()
            == 1
        )
    device.close()
