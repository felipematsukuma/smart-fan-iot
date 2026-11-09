from copy import deepcopy

from smartfan_common.model_policy import promotion_reasons


def report():
    metrics = {"mae": 1.0, "rmse": 2.0, "r2": 0.8, "count": 200}
    baseline = {"mae": 2.0, "rmse": 3.0, "r2": 0.1, "count": 200}
    return {
        "active_reference_version": None,
        "targets": {
            target: {
                "test": metrics.copy(),
                "benchmark": metrics.copy(),
                "benchmark_baseline": baseline.copy(),
                "benchmark_active": None,
                "per_mode": {},
            }
            for target in ("health_score", "rul_calendar_hours")
        },
    }


def test_first_promotion_requires_both_targets_to_beat_baseline_with_defined_metrics():
    valid = report()
    assert promotion_reasons(valid, None) == []
    invalid = deepcopy(valid)
    invalid["targets"]["rul_calendar_hours"]["benchmark"]["mae"] = 1.95
    assert "rul_calendar_hours_below_baseline_gate" in promotion_reasons(invalid, None)
    invalid = deepcopy(valid)
    invalid["targets"]["health_score"]["test"]["r2"] = None
    assert "health_score_undefined_metrics" in promotion_reasons(invalid, None)


def test_active_reference_and_improvement_are_mandatory_not_just_new_version():
    value = report()
    value["active_reference_version"] = "mdl_old"
    for target in value["targets"].values():
        target["benchmark_active"] = {"mae": 1.0, "rmse": 2.0, "r2": 0.8, "count": 200}
    assert "insufficient_active_improvement" in promotion_reasons(value, "mdl_old")
    value["targets"]["health_score"]["benchmark"]["mae"] = 0.95
    assert promotion_reasons(value, "mdl_old") == []
    assert "active_reference_changed" in promotion_reasons(value, "mdl_new")


def test_sufficient_mode_regression_blocks_an_overall_improvement():
    value = report()
    value["active_reference_version"] = "mdl_old"
    for target in value["targets"].values():
        target["benchmark_active"] = {"mae": 1.2, "rmse": 2.0, "r2": 0.8, "count": 200}
    value["targets"]["health_score"]["per_mode"] = {
        "mechanical_wear": {"count": 100, "mae": 2.0, "active_mae": 1.0}
    }
    assert "health_score_mechanical_wear_regression" in promotion_reasons(value, "mdl_old")
