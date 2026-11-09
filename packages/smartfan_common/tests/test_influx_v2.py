import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from smartfan_common.contracts_v2 import TelemetrySampleV2
from smartfan_common.energy_v2 import integrate_raw_power
from smartfan_common.influx_v2 import InfluxHTTP, telemetry_point, timestamp_ns


def sample():
    cases = json.loads((Path(__file__).parents[1] / "fixtures/events.v2.json").read_text())
    return TelemetrySampleV2.model_validate(
        next(c["value"] for c in cases if c["valid"] and c["value"]["tipo"] == "telemetry.sampled")
    )


def test_point_identity_bytes_types_and_missing_not_zero():
    event = sample()
    observed = datetime.now(timezone.utc)
    key, raw = telemetry_point(event, observed)
    assert telemetry_point(event, observed) == (key, raw)
    assert b"sequence=" + str(event.metadata.sequence).encode() + b"i" in raw
    assert b'boot_id="' in raw and b'event_id="' in raw
    assert b",event_id=" not in raw.split(b" ")[0]
    changed = event.model_dump()
    changed["conteudo"]["readings"]["current_a"] = None
    changed["conteudo"]["quality"]["missing_fields"] = list(
        set(changed["conteudo"]["quality"]["missing_fields"]) | {"current_a"}
    )
    _, line = telemetry_point(TelemetrySampleV2.model_validate(changed), observed)
    assert b"current_a=" not in line
    assert b'missing_fields="' in line and b"current_a" in line


def test_timestamp_uses_integer_arithmetic_and_timezone_equivalence():
    assert timestamp_ns("2026-11-08T12:00:00.123456Z") == 1794139200123456000
    assert timestamp_ns("2026-11-08T09:00:00.123456-03:00") == timestamp_ns(
        "2026-11-08T12:00:00.123456Z"
    )


def test_history_query_limits_cursor_and_injection(tmp_path):
    token = tmp_path / "token"
    token.write_text("test-only")
    client = InfluxHTTP(token)
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        client.history_query('bad"injection', now - timedelta(hours=1), now)
    with pytest.raises(ValueError):
        client.history_query("ac_01", now - timedelta(days=32), now)
    with pytest.raises(ValueError):
        client.history_query("ac_01", now - timedelta(hours=1), now, 1001)
    query = client.history_query(
        "ac_01",
        now - timedelta(hours=1),
        now,
        2,
        after=(now - timedelta(minutes=1), "quarto", "ac_split_onoff"),
    )
    assert "limit(n:2)" in query and "r.zone>" in query
    assert "aggregateWindow" in client.chart_query("ac_01", now - timedelta(hours=24), now)


def test_energy_does_not_bridge_missing_boots_or_large_gaps():
    now = datetime.now(timezone.utc)

    def row(offset, power, boot="first"):
        return {
            "_time": (now + timedelta(seconds=offset)).isoformat(),
            "power_w": power,
            "boot_id": boot,
        }

    result = integrate_raw_power(
        [
            row(0, "1000"),
            row(2, "1000"),
            row(4, ""),
            row(6, "1000"),
            row(8, "1000", "next"),
            row(20, "1000", "next"),
        ]
    )
    assert result.energy_wh == pytest.approx(1000 * 2 / 3600)
    assert result.covered_seconds == 2 and result.missing_samples == 1
    assert result.discarded_intervals == 2
