import pytest
from pydantic import ValidationError

from smartfan_common.lab_config import LabConfig


def test_default_counts_vectors_and_primary_sensors_not_individual_fields():
    config = LabConfig()
    assert config.total == 1036800
    assert (
        config.model_dump() == LabConfig.model_validate_json(config.model_dump_json()).model_dump()
    )
    assert sum(config.sensor_counts.model_dump().values()) == 5


@pytest.mark.parametrize(
    "changes",
    [
        {"days": 365},
        {"records_cap": 100},
        {"equipment_count": True},
        {"block_size": 50001},
        {"missing_fraction": 0.3},
        {"sample_interval_seconds": True},
        {"failure_modes": ["mechanical_wear", "mechanical_wear"]},
        {"sensor_counts": {"current_a": 0}},
        {"start_utc": "2026-01-01T00:00:00+03:00"},
    ],
)
def test_invalid_or_unbounded_config_rejected(changes):
    with pytest.raises(ValidationError):
        LabConfig.model_validate(changes)
