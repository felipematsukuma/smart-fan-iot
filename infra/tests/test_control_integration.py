"""Real PG control transactions with simulator physical effects and duplicate ACKs."""
# ruff: noqa: F811

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import (
    CommandRequestedV2,
    TelemetrySampleV2,
    parse_event_v2,
)
from smartfan_common.reliability.store import DurableStore
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text
from test_api_integration import api, headers, login  # noqa: F401
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

from services.control.domain import CommandService
from services.control.worker import Controller
from services.gateway.bridge import GatewayBridge
from services.simulator.device import SimulatorDevice
from services.simulator.physics import PlantConfig

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated real PG",
)


@pytest.fixture
def plant(api, database, tmp_path):
    client, _, _, _ = api
    admin, engines = database
    device = SimulatorDevice(tmp_path / "control.sqlite3", PlantConfig())
    gateway = GatewayBridge(DurableStore(engines["gateway"], "gateway"))
    controller = Controller(DurableStore(engines["control"], "control"))
    now = datetime.now(UTC)
    gateway.receive_device("devices/ac_01/state", device.report_state(now))
    raw = device.sample(now)
    gateway.receive_device("devices/ac_01/telemetry", raw)
    event = parse_event_v2(raw)
    controller.receive(raw, routing_key_v2(event)[1], "gateway", event.id)
    yield client, device, gateway, controller, admin, engines
    device.close()


def intent(plant, action="fan_on", key=None, who="operador"):
    client, *_ = plant
    # The imported fixture is also the object returned in plant's API context.
    return client.post(
        "/api/v1/devices/ac_01/commands",
        headers={
            **headers(plant_token(plant, who)),
            "Idempotency-Key": key or str(uuid4()),
        },
        json={"action": action},
    )


def plant_token(plant, who="operador"):
    # Assigned by tests to avoid printing/authenticating with any fixed password.
    return plant[-1]["tokens"][who]


@pytest.fixture
def ready(plant, api):
    plant[-1]["tokens"] = {
        name: login(api, name) for name in ["admin", "operador", "visualizador"]
    }
    yield plant
    del plant[-1]["tokens"]


def apply_physical(plant, command_id):
    _, device, gateway, controller, admin, _ = plant
    with admin.connect() as conn:
        raw = bytes(
            conn.execute(
                text("SELECT payload FROM app.commands WHERE id=:id"),
                {"id": command_id},
            ).scalar_one()
        )
    event = parse_event_v2(raw)
    assert gateway.receive_command(
        raw, routing_key_v2(event)[1], event.metadata.producer
    )
    ack = device.command(raw, datetime.now(UTC))
    gateway.receive_device("devices/ac_01/acks", ack)
    parsed = parse_event_v2(ack)
    controller.receive(ack, routing_key_v2(parsed)[1], "gateway", parsed.id)
    return ack


def test_manual_intention_is_idempotent_and_only_physical_ack_confirms(ready):
    client, device, gateway, controller, admin, _ = ready
    key = str(uuid4())
    response = intent(ready, key=key)
    assert response.status_code == 202
    command = response.json()
    assert command["status"] == "pending" and command["observed"] is None
    assert response.headers["location"].endswith(command["id"])
    assert intent(ready, key=key).json()["id"] == command["id"]
    assert intent(ready, "fan_off", key=key).status_code == 409
    assert intent(ready, "fan_off").status_code == 409
    assert intent(ready, who="visualizador").status_code == 403
    ack = apply_physical(ready, command["id"])
    applied = client.get(
        "/api/v1/commands/" + command["id"], headers=headers(plant_token(ready))
    ).json()
    assert (
        applied["status"] == "confirmed"
        and applied["observed"]["condenser_fan_on"] is True
    )
    assert applied["execution_unknown"] is False
    parsed = parse_event_v2(ack)
    controller.receive(ack, routing_key_v2(parsed)[1], "gateway", parsed.id)
    assert intent(ready, key=key).json()["id"] == command["id"]
    with admin.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM app.commands")).scalar_one() == 1
        assert (
            conn.execute(
                text("SELECT count(*) FROM app.audit WHERE action='command.confirmed'")
            ).scalar_one()
            == 1
        )
    sample = device.sample(datetime.now(UTC))
    gateway.receive_device("devices/ac_01/telemetry", sample)
    measured = parse_event_v2(sample)
    assert isinstance(measured, TelemetrySampleV2)
    assert measured.conteudo.actuators.condenser_fan_on is True


