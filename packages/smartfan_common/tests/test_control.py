from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from smartfan_common.control import RuleConfig, schedule_open, thermostat

NOW = datetime(2026, 11, 9, 15, tzinfo=UTC)


def decide(**changes):
    args = {
        "indoor": 27.0,
        "case": 40.0,
        "compressor": False,
        "fan": False,
        "manual": False,
        "seconds_off": 180.0,
        "seconds_on": 60.0,
    }
    args.update(changes)
    return thermostat(RuleConfig(), NOW, **args)


def test_thermostat_hysteresis_cycles_missing_and_manual():
    assert decide() == (True, True, "thermostat_hot")
    assert decide(seconds_off=179) is None
    assert decide(indoor=24.5) is None
    assert decide(indoor=None) is None
    assert decide(manual=True, case=90) is None  # Local hardware protection remains active.
    assert decide(compressor=True, fan=True, indoor=22) == (False, False, "thermostat_satisfied")
    assert decide(compressor=True, fan=True, indoor=22, seconds_on=59) is None
    assert decide(compressor=True, fan=True, case=80) == (False, True, "thermal_protection")
    assert decide(case=76) is None


def test_overnight_schedule_belongs_to_previous_weekday_and_timezone():
    rule = RuleConfig(schedule_enabled=True, start_hour=22, end_hour=6, weekdays=[1])
    assert schedule_open(
        rule, datetime(2026, 11, 10, 4, tzinfo=UTC)
    )  # Tuesday 01:00 local, Monday window.
    assert not schedule_open(rule, datetime(2026, 11, 11, 4, tzinfo=UTC))
    assert not schedule_open(rule, NOW)
    assert thermostat(
        rule,
        NOW,
        indoor=30,
        case=40,
        compressor=True,
        fan=True,
        manual=False,
        seconds_off=0,
        seconds_on=5,
    ) == (False, False, "schedule_closed")


@pytest.mark.parametrize(
    "changes",
    [
        {"minimum_off_seconds": 179},
        {"minimum_on_seconds": 0},
        {"hysteresis_c": 0},
        {"weekdays": [1, 1]},
        {"start_hour": 7, "end_hour": 7},
        {"enabled": "true"},
        {"setpoint_c": float("nan")},
    ],
)
def test_invalid_rules_rejected(changes):
    with pytest.raises(ValidationError):
        RuleConfig.model_validate(changes)
