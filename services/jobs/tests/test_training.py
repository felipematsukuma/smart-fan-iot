import json
from uuid import uuid4

import numpy as np
import pytest
from smartfan_common.features import (
    FEATURE_NAMES,
    FeatureConfig,
    FeatureSample,
    FeatureWindow,
    summarize_window,
)
from smartfan_common.lab_config import LabConfig
from smartfan_common.model_policy import promotion_reasons
from smartfan_common.training_config import TrainingRequest, TrainingTask

from services.jobs.batch_features import extract
from services.jobs.generate import generate
from services.jobs.train import train


def test_batch_windows_equal_incremental_features_and_reject_future(tmp_path):
    config = LabConfig(days=0.1, equipment_count=6, missing_fraction=0.01)
    manifest = generate(config, tmp_path)
    features = extract(tmp_path, manifest, 1000, 42)
    readings = np.load(tmp_path / "readings.npy", allow_pickle=False)
    stamps = np.load(tmp_path / "timestamp_seconds.npy", allow_pickle=False)
    compressor = np.load(tmp_path / "compressor_on.npy", allow_pickle=False)
    for row in np.linspace(0, len(features["X"]) - 1, num=5, dtype=int):
        index = int(features["source_indices"][row])
        group = int(features["groups"][row])
        start = group * config.samples_per_equipment
        window = FeatureWindow()
        for current in range(start, index + 1):
            result = window.push_sample(
                FeatureSample(
                    str(group),
                    "one_boot",
                    current - start,
                    float(stamps[current]),
                    bool(compressor[current]),
                    tuple(
                        float(value) if np.isfinite(value) else None
                        for value in readings[current]
                    ),
                )
            )
        assert result.status == "valid" and result.values is not None
        np.testing.assert_allclose(
            result.values, features["X"][row], rtol=1e-12, atol=1e-12
        )
    with pytest.raises(ValueError):
        summarize_window(
            [(10.0, (1.0,) * 5), (11.0, (2.0,) * 5), (12.0, (3.0,) * 5)],
            at=11.0,
            config=FeatureConfig(min_span_seconds=1),
        )


def test_changing_true_labels_never_changes_observed_features(tmp_path):
    manifest = generate(LabConfig(days=0.1, equipment_count=6), tmp_path)
    first = extract(tmp_path, manifest, 1000, 42)
    truth = np.lib.format.open_memmap(tmp_path / "health_score.npy", mode="r+")
    truth[:] = 17
    truth.flush()
    del truth
    rul = np.lib.format.open_memmap(tmp_path / "rul_calendar_hours.npy", mode="r+")
    rul[:] = 999
    rul.flush()
    del rul
    second = extract(tmp_path, manifest, 1000, 42)
    np.testing.assert_array_equal(first["X"], second["X"])
    assert not np.array_equal(first["y"], second["y"], equal_nan=True)


def test_grouped_training_writes_both_regressors_baselines_and_importance(tmp_path):
    dataset_id = str(uuid4())
    source = tmp_path / "datasets" / dataset_id
    config = LabConfig(days=0.1, equipment_count=30)
    manifest = generate(config, source)
    task = TrainingTask(
        request=TrainingRequest(
            dataset_id=dataset_id,
            max_feature_rows=6000,
            benchmark_feature_rows=3000,
            importance_rows=100,
        ),
        model_version="mdl_" + uuid4().hex,
        dataset_sha256=manifest["sha256"],
        source_config=config,
    )
    result = train(task, tmp_path / "work" / "test_training", tmp_path)
    report = result["content"]["report"]
    assert report["feature_names"] == list(FEATURE_NAMES)
    groups = report["split"]
    assert (
        not set(groups["train"]) & set(groups["validation"])
        and not set(groups["test"]) & set(groups["train"])
        and not set(groups["test"]) & set(groups["validation"])
    )
    assert report["benchmark_seed"] != config.seed
    assert report["rul_unit"] == "calendar_hours"
    for target in ["health_score", "rul_calendar_hours"]:
        entry = report["targets"][target]
        assert set(entry["validation_candidates"]) == {
            "ridge",
            "hist_gradient_boosting",
        }
        assert all(np.isfinite(entry["test"][name]) for name in ["mae", "rmse", "r2"])
        assert len(entry["feature_importance"]) == 18 and entry["scatter"]
    assert (tmp_path / "work" / "test_training" / "bundle.joblib").exists()
    assert (
        json.loads((tmp_path / "work" / "test_training" / "report.json").read_text())
        == report
    )
    repeated = train(
        task.model_copy(update={"model_version": "mdl_" + uuid4().hex}),
        tmp_path / "work" / "repeat",
        tmp_path,
    )["content"]["report"]
    for target in ("health_score", "rul_calendar_hours"):
        assert (
            repeated["targets"][target]["selected_algorithm"]
            == report["targets"][target]["selected_algorithm"]
        )
        np.testing.assert_allclose(
            [
                repeated["targets"][target]["test"][metric]
                for metric in ("mae", "rmse", "r2")
            ],
            [
                report["targets"][target]["test"][metric]
                for metric in ("mae", "rmse", "r2")
            ],
            rtol=1e-8,
            atol=1e-8,
        )


def test_promotion_rejects_partial_metrics_and_regression_without_fabricated_r2():
    report = {
        "targets": {"health_score": {"test": {"mae": 1, "rmse": 1, "r2": None}}},
        "active_reference_version": None,
    }
    assert "health_score_undefined_metrics" in promotion_reasons(report, None)
