import pytest
from pydantic import ValidationError

from smartfan_common.device_registry import DeviceCreate, DeviceProfile, DeviceUpdate
from smartfan_common.ws_protocol import default_descriptor


def test_longest_device_id_generates_valid_stable_component_ids():
    device = DeviceCreate(id="a" * 32, name="Split", zone="sala")
    descriptor = default_descriptor(device.id, device.zone, None, None)
    assert len(set(descriptor.sensor_ids.model_dump().values())) == 5
    assert len(set(descriptor.actuator_ids.model_dump().values())) == 2


@pytest.mark.parametrize(
    "body",
    [
        {"expected_revision": True, "enabled": False},
        {"expected_revision": 1},
        {"expected_revision": 1, "enabled": None},
        {"expected_revision": 1, "enabled": "false"},
        {"expected_revision": 1, "zone": "changed"},
    ],
)
def test_update_requires_typed_revision_and_explicit_nonnull_changes(body):
    with pytest.raises(ValidationError):
        DeviceUpdate.model_validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"rated_power_w": float("nan")},
        {"nominal_voltage_v": True},
        {"expected_life_hours": 999},
        {"healthy_ranges": {"current_a": {"minimum": -1, "maximum": 12}}},
        {"healthy_ranges": {"vibration_rms_mm_s": {"minimum": 0, "maximum": 51}}},
        {"healthy_ranges": {"indoor_temp_c": {"minimum": 28, "maximum": 20}}},
        {"healthy_ranges": {"current_amp": {"minimum": 0, "maximum": 12}}},
    ],
)
def test_profile_rejects_unsafe_or_ambiguous_units_and_nonfinite_values(body):
    with pytest.raises(ValidationError):
        DeviceProfile.model_validate(body)
