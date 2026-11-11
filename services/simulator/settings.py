"""Sampling stays within the causal feature window's supported density."""

import math


def sampling_interval(value: str = "2") -> float:
    try:
        interval = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            "SIM_INTERVAL_SECONDS must be a number between 0.2 and 2"
        ) from None
    if not math.isfinite(interval) or not 0.2 <= interval <= 2:
        raise ValueError("SIM_INTERVAL_SECONDS must be finite and between 0.2 and 2")
    return interval
