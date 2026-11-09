"""Promotion is an explicit, reproducible gate; model.available is only notification."""

from math import isfinite
from typing import Any


def valid_metrics(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        all(
            type(value.get(name)) in (int, float) and isfinite(value[name])
            for name in ("mae", "rmse", "r2")
        )
        and value["mae"] >= 0
        and value["rmse"] >= 0
    )


def promotion_reasons(report: dict[str, Any], active_version: str | None) -> list[str]:
    reasons = []
    if report.get("active_reference_version") != active_version:
        reasons.append("active_reference_changed")
    for target in ("health_score", "rul_calendar_hours"):
        entry = report.get("targets", {}).get(target, {})
        candidate = entry.get("benchmark", {})
        baseline = entry.get("benchmark_baseline", {})
        if (
            not valid_metrics(candidate)
            or not valid_metrics(baseline)
            or not valid_metrics(entry.get("test", {}))
        ):
            reasons.append(target + "_undefined_metrics")
            continue
        if candidate["mae"] > baseline["mae"] * 0.95 or candidate["rmse"] > baseline["rmse"]:
            reasons.append(target + "_below_baseline_gate")
        if active_version is not None:
            active = entry.get("benchmark_active", {})
            if not valid_metrics(active):
                reasons.append(target + "_active_not_comparable")
                continue
            if candidate["mae"] > active["mae"]:
                reasons.append(target + "_regresses_active")
            for mode, values in entry.get("per_mode", {}).items():
                if (
                    values.get("count", 0) >= 100
                    and values.get("active_mae") is not None
                    and values["mae"] > values["active_mae"] * 1.1
                ):
                    reasons.append(target + "_" + mode + "_regression")
    if active_version is not None:
        improvements = []
        for target in ("health_score", "rul_calendar_hours"):
            entry = report.get("targets", {}).get(target, {})
            current = entry.get("benchmark_active", {})
            candidate = entry.get("benchmark", {})
            if valid_metrics(current) and valid_metrics(candidate):
                improvements.append(candidate["mae"] <= current["mae"] * 0.98)
        if not any(improvements):
            reasons.append("insufficient_active_improvement")
    return reasons
