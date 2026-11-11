"""Recovery must not let future, foreign-boot or corrupt history affect live features."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import TelemetryPersistedV2
from smartfan_common.features import SENSORS
from smartfan_common.influx_v2 import InfluxHTTP

from services.inference.window import Windows


def event():
    root = Path(__file__).resolve().parents[3]
    controls = json.loads(
        (root / "web-smart-fan-iot/frontend/src/lib/ws.fixtures.json").read_text(
            encoding="utf-8"
        )
    )
    snapshot = next(item["value"] for item in controls if item["name"] == "snapshot")
    frame = next(item for item in snapshot["events"] if item["tipo"] == "frame.ready")
    frame.update(id=str(uuid4()), tipo="telemetry.persisted")
    frame["metadata"]["producer"] = "writer"
    frame["metadata"]["sequence"] = 1000
    frame["conteudo"] = frame["conteudo"]["telemetry"]
    frame["conteudo"]["readings"] = dict(
        zip(SENSORS, (4.0, 55.0, 1.0, 27.0, 32.0), strict=True)
    ) | {"power_w": 800.0}
    frame["conteudo"]["quality"] = {"missing_fields": []}
    frame["conteudo"]["actuators"] = {"compressor_on": True, "condenser_fan_on": True}
    return TelemetryPersistedV2.model_validate(frame)


def history(source):
    at = datetime.fromisoformat(source.timestamp)
    return [
        {
            "_time": (at - timedelta(seconds=60 - index * 2)).isoformat(),
            "boot_id": source.metadata.boot_id,
            "sequence": str(index),
            "compressor_on": "true",
            **{
                field: str(getattr(source.conteudo.readings, field))
                for field in SENSORS
            },
        }
        for index in range(30)
    ]


class History(InfluxHTTP):
    def __init__(self, rows, fail=False):
        self.rows = rows
        self.fail = fail
        self.bucket = "live"
        self.calls = 0

    def query(self, flux):
        self.calls += 1
        if self.fail:
            raise OSError("History dependency unavailable")
        return self.rows


def test_past_only_same_boot_history_matches_clean_features_and_restores_once():
    source = event()
    rows = history(source)
    future = {
        **rows[-1],
        "_time": (
            datetime.fromisoformat(source.timestamp) + timedelta(seconds=1)
        ).isoformat(),
        "current_a": "10000",
    }
    foreign = {**rows[-1], "boot_id": str(uuid4()), "current_a": "10000"}
    invalid_boolean = {**rows[-1], "compressor_on": "unknown", "current_a": "10000"}
    transport = History([*rows, future, foreign, invalid_boolean])
    recovered = Windows(transport)
    result = recovered.push(source)
    reference = Windows(History(rows)).push(source)
    assert result.status == reference.status == "valid"
    assert result.values == reference.values
    assert recovered.push(source).status == "ignored" and transport.calls == 1


@pytest.mark.parametrize("corruption", ["unavailable", "bad_number", "bad_sequence"])
def test_failed_recovery_warms_from_current_sample_instead_of_partial_history(
    corruption,
):
    source = event()
    rows = history(source)
    if corruption == "bad_number":
        rows[-1]["current_a"] = "not-a-reading"
    elif corruption == "bad_sequence":
        rows[-1]["sequence"] = "not-a-sequence"
    result = Windows(History(rows, fail=corruption == "unavailable")).push(source)
    assert result.status == "warming_up" and result.values is None
