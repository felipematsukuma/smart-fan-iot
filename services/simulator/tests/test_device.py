import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import (
    CommandAckV2,
    DeviceStateV2,
    TelemetrySampleV2,
    parse_event_v2,
)

from services.simulator.device import SimulatorDevice, SpoolFull
from services.simulator.physics import PlantConfig, PlantState, advance

NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


def test_v21_retained_state_reports_command_watermark_after_reboot(tmp_path):
    path = tmp_path / "device.db"
    device = SimulatorDevice(path)
    device.command(command(device, revision=7, compressor=False), NOW)
    state = parse_event_v2(device.report_state(NOW))
    assert isinstance(state, DeviceStateV2) and state.schema_version == "2.1"
    assert state.conteudo.last_revision == 7
    device.close()
    device = SimulatorDevice(path)
    try:
        state = parse_event_v2(device.report_state(NOW + timedelta(seconds=2)))
        assert isinstance(state, DeviceStateV2)
        assert state.conteudo.last_revision == 7
        assert not state.conteudo.actuators.compressor_on
    finally:
        device.close()


def command(
    device,
    *,
    revision=1,
    compressor=True,
    fan=True,
    now=NOW,
    boot=None,
    producer="api",
    mode="manual",
):
    identity = str(uuid4())
    return json.dumps(
        {
            "id": identity,
            "schema_version": "2.0",
            "timestamp": (now - timedelta(seconds=1))
            .isoformat()
            .replace("+00:00", "Z"),
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
                "target_boot_id": boot or device.boot_id,
                "revision": revision,
                "desired": {"compressor_on": compressor, "condenser_fan_on": fan},
                "mode": mode,
                "expires_at": (now + timedelta(seconds=15))
                .isoformat()
                .replace("+00:00", "Z"),
                "reason_code": "test_intent",
            },
        }
    ).encode()


def ack(raw):
    result = parse_event_v2(raw)
    assert isinstance(result, CommandAckV2)
    return result


def test_five_sensors_closed_telemetry_and_real_command_effect(tmp_path):
    device = SimulatorDevice(tmp_path / "device.db")
    try:
        before = parse_event_v2(device.sample(NOW))
        assert isinstance(before, TelemetrySampleV2)
        assert before.conteudo.readings.current_a == 0
        raw = command(device)
        assert ack(device.command(raw, NOW)).tipo == "command.applied"
        after = parse_event_v2(device.sample(NOW + timedelta(seconds=2)))
        assert isinstance(after, TelemetrySampleV2)
        assert (
            after.conteudo.readings.current_a is not None
            and after.conteudo.readings.current_a > 0
        )
        assert after.conteudo.actuators.compressor_on
        assert not any(
            word in after.model_dump_json()
            for word in ("damage", "health_true", "rul_true", "operating_hours")
        )
        assert device.command(raw, NOW + timedelta(seconds=1)) == device.command(
            raw, NOW + timedelta(seconds=2)
        )
    finally:
        device.close()


def test_spool_survives_reboot_receipt_is_required_and_boot_changes(tmp_path):
    path = tmp_path / "device.db"
    device = SimulatorDevice(path)
    raw = command(device)
    original = device.command(raw, NOW)
    sample = device.sample(NOW + timedelta(seconds=2))
    sample_id = parse_event_v2(sample).id
    old_boot = device.boot_id
    device.sent(sample_id, NOW.timestamp())
    assert any(row[0] == sample_id for row in device.pending(NOW.timestamp() + 6))
    device.close()
    device = SimulatorDevice(path)
    try:
        assert device.boot_id != old_boot
        assert not device.state().compressor_on
        assert any(row[0] == sample_id for row in device.pending(NOW.timestamp() + 6))
        assert device.command(raw, NOW + timedelta(seconds=3)) == original
        device.receipt(sample_id)
        assert not any(
            row[0] == sample_id for row in device.pending(NOW.timestamp() + 6)
        )
        assert (
            ack(
                device.command(command(device, boot=old_boot, revision=2), NOW)
            ).conteudo.reason_code
            == "boot_mismatch"
        )
    finally:
        device.close()