def test_timeout_is_unknown_and_late_physical_ack_reconciles(ready):
    client, _, _, _, admin, _ = ready
    command = intent(ready).json()
    with admin.begin() as conn:
        CommandService.expire(conn, datetime.now(UTC) + timedelta(seconds=21))
    row = client.get(
        "/api/v1/commands/" + command["id"], headers=headers(plant_token(ready))
    ).json()
    assert (
        row["status"] == "failed"
        and row["execution_unknown"] is True
        and row["result"] == "ack_timeout"
    )
    apply_physical(ready, command["id"])
    row = client.get(
        "/api/v1/commands/" + command["id"], headers=headers(plant_token(ready))
    ).json()
    assert row["status"] == "confirmed" and not row["execution_unknown"]


def test_stale_boot_disabled_device_and_viewer_cannot_actuate(ready):
    client, _, _, _, admin, _ = ready
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.control_observations SET sampled_at=clock_timestamp()-interval '7 seconds'"
            )
        )
    assert intent(ready).status_code == 409
    assert (
        client.post(
            "/api/v1/devices/ac_01/commands",
            headers=headers(plant_token(ready)),
            json={"action": "fan_on"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/devices/ac_01/commands",
            headers={**headers(plant_token(ready)), "Idempotency-Key": "valid"},
            json={"action": "compressor_on"},
        ).status_code
        == 422
    )


def test_automatic_threshold_creates_once_and_manual_hold_prevents_override(ready):
    _, device, gateway, controller, admin, _ = ready
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.control_observations SET last_off_at=clock_timestamp()-interval '181 seconds'"
            )
        )
        conn.execute(
            text(
                "UPDATE transport.device_presence SET boot_seen_at=clock_timestamp()-interval '181 seconds'"
            )
        )
    raw = device.sample(datetime.now(UTC))
    event = parse_event_v2(raw)
    gateway.receive_device("devices/ac_01/telemetry", raw)
    controller.receive(raw, routing_key_v2(event)[1], "gateway", event.id)
    with admin.connect() as conn:
        rows = conn.execute(
            text("SELECT id,payload FROM app.commands WHERE producer='control'")
        ).all()
        assert len(rows) == 1
        requested = parse_event_v2(bytes(rows[0][1]))
        assert isinstance(requested, CommandRequestedV2)
        assert requested.conteudo.desired.compressor_on is True
    apply_physical(ready, str(rows[0][0]))
    # A web fan-off request stops both actuators and establishes a manual hold.
    raw = device.sample(datetime.now(UTC))
    event = parse_event_v2(raw)
    assert (
        isinstance(event, TelemetrySampleV2) and event.conteudo.actuators.compressor_on
    )
    gateway.receive_device("devices/ac_01/telemetry", raw)
    controller.receive(raw, routing_key_v2(event)[1], "gateway", event.id)
    command = intent(ready, "fan_off").json()
    apply_physical(ready, command["id"])
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE app.control_observations SET last_off_at=clock_timestamp()-interval '181 seconds'"
            )
        )
    raw = device.sample(datetime.now(UTC))
    event = parse_event_v2(raw)
    gateway.receive_device("devices/ac_01/telemetry", raw)
    controller.receive(raw, routing_key_v2(event)[1], "gateway", event.id)
    with admin.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM app.commands")).scalar_one() == 2


def test_rules_are_admin_only_versioned_and_reject_short_cycles(ready):
    client, _, _, _, _, _ = ready
    original = client.get(
        "/api/v1/devices/ac_01/rule", headers=headers(plant_token(ready))
    ).json()
    body = {
        "expected_revision": original["revision"],
        "configuration": {**original["configuration"], "setpoint_c": 25},
    }
    assert (
        client.patch(
            "/api/v1/devices/ac_01/rule", headers=headers(plant_token(ready)), json=body
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/v1/devices/ac_01/rule",
            headers=headers(plant_token(ready, "admin")),
            json=body,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/devices/ac_01/rule",
            headers=headers(plant_token(ready, "admin")),
            json=body,
        ).status_code
        == 409
    )
    body["expected_revision"] += 1
    body["configuration"]["minimum_off_seconds"] = 1
    assert (
        client.patch(
            "/api/v1/devices/ac_01/rule",
            headers=headers(plant_token(ready, "admin")),
            json=body,
        ).status_code
        == 422
    )
