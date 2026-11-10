"""Corrupt or noncausal lab data must fail before training can publish a model."""

import copy
import hashlib
import json

import numpy as np
import pytest
from smartfan_common.lab_config import LabConfig
from smartfan_common.ml_pipeline import TrainingQuantiles, predict_target

from services.jobs.batch_features import extract
from services.jobs.generate import Cancelled, canonical, generate
from services.jobs.train import dataset_manifest, metrics


@pytest.fixture
def dataset(tmp_path):
    manifest = generate(LabConfig(days=0.03, equipment_count=6), tmp_path)
    return tmp_path, manifest


@pytest.mark.parametrize(
    "corruption", ["channels", "shape", "dtype", "groups", "chronology", "uneven"]
)
def test_extractor_rejects_corrupt_equipment_or_sensor_alignment(dataset, corruption):
    path, manifest = dataset
    manifest = copy.deepcopy(manifest)
    content = manifest["content"]
    if corruption == "channels":
        content["primary_channel_indices"].reverse()
    elif corruption in ("shape", "dtype", "uneven"):
        values = np.load(path / "readings.npy")
        if corruption == "shape":
            values = values[:, :-1]
        elif corruption == "dtype":
            values = values.astype(np.float64)
        else:
            values = values[:-1]
            content["rows"] -= 1
        np.save(path / "readings.npy", values, allow_pickle=False)
    elif corruption == "groups":
        values = np.load(path / "equipment_index.npy")
        values[0] = 1
        np.save(path / "equipment_index.npy", values, allow_pickle=False)
    else:
        values = np.load(path / "timestamp_seconds.npy")
        values[1] = values[0]
        np.save(path / "timestamp_seconds.npy", values, allow_pickle=False)
    with pytest.raises(ValueError):
        extract(path, manifest, 1000, 42)


def test_cancellation_inside_device_window_and_no_usable_windows(dataset):
    path, manifest = dataset
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 2

    with pytest.raises(InterruptedError):
        extract(path, manifest, 1000, 42, cancel)
    assert calls == 2
    running = np.load(path / "compressor_on.npy")
    running[:] = False
    np.save(path / "compressor_on.npy", running, allow_pickle=False)
    with pytest.raises(ValueError, match="Insufficient causal"):
        extract(path, manifest, 1000, 42)


@pytest.mark.parametrize("corruption", ["manifest", "file_set", "bytes", "cancel"])
def test_training_verifies_manifest_and_every_file_before_loading(dataset, corruption):
    path, manifest = dataset
    expected = manifest["sha256"]
    if corruption == "manifest":
        manifest["content"]["rows"] += 1
    elif corruption == "file_set":
        manifest["content"]["files"].pop("outliers.npy")
        expected = hashlib.sha256(canonical(manifest["content"])).hexdigest()
        manifest["sha256"] = expected
    elif corruption == "bytes":
        with (path / "readings.npy").open("ab") as stream:
            stream.write(b"corruption")
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(Cancelled if corruption == "cancel" else ValueError):
        dataset_manifest(path, expected, lambda: corruption == "cancel")


def test_invalid_metrics_and_feature_width_cannot_be_reported_as_model_quality():
    assert metrics(np.array([1.0, np.nan]), np.array([1.0, 2.0]))["mae"] is None
    constant = metrics(np.array([3.0, 3.0]), np.array([3.0, 3.0]))
    assert constant["r2"] is None and constant["reason"] == "constant_target"
    fitted = TrainingQuantiles().fit(np.array([[1.0, 2.0], [2.0, 3.0]]))
    for invalid in (np.ones(2), np.ones((2, 3))):
        with pytest.raises(ValueError, match="dimensions"):
            fitted.transform(invalid)
    with pytest.raises(ValueError, match="Unknown regression target"):
        predict_target(None, np.zeros((1, 18)), "unapproved_target")
