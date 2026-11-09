"""Causal thermostat decisions; all timestamps are real UTC calendar time."""

from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from .contracts import WireModel


class RuleConfig(WireModel):
    enabled: Annotated[bool, Field(strict=True)] = True
    setpoint_c: Annotated[float, Field(ge=18, le=30, allow_inf_nan=False)] = 24
    hysteresis_c: Annotated[float, Field(ge=0.5, le=3, allow_inf_nan=False)] = 1
    minimum_off_seconds: Annotated[int, Field(strict=True, ge=180, le=1800)] = 180
    minimum_on_seconds: Annotated[int, Field(strict=True, ge=60, le=600)] = 60
    schedule_enabled: Annotated[bool, Field(strict=True)] = False
    start_hour: Annotated[int, Field(strict=True, ge=0, le=23)] = 7
    end_hour: Annotated[int, Field(strict=True, ge=0, le=23)] = 23
    weekdays: list[Annotated[int, Field(strict=True, ge=1, le=7)]] = Field(
        default_factory=lambda: list(range(1, 8)), min_length=1, max_length=7
    )

    @model_validator(mode="after")
    def schedule_valid(self) -> "RuleConfig":
        if self.start_hour == self.end_hour or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("Schedule must have distinct hours and unique weekdays")
        return self


class RuleUpdate(WireModel):
    expected_revision: Annotated[int, Field(strict=True, ge=1)]
    configuration: RuleConfig


class CommandIntent(WireModel):
    action: Literal["fan_on", "fan_off", "release_auto"]


def schedule_open(rule: RuleConfig, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("UTC-aware clock required")
    if not rule.schedule_enabled:
        return True
    local = now.astimezone(ZoneInfo("America/Sao_Paulo"))
    if rule.start_hour < rule.end_hour:
        return local.isoweekday() in rule.weekdays and rule.start_hour <= local.hour < rule.end_hour
    # After midnight belongs to the previous day's overnight schedule.
    day = local.isoweekday() if local.hour >= rule.start_hour else (local.isoweekday() - 2) % 7 + 1
    return day in rule.weekdays and (local.hour >= rule.start_hour or local.hour < rule.end_hour)


def thermostat(
    rule: RuleConfig,
    now: datetime,
    *,
    indoor: float | None,
    case: float | None,
    compressor: bool,
    fan: bool,
    manual: bool,
    seconds_off: float,
    seconds_on: float,
) -> tuple[bool, bool, str] | None:
    if manual:
        return None
    if case is not None and case >= 80:
        desired = (False, True, "thermal_protection")
    elif not rule.enabled or not schedule_open(rule, now):
        desired = (False, False, "schedule_closed" if rule.enabled else "rule_disabled")
    elif indoor is None or case is None:
        return None
    elif compressor:
        desired = (
            (False, False, "thermostat_satisfied")
            if indoor <= rule.setpoint_c - rule.hysteresis_c
            and seconds_on >= rule.minimum_on_seconds
            else (True, True, "cooling")
        )
    elif (
        indoor >= rule.setpoint_c + rule.hysteresis_c
        and case <= 75
        and seconds_off >= rule.minimum_off_seconds
    ):
        desired = (True, True, "thermostat_hot")
    else:
        return None
    return desired if desired[:2] != (compressor, fan) else None
