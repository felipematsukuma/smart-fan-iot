"""Generate v2 schema and fixtures, without touching v1 or operational traffic."""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/smartfan_common/src"))

from smartfan_common.contracts_v2 import EVENT_V2_ADAPTER  # noqa: E402

UID = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
BOOT = "33333333-3333-4333-8333-333333333333"


def export_values():
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "discriminator"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    schema = strip(EVENT_V2_ADAPTER.json_schema())
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:smartfan:message:2.1",
            "title": "EventV2",
        }
    )
    meta = {
        "producer": "simulator",
        "causation_id": None,
        "boot_id": BOOT,
        "sequence": 120,
        "zone": "quarto",
        "equipment_type": "ac_split_onoff",
        "clock_scale": 1,
    }
    readings = {
        "current_a": 4.2,
        "compressor_case_temp_c": 58.0,
        "vibration_rms_mm_s": 1.2,
        "indoor_temp_c": 26.0,
        "outdoor_temp_c": 32.0,
        "power_w": 850.0,
    }
    states = {"compressor_on": True, "condenser_fan_on": True}
    data = {
        "readings": readings,
        "actuators": states,
        "quality": {"missing_fields": []},
    }
    base = {
        "id": UID,
        "schema_version": "2.0",
        "timestamp": "2026-11-08T22:00:00Z",
        "tipo": "telemetry.sampled",
        "dispositivo": "ac_01",
        "correlation_id": None,
        "metadata": meta,
        "conteudo": data,
    }
    cases = []

    def add(name, kind, content, producer="simulator", system=False):
        event = copy.deepcopy(base)
        event.update(tipo=kind, conteudo=copy.deepcopy(content))
        event["metadata"]["producer"] = producer
        if producer in ("writer", "inference", "gateway", "control"):
            event["metadata"]["observed_at"] = base["timestamp"]
        if system or kind == "command.requested":
            event["metadata"] = {"producer": producer, "causation_id": None}
            if kind == "command.requested":
                event["metadata"].update(zone="quarto", equipment_type="ac_split_onoff")
        if system:
            event["dispositivo"] = None
        cases.append({"name": name, "valid": True, "value": event})
        return event

    add("sample", "telemetry.sampled", data)
    missing = copy.deepcopy(data)
    missing["readings"]["current_a"] = None
    missing["quality"]["missing_fields"] = ["current_a"]
    add("missing_sensor", "telemetry.sampled", missing)
    persisted = dict(data, source_event_id=OTHER)
    add("persisted", "telemetry.persisted", persisted, "writer")
    insight = {
        "status": "valid",
        "model_version": "hvac_demo_001",
        "feature_version": "hvac-window-v1",
        "health_score": 72.0,
        "rul_calendar_hours": 24.5,
    }
    add(
        "insight",
        "insight.predicted",
        dict(insight, source_event_id=OTHER),
        "inference",
    )
    frame = {"source_event_id": OTHER, "telemetry": persisted, "insight": insight}
    add("frame", "frame.ready", frame, "inference")
    for status in (
        "warming_up",
        "insufficient_data",
        "inactive",
        "stale",
        "model_unavailable",
        "out_of_domain",
    ):
        unavailable = dict(
            insight,
            status=status,
            model_version=None,
            health_score=None,
            rul_calendar_hours=None,
        )
        add(status, "frame.ready", dict(frame, insight=unavailable), "inference")
    add(
        "command",
        "command.requested",
        {
            "command_id": UID,
            "target_boot_id": BOOT,
            "revision": 12,
            "desired": states,
            "mode": "manual",
            "expires_at": "2026-11-08T22:00:15Z",
            "reason_code": "manual_on",
        },
        "api",
    )
    for status in ("applied", "rejected", "expired"):
        add(
            status,
            "command." + status,
            {
                "command_id": OTHER,
                "revision": 12,
                "observed": states,
                "reason_code": status,
            },
        )
    add(
        "state",
        "device.state",
        {
            "actuators": states,
            "mode": "auto",
            "manual_cooling_block": False,
            "reason_code": "thermostat",
        },
    )
    add(
        "availability",
        "device.availability",
        {"status": "online", "reason_code": "connected"},
    )
    add(
        "receipt",
        "transport.received",
        {"source_event_id": OTHER, "status": "durably_received"},
        "gateway",
    )
    for kind in ("alert.raised", "alert.cleared"):
        add(
            kind,
            kind,
            {
                "alert_id": UID,
                "rule_id": OTHER,
                "severity": "warning",
                "source_event_id": OTHER,
                "reason_code": "health_low",
            },
            "control",
        )
    for kind in ("job.generate", "job.train"):
        add(
            kind,
            kind,
            {"job_id": UID, "dataset_id": OTHER, "config_version": 1},
            "api",
            True,
        )
    add(
        "progress",
        "job.progress",
        {
            "job_id": UID,
            "kind": "train",
            "status": "running",
            "processed": 10,
            "total": 100,
        },
        "jobs-worker",
        True,
    )
    for kind, producer in (
        ("model.available", "jobs-worker"),
        ("model.activated", "inference"),
    ):
        add(
            kind,
            kind,
            {
                "model_version": "hvac_demo_001",
                "feature_version": "hvac-window-v1",
                "dataset_id": OTHER,
                "sha256": "a" * 64,
            },
            producer,
            True,
        )
    failure = {
        "failure_id": UID,
        "owner": "writer",
        "reason_code": "invalid_input",
        "original_sha256": "b" * 64,
        "original_route": "telemetry.quarto.hvac.ac_01",
        "attempts": 5,
        "original_bytes_b64": "e30=",
        "original_ref": None,
    }
    add("quarantine_inline", "message.quarantined", failure, "writer", True)
    add(
        "quarantine_ref",
        "message.quarantined",
        dict(failure, original_bytes_b64=None, original_ref=OTHER),
        "writer",
        True,
    )

    def invalid(name, source, path, value):
        event = copy.deepcopy(next(c["value"] for c in cases if c["name"] == source))
        parent = event
        for part in path[:-1]:
            parent = parent[part]
        parent[path[-1]] = value
        cases.append({"name": name, "valid": False, "value": event})

    for name, path, value in [
        ("old_version", ["schema_version"], "1.0"),
        ("unknown_type", ["tipo"], "shell.execute"),
        ("unsafe_device", ["dispositivo"], "ac/#"),
        ("bad_date", ["timestamp"], "2026-02-30T22:00:00Z"),
        ("naive_date", ["timestamp"], "2026-11-08T22:00:00"),
        ("bad_uuid", ["id"], "abc"),
        ("clock_acceleration", ["metadata", "clock_scale"], 2),
        ("boolean_clock", ["metadata", "clock_scale"], True),
        ("negative_sequence", ["metadata", "sequence"], -1),
        ("boolean_sequence", ["metadata", "sequence"], True),
        ("unsafe_sequence", ["metadata", "sequence"], 9007199254740992),
        ("wrong_producer", ["metadata", "producer"], "api"),
        ("negative_current", ["conteudo", "readings", "current_a"], -1),
        ("string_current", ["conteudo", "readings", "current_a"], "4.2"),
        ("boolean_current", ["conteudo", "readings", "current_a"], True),
        ("missing_unmarked", ["conteudo", "readings", "current_a"], None),
        (
            "false_missing_marker",
            ["conteudo", "quality", "missing_fields"],
            ["current_a"],
        ),
        ("label_root", ["health_true"], 90),
        ("label_metadata", ["metadata", "damage"], 0.4),
        ("label_readings", ["conteudo", "readings", "rul_true_hours"], 12),
        ("label_content", ["conteudo", "labels"], {}),
    ]:
        invalid(name, "sample", path, value)
    invalid(
        "duplicate_missing",
        "missing_sensor",
        ["conteudo", "quality", "missing_fields"],
        ["current_a", "current_a"],
    )
    invalid(
        "unsafe_interlock",
        "command",
        ["conteudo", "desired", "condenser_fan_on"],
        False,
    )
    invalid("command_identity", "command", ["conteudo", "command_id"], OTHER)
    invalid(
        "command_lifetime",
        "command",
        ["conteudo", "expires_at"],
        "2026-11-08T21:59:59Z",
    )
    invalid("frame_identity", "frame", ["conteudo", "source_event_id"], UID)
    invalid("truth_on_old_unit", "insight", ["conteudo", "rul_operating_hours"], 24)
    invalid(
        "unavailable_numeric_rul",
        "model_unavailable",
        ["conteudo", "insight", "rul_calendar_hours"],
        24,
    )
    invalid("valid_null_health", "frame", ["conteudo", "insight", "health_score"], None)
    invalid("progress_over_total", "progress", ["conteudo", "processed"], 101)
    invalid(
        "quarantine_two_sources",
        "quarantine_inline",
        ["conteudo", "original_ref"],
        OTHER,
    )
    invalid("job_device", "job.train", ["dispositivo"], "ac_01")
    numeric = copy.deepcopy(base)
    numeric["metadata"]["sequence"] = 120.0
    cases.append(
        {"name": "json_integer_numeric_equivalence", "valid": True, "value": numeric}
    )
    micro = copy.deepcopy(next(c["value"] for c in cases if c["name"] == "command"))
    micro["timestamp"] = "2026-11-08T22:00:00.000001Z"
    micro["conteudo"]["expires_at"] = "2026-11-08T22:00:00.000002Z"
    cases.append({"name": "submillisecond_lifetime", "valid": True, "value": micro})
    state = copy.deepcopy(next(c["value"] for c in cases if c["name"] == "state"))
    state["schema_version"] = "2.1"
    state["conteudo"]["last_revision"] = 12
    cases.append({"name": "state_v21_revision", "valid": True, "value": state})
    invalid("state_v21_without_revision", "state", ["schema_version"], "2.1")
    invalid("unknown_major", "sample", ["schema_version"], "3.0")
    return schema, cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    schema, cases = export_values()
    outputs = {
        "packages/smartfan_common/schema/envelope.v2.json": schema,
        "packages/smartfan_common/fixtures/events.v2.json": cases,
        "web-smart-fan-iot/frontend/src/lib/contracts-v2.schema.json": schema,
        "web-smart-fan-iot/frontend/src/lib/contracts-v2.fixtures.json": cases,
    }
    for name, value in outputs.items():
        path = ROOT / name
        content = (
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Contract artifact differs: {name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    print("V2 artifacts match" if args.check else "V2 artifacts generated")


if __name__ == "__main__":
    main()
