"""Export canonical wire schema and cross-language acceptance fixtures.

Run with the backend development Python environment. --check never writes.
"""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/smartfan_common/src"))

from smartfan_common.contracts import EVENT_ADAPTER


def export_values() -> tuple[dict, list[dict]]:
    schema = EVENT_ADAPTER.json_schema()

    def strip_openapi(value):
        if isinstance(value, dict):
            return {
                k: strip_openapi(v) for k, v in value.items() if k != "discriminator"
            }
        if isinstance(value, list):
            return [strip_openapi(v) for v in value]
        return value

    schema = strip_openapi(schema)
    schema.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "urn:smartfan:envelope:v1",
            "title": "EventV1",
        }
    )
    uid = "b7b4d8ec-8b91-4a0a-9d51-56bf65fa1448"
    base = {
        "schema_version": "1.0",
        "id": uid,
        "timestamp": "2026-10-26T15:00:00Z",
        "type": "telemetry.sampled",
        "stream": "live",
        "device_id": "ac_01",
        "zone": "lab_a",
        "equipment_type": "ac_split_onoff",
        "metadata": {"producer": "simulator", "boot_id": uid, "sequence": 1},
        "data": {
            "readings": {
                "current_a": 5.2,
                "compressor_case_temp_c": 67,
                "vibration_rms_mm_s": 2.1,
                "indoor_temp_c": 25.3,
                "outdoor_temp_c": 32,
                "power_w": 1030,
            },
            "actuators": {"compressor_on": True, "condenser_fan_on": True},
            "quality": {"missing_fields": []},
        },
    }
    cases = [{"name": "valid_telemetry", "valid": True, "value": base}]

    def variant(name, event_type, data, system=False):
        value = copy.deepcopy(base)
        value.update(type=event_type, data=data)
        if not event_type.startswith("telemetry."):
            value["metadata"] = {"producer": "api"}
        if system:
            value.update(
                stream="system", device_id=None, zone=None, equipment_type=None
            )
            value["metadata"] = {"producer": "jobs-worker"}
        cases.append({"name": name, "valid": True, "value": value})

    variant("persisted", "telemetry.persisted", base["data"])
    state = copy.deepcopy(base)
    state.update(
        type="device.state",
        data={"actuators": base["data"]["actuators"], "mode": "auto"},
    )
    cases.append({"name": "state", "valid": True, "value": state})
    available = copy.deepcopy(base)
    available.update(type="device.availability", data={"status": "offline"})
    cases.append({"name": "availability", "valid": True, "value": available})
    variant(
        "command",
        "command.requested",
        {
            "target_boot_id": uid,
            "revision": 1,
            "desired": base["data"]["actuators"],
            "mode": "manual",
            "expires_at": "2026-10-26T15:00:10Z",
        },
    )
    variant(
        "ack",
        "command.applied",
        {
            "command_id": uid,
            "revision": 1,
            "status": "applied",
            "observed": base["data"]["actuators"],
            "reason": "ok",
        },
    )
    variant(
        "insight",
        "insight.predicted",
        {
            "source_event_id": uid,
            "model_version": "ridge_1",
            "feature_version": "hvac-window-v1",
            "status": "valid",
            "rul_operating_hours": 20,
            "health_score": 80,
        },
    )
    variant(
        "alert",
        "alert.raised",
        {
            "alert_id": uid,
            "rule_id": uid,
            "severity": "warning",
            "reason_code": "high_vibration",
        },
    )
    variant(
        "generate",
        "dataset.generate.requested",
        {
            "job_id": uid,
            "dataset_id": uid,
            "seed": 42,
            "records": 1000000,
            "equipment_count": 40,
            "chunk_size": 10000,
            "scenarios": ["healthy", "mechanical_wear"],
            "noise_std": 0.1,
            "missing_fraction": 0.01,
            "outlier_fraction": 0.01,
        },
        True,
    )
    variant(
        "train",
        "model.train.requested",
        {
            "job_id": uid,
            "dataset_id": uid,
            "seed": 42,
            "feature_version": "hvac-window-v1",
            "algorithms": ["ridge", "hist_gradient_boosting"],
        },
        True,
    )
    variant(
        "progress",
        "job.progress",
        {
            "job_id": uid,
            "kind": "model.train",
            "status": "running",
            "processed": 0,
            "total": 100,
        },
        True,
    )
    variant(
        "model",
        "model.activated",
        {
            "model_version": "ridge_1",
            "feature_version": "hvac-window-v1",
            "sha256": "a" * 64,
        },
        True,
    )
    for name, event_type, status, reason in [
        ("ack_rejected", "command.rejected", "rejected", "interlock"),
        ("ack_expired", "command.expired", "expired", "expired"),
    ]:
        variant(
            name,
            event_type,
            {
                "command_id": uid,
                "revision": 1,
                "status": status,
                "observed": base["data"]["actuators"],
                "reason": reason,
            },
        )
    for name, event_type in [
        ("alert_cleared", "alert.cleared"),
        ("alert_acknowledged", "alert.acknowledged"),
    ]:
        variant(
            name,
            event_type,
            {
                "alert_id": uid,
                "rule_id": uid,
                "severity": "warning",
                "reason_code": "high_vibration",
            },
        )
    model = next(c["value"] for c in cases if c["name"] == "model")
    variant("model_activation", "model.activation.requested", model["data"], True)
    unavailable = copy.deepcopy(
        next(c["value"]["data"] for c in cases if c["name"] == "insight")
    )
    unavailable.update(status="warming_up", rul_operating_hours=None)
    variant("warming_up", "insight.predicted", unavailable)

    def invalid(name, path, value):
        record = copy.deepcopy(base)
        parent = record
        for part in path[:-1]:
            parent = parent[part]
        parent[path[-1]] = value
        cases.append({"name": name, "valid": False, "value": record})

    invalid("unknown_version", ["schema_version"], "2.0")
    invalid("unknown_event", ["type"], "execute.shell")
    invalid("topic_injection", ["device_id"], "ac.01/#")
    invalid("numeric_identity", ["device_id"], 42)
    invalid("naive_time", ["timestamp"], "2026-10-26T15:00:00")
    invalid("year_zero", ["timestamp"], "0000-01-01T00:00:00Z")
    invalid("leap_second", ["timestamp"], "2026-12-31T23:59:60Z")
    invalid("invalid_calendar", ["timestamp"], "2026-02-30T15:00:00Z")
    invalid("invalid_uuid", ["id"], "not-a-uuid")
    invalid("negative_sequence", ["metadata", "sequence"], -1)
    invalid("boolean_sequence", ["metadata", "sequence"], True)
    invalid("unsafe_integer", ["metadata", "sequence"], 9007199254740992)
    invalid("negative_current", ["data", "readings", "current_a"], -1)
    invalid("string_current", ["data", "readings", "current_a"], "5.2")
    invalid("boolean_current", ["data", "readings", "current_a"], True)
    invalid("string_actuator", ["data", "actuators", "compressor_on"], "false")
    invalid("truth_in_readings", ["data", "readings", "rul_true"], 10)
    invalid("truth_in_metadata", ["metadata", "damage"], 0.9)
    invalid("truth_in_data", ["data", "labels"], {"rul": 10})
    invalid("truth_at_root", ["ground_truth"], 10)
    invalid("lab_in_live_contract", ["stream"], "lab")
    invalid(
        "missing_marker_without_null",
        ["data", "quality", "missing_fields"],
        ["current_a"],
    )
    invalid("null_without_missing_marker", ["data", "readings", "current_a"], None)
    missing = copy.deepcopy(base)
    missing["data"]["readings"]["current_a"] = None
    missing["data"]["quality"]["missing_fields"] = ["current_a"]
    cases.append({"name": "missing_is_not_zero", "valid": True, "value": missing})
    duplicated = copy.deepcopy(missing)
    duplicated["data"]["quality"]["missing_fields"] = ["current_a", "current_a"]
    cases.append(
        {"name": "duplicate_missing_marker", "valid": False, "value": duplicated}
    )
    for name, source, field, value in [
        ("valid_prediction_requires_rul", "insight", "rul_operating_hours", None),
        ("unavailable_prediction_has_no_rul", "warming_up", "rul_operating_hours", 15),
        ("applied_cannot_be_rejected", "ack", "status", "rejected"),
        ("applied_cannot_have_interlock_reason", "ack", "reason", "interlock"),
        ("distinct_algorithms_required", "train", "algorithms", ["ridge", "ridge"]),
        (
            "distinct_scenarios_required",
            "generate",
            "scenarios",
            ["healthy", "healthy"],
        ),
    ]:
        value_event = copy.deepcopy(
            next(c["value"] for c in cases if c["name"] == source)
        )
        value_event["data"][field] = value
        cases.append({"name": name, "valid": False, "value": value_event})
    return schema, cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    schema, cases = export_values()
    for path, value in [
        (ROOT / "packages/smartfan_common/schema/envelope.v1.json", schema),
        (ROOT / "packages/smartfan_common/fixtures/events.v1.json", cases),
        (ROOT / "web-smart-fan-iot/frontend/src/lib/contracts-v1.schema.json", schema),
        (ROOT / "web-smart-fan-iot/frontend/src/lib/contracts-v1.fixtures.json", cases),
    ]:
        content = (
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"Contract artifact differs: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    print("Contract artifacts match" if args.check else "Contract artifacts generated")


if __name__ == "__main__":
    main()
