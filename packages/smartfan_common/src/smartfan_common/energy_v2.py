"""Raw power integration: missing data and boot boundaries never imply zero power."""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EnergySummary:
    energy_wh: float
    covered_seconds: float
    total_samples: int
    missing_samples: int
    discarded_intervals: int


def integrate_raw_power(
    rows: Iterable[Mapping[str, str]], max_gap_seconds: float = 6
) -> EnergySummary:
    if not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError("Energy gap must be finite and positive")
    previous: tuple[datetime, float, str] | None = None
    energy = covered = 0.0
    total = missing = discarded = 0
    for row in rows:
        total += 1
        power = row.get("power_w", "")
        if not power:
            missing += 1
            previous = None
            continue
        stamp = datetime.fromisoformat(row["_time"])
        value = float(power)
        if stamp.tzinfo is None or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid raw power observation")
        boot = row["boot_id"]
        if previous is not None:
            before, old_power, old_boot = previous
            gap = (stamp - before).total_seconds()
            if 0 < gap <= max_gap_seconds and old_boot == boot:
                energy += (old_power + value) * 0.5 * gap / 3600
                covered += gap
            else:
                discarded += 1
        previous = (stamp, value, boot)
    return EnergySummary(energy, covered, total, missing, discarded)
