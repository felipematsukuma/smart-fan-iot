"""Gateway protocol boundary against an isolated real PostgreSQL database."""
# ruff: noqa: F811

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import (
    CommandRequestedV2,
    TransportReceiptV2,
    parse_event_v2,
    serialize_event_v2,
)
from smartfan_common.reliability.store import DurableStore
from sqlalchemy import text
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

from services.gateway.bridge import GatewayBridge
from services.simulator.device import SimulatorDevice
from services.simulator.physics import PlantConfig

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated Docker integration environment",
)


def command_for(device, now, producer="api", mode="manual"):
    identity = str(uuid4())
    return CommandRequestedV2.model_validate(
        {
            "id": identity,
            "schema_version": "2.0",
            "timestamp": now.isoformat().replace("+00:00", "Z"),
            "tipo": "command.requested",
            "dispositivo": "ac_01",
            "correlation_id": None,
            "metadata": {
                "producer": producer,
                "causation_id": None,
                "zone": "quarto",
                "equipment_type": "ac_split_onoff",
            },
            "conteudo": {
                "command_id": identity,
                "target_boot_id": device.boot_id,
                "revision": 1,
                "desired": {"compressor_on": False, "condenser_fan_on": True},
                "mode": mode,
                "expires_at": (now + timedelta(seconds=15))
                .isoformat()
                .replace("+00:00", "Z"),
                "reason_code": "test",
            },
        }
    )


def test_durable_receipt_duplicate_original_bytes_and_stale_sample(database, tmp_path):
    _, engines = database
    store = DurableStore(engines["gateway"], "gateway")
    bridge = GatewayBridge(store, {"ac_01": "quarto"})
    device = SimulatorDevice(tmp_path / "device.sqlite3", PlantConfig())
    try:
        now = datetime.now(UTC)
        raw = device.sample(now)
        first = bridge.receive_device("devices/ac_01/telemetry", raw)
        assert first is not None
        receipt = parse_event_v2(first[1])
        assert isinstance(receipt, TransportReceiptV2)
        assert receipt.conteudo.source_event_id == parse_event_v2(raw).id
        assert bridge.receive_device("devices/ac_01/telemetry", raw) == first
        outgoing = store.pending_outbox()
        assert len(outgoing) == 1
        claimed = store.claim("outbox")
        assert claimed is not None and claimed.payload == raw
        old = device.sample(now - timedelta(seconds=60))
        bridge.receive_device("devices/ac_01/telemetry", old)
        with engines["gateway"].connect() as conn:
            observed = conn.execute(
                text(
                    "SELECT last_sample_at FROM transport.device_presence WHERE device_id='ac_01'"
                )
            ).scalar_one()
        assert observed == now
    finally:
        device.close()


def test_command_origin_expiry_and_ack_link(database, tmp_path):
    _, engines = database
    store = DurableStore(engines["gateway"], "gateway")
    bridge = GatewayBridge(store, {"ac_01": "quarto"})
    device = SimulatorDevice(tmp_path / "device.sqlite3", PlantConfig())
    try:
        now = datetime.now(UTC)
        command = command_for(device, now)
        raw = serialize_event_v2(command)
        assert not bridge.receive_command(raw, "command.ac_01", "control")
        assert not bridge.receive_command(raw, "command.another", "api")
        assert bridge.receive_command(raw, "command.ac_01", "api")
        assert bridge.receive_command(raw, "command.ac_01", "api")
        assert bridge.dispatchable(command, now)
        assert not bridge.dispatchable(command, now + timedelta(seconds=15))
        bridge.receive_device("devices/ac_01/state", device.report_state(now))
        bridge.receive_device("devices/ac_01/telemetry", device.sample(now))
        assert bridge.ready_for(command, now)
        assert not bridge.ready_for(command, now + timedelta(seconds=7))
        ack = device.command(raw, now)
        assert bridge.receive_device("devices/ac_01/acks", ack) is not None
        assert bridge.has_result(command.id)
        automatic = command_for(device, now, producer="control", mode="manual")
        assert not bridge.receive_command(
            serialize_event_v2(automatic), "command.ac_01", "control"
        )
    finally:
        device.close()


def test_invalid_mqtt_has_no_application_receipt(database):
    _, engines = database
    bridge = GatewayBridge(
        DurableStore(engines["gateway"], "gateway"), {"ac_01": "quarto"}
    )
    assert bridge.receive_device("devices/ac_01/telemetry", b"{}") is None


def test_will_uses_first_gateway_observation_not_configuration_time(database, tmp_path):
    _, engines = database
    store = DurableStore(engines["gateway"], "gateway")
    bridge = GatewayBridge(store, {"ac_01": "quarto"})
    device = SimulatorDevice(tmp_path / "device.sqlite3", PlantConfig())
    try:
        raw = device.availability(
            datetime.now(UTC) - timedelta(hours=2), "offline", will=True
        )
        first = bridge.receive_device("devices/ac_01/availability", raw)
        assert (
            first is not None
            and bridge.receive_device("devices/ac_01/availability", raw) == first
        )
        outgoing = store.claim("outbox")
        assert outgoing is not None
        report = parse_event_v2(outgoing.payload)
        receipt = parse_event_v2(first[1])
        assert report.metadata.producer == "gateway"
        assert report.metadata.causation_id == parse_event_v2(raw).id
        assert report.timestamp == receipt.timestamp
        assert (
            datetime.now(UTC) - datetime.fromisoformat(report.timestamp)
        ).total_seconds() < 5
    finally:
        device.close()
