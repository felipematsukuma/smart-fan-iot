import pytest
from smartfan_common.features import FeatureConfig

from services.simulator.settings import sampling_interval


def test_default_and_fastest_cadence_preserve_the_supported_causal_window():
    assert sampling_interval() == 2
    interval = sampling_interval("0.2")
    features = FeatureConfig()
    assert features.max_samples * interval >= features.window_seconds
    assert sampling_interval("1") == 1


@pytest.mark.parametrize(
    "value", ["nan", "inf", "-inf", "0", "-1", "0.199", "2.001", "true", ""]
)
def test_bad_cadence_fails_before_device_io(value):
    with pytest.raises(ValueError, match="SIM_INTERVAL_SECONDS"):
        sampling_interval(value)
