import pytest
from pydantic import ValidationError

from smartfan_common.predictive import PredictiveRule, advance


def test_three_bad_predictions_raise_and_ten_good_predictions_clear():
    rule = PredictiveRule()
    bad = good = 0
    for index in range(3):
        bad, good, transition = advance(rule, 30, 20, bad, good, False)
        assert transition == ("raised" if index == 2 else None)
    for index in range(10):
        bad, good, transition = advance(rule, 80, 40, bad, good, True)
        assert transition == ("cleared" if index == 9 else None)


def test_gray_band_breaks_candidates_without_clearing_active_alert():
    assert advance(PredictiveRule(), 42, 27, 2, 8, True) == (0, 0, None)


@pytest.mark.parametrize(
    "changes",
    [
        {"bad_samples": 2},
        {"good_samples": 9},
        {"health_clear": 35},
        {"rul_clear_hours": 20},
        {"enabled": "true"},
    ],
)
def test_rules_cannot_remove_hysteresis_or_invert_clear_thresholds(changes):
    with pytest.raises(ValidationError):
        PredictiveRule.model_validate(changes)
