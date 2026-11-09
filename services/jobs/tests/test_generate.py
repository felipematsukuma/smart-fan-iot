import numpy as np
import pytest
from smartfan_common.lab_config import LabConfig

from services.jobs.generate import Cancelled, generate


def test_seed_and_substreams_reproduce_hash_across_block_sizes(tmp_path):
    config = LabConfig(
        days=0.02,
        equipment_count=4,
        block_size=100,
        missing_fraction=0.1,
        outlier_fraction=0.05,
    )
    first = generate(config, tmp_path / "first")
    second = generate(
        config.model_copy(update={"block_size": 50000}), tmp_path / "second"
    )
    assert first["sha256"] == second["sha256"]
    assert first["content"]["rows"] == config.total
    readings = np.load(
        tmp_path / "first" / "readings.npy", mmap_mode="r", allow_pickle=False
    )
    assert readings.shape == (config.total, 5)
    assert 0.07 < np.isnan(readings).mean() < 0.13
    outliers = np.load(
        tmp_path / "first" / "outliers.npy", mmap_mode="r", allow_pickle=False
    )
    assert 0.03 < outliers.mean() < 0.07


def test_progressive_mechanical_fault_affects_three_sensors_and_censors_unknown_rul(
    tmp_path,
):
    config = LabConfig(
        days=0.1,
        equipment_count=12,
        failure_fraction=1,
        failure_modes=["mechanical_wear"],
        noise_std=0,
        missing_fraction=0,
        outlier_fraction=0,
    )
    manifest = generate(config, tmp_path / "failure")
    readings = np.load(tmp_path / "failure" / "readings.npy", allow_pickle=False)
    health = np.load(tmp_path / "failure" / "health_score.npy", allow_pickle=False)
    active = np.load(tmp_path / "failure" / "compressor_on.npy", allow_pickle=False)
    damage = 1 - health / 100
    for column in [0, 1, 2]:
        assert np.corrcoef(damage[active], readings[active, column])[0, 1] > 0.5
    rul = np.load(tmp_path / "failure" / "rul_calendar_hours.npy", allow_pickle=False)
    censored = np.load(tmp_path / "failure" / "censored.npy", allow_pickle=False)
    assert np.isnan(rul[censored]).all()
    assert np.isfinite(rul[~censored]).all() and (~censored).any()
    assert manifest["content"]["rul_unit"] == "calendar_hours"
    for start in range(0, config.total, config.samples_per_equipment):
        assert np.all(
            np.diff(health[start : start + config.samples_per_equipment]) <= 0
        )


def test_healthy_devices_have_unknown_rul_instead_of_zero(tmp_path):
    generate(LabConfig(days=0.01, equipment_count=3, failure_fraction=0), tmp_path)
    assert np.isnan(
        np.load(tmp_path / "rul_calendar_hours.npy", allow_pickle=False)
    ).all()
    assert (np.load(tmp_path / "health_score.npy", allow_pickle=False) == 100).all()


def test_cancelled_partial_does_not_have_complete_manifest(tmp_path):
    checks = 0

    def cancel():
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(Cancelled):
        generate(
            LabConfig(days=0.01, equipment_count=3, block_size=100), tmp_path, cancel
        )
    assert not (tmp_path / "manifest.json").exists()
    assert (tmp_path / "progress.json").exists()