def test_expiry_revision_cooldown_and_manual_block(tmp_path):
    device = SimulatorDevice(tmp_path / "device.db")
    try:
        assert ack(device.command(command(device), NOW)).tipo == "command.applied"
        off = command(device, revision=2, compressor=False, fan=False)
        assert (
            ack(device.command(off, NOW + timedelta(seconds=1))).tipo
            == "command.applied"
        )
        denied = ack(
            device.command(command(device, revision=3), NOW + timedelta(seconds=2))
        )
        assert denied.conteudo.reason_code == "restart_delay"
        later = NOW + timedelta(seconds=182)
        blocked = ack(
            device.command(
                command(device, revision=4, now=later, producer="control", mode="auto"),
                later,
            )
        )
        assert blocked.conteudo.reason_code == "manual_block"
        released = ack(
            device.command(
                command(device, revision=5, now=later, compressor=False, mode="auto"),
                later,
            )
        )
        assert (
            released.tipo == "command.applied"
            and not device.state().manual_cooling_block
        )
        assert (
            ack(
                device.command(command(device, revision=4, now=later), later)
            ).conteudo.reason_code
            == "stale_revision"
        )
        expired = command(device, revision=6, now=later)
        assert (
            ack(device.command(expired, later + timedelta(seconds=16))).tipo
            == "command.expired"
        )
        assert not device.state().compressor_on
    finally:
        device.close()


def test_quota_rolls_back_actuator_effect_and_preserves_message_identity(tmp_path):
    device = SimulatorDevice(tmp_path / "device.db", quota_bytes=1)
    try:
        with pytest.raises(SpoolFull):
            device.command(command(device), NOW)
        assert not device.state().compressor_on
    finally:
        device.close()


def test_same_command_id_different_bytes_never_reapplies(tmp_path):
    device = SimulatorDevice(tmp_path / "device.db")
    try:
        raw = command(device)
        device.command(raw, NOW)
        changed = json.loads(raw)
        changed["conteudo"]["desired"] = {
            "compressor_on": False,
            "condenser_fan_on": False,
        }
        with pytest.raises(ValueError, match="identity conflict"):
            device.command(json.dumps(changed).encode(), NOW)
        assert device.state().compressor_on
    finally:
        device.close()


def test_progressive_degradation_and_temperature_context_are_reproducible():
    config = PlantConfig(
        scenario="mechanical_wear", damage_per_operating_hour=1.0, noise=0.0
    )
    one = PlantState(compressor_on=True, condenser_fan_on=True)
    two = PlantState(compressor_on=True, condenser_fan_on=True)
    start = advance(one, config, NOW.timestamp(), 2)
    advance(two, config, NOW.timestamp(), 2)
    for index in range(1, 200):
        left = advance(one, config, NOW.timestamp() + 2 * index, 2)
        right = advance(two, config, NOW.timestamp() + 2 * index, 2)
        assert left == right
    assert left["current_a"] > start["current_a"]
    assert left["vibration_rms_mm_s"] > start["vibration_rms_mm_s"]
    assert left["compressor_case_temp_c"] > start["compressor_case_temp_c"]
    healthy = PlantState(compressor_on=True, condenser_fan_on=True)
    for _ in range(20):
        advance(healthy, PlantConfig(), NOW.timestamp(), 2)
    assert healthy.damage == 0


def test_local_thermal_protection_and_last_will_are_not_fake_measurements(tmp_path):
    state = PlantState(compressor_on=True, condenser_fan_on=True, case_temp_c=100.0)
    advance(state, PlantConfig(), NOW.timestamp(), 2)
    assert state.thermal_lock and not state.compressor_on
    device = SimulatorDevice(tmp_path / "device.db")
    try:
        will = device.availability(NOW, "offline", will=True)
        assert parse_event_v2(will).tipo == "device.availability"
        assert device.pending(NOW.timestamp()) == []
    finally:
        device.close()
