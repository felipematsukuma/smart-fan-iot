"""Observable predictive rules and pure hysteresis; unavailable data never clears."""

from typing import Annotated

from pydantic import Field, model_validator

from .contracts import WireModel


class PredictiveRule(WireModel):
    enabled: Annotated[bool, Field(strict=True)] = True
    health_raise: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] = 40.0
    health_clear: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] = 45.0
    rul_raise_hours: Annotated[float, Field(ge=0, le=100000, allow_inf_nan=False)] = 24.0
    rul_clear_hours: Annotated[float, Field(ge=0, le=100000, allow_inf_nan=False)] = 30.0
    bad_samples: Annotated[int, Field(strict=True, ge=3, le=30)] = 3
    good_samples: Annotated[int, Field(strict=True, ge=10, le=100)] = 10

    @model_validator(mode="after")
    def increasing_clear_thresholds(self) -> "PredictiveRule":
        if self.health_clear <= self.health_raise or self.rul_clear_hours <= self.rul_raise_hours:
            raise ValueError("Clear thresholds must exceed raise thresholds")
        return self


class PredictiveRuleUpdate(WireModel):
    expected_revision: Annotated[int, Field(strict=True, ge=1)]
    configuration: PredictiveRule


def advance(
    rule: PredictiveRule, health: float, rul: float, bad: int, good: int, active: bool
) -> tuple[int, int, str | None]:
    if health < rule.health_raise or rul < rule.rul_raise_hours:
        bad = min(rule.bad_samples, bad + 1)
        good = 0
    elif health > rule.health_clear and rul > rule.rul_clear_hours:
        good = min(rule.good_samples, good + 1)
        bad = 0
    else:
        bad = good = 0
    transition = (
        "raised"
        if not active and bad >= rule.bad_samples
        else "cleared"
        if active and good >= rule.good_samples
        else None
    )
    return bad, good, transition
