"""Bounded historical charts and raw-power energy; never feeds the live store."""

import math
from datetime import timedelta

from smartfan_common.influx_v2 import InfluxHTTP

from .errors import Problem
from .realtime import utc_now, wire_time


def metrics(client: InfluxHTTP, device_id: str, hours: int) -> dict:
    stop = utc_now()
    start = stop - timedelta(hours=hours)
    try:
        rows = client.query(client.chart_query(device_id, start, stop))
        energy_rows = client.query(client.energy_query(device_id, start, stop))
    except (OSError, ValueError):
        raise Problem(
            503, "history_unavailable", "Histórico temporariamente indisponível."
        ) from None
    fields = (
        "current_a",
        "compressor_case_temp_c",
        "vibration_rms_mm_s",
        "indoor_temp_c",
        "outdoor_temp_c",
        "power_w",
    )
    points = []
    for row in rows:
        point: dict[str, str | float | None] = {"timestamp": row["_time"]}
        for name in fields:
            value = float(row[name]) if row.get(name) else None
            if value is not None and not math.isfinite(value):
                raise Problem(
                    503, "invalid_history", "O histórico não pôde ser validado."
                )
            point[name] = value
        points.append(point)
    raw = energy_rows[0] if energy_rows else {}
    energy = {
        name: float(raw.get(name, "0"))
        for name in (
            "energy_wh",
            "covered_seconds",
            "total_samples",
            "missing_samples",
            "discarded_intervals",
        )
    }
    if any(not math.isfinite(value) or value < 0 for value in energy.values()):
        raise Problem(503, "invalid_history", "O histórico não pôde ser validado.")
    energy["coverage_fraction"] = min(1, energy["covered_seconds"] / (hours * 3600))
    return {
        "device_id": device_id,
        "period_start": wire_time(start),
        "period_end": wire_time(stop),
        "chart": points,
        "energy": {
            **energy,
            "energy_wh": energy["energy_wh"] if energy["covered_seconds"] > 0 else None,
            "status": "available" if energy["covered_seconds"] > 0 else "no_data",
        },
    }
