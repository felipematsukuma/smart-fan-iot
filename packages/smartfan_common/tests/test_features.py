import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import pytest

from smartfan_common.contracts import parse_event
from smartfan_common.features import (
    FEATURE_NAMES,
    SENSORS,
    FeatureConfig,
    FeatureWindow,
    extract_batch,
)

BASE = json.loads((Path(__file__).parents[1] / "fixtures/events.v1.json").read_text())[0]["value"]
CONFIG = FeatureConfig(min_span_seconds=2, min_samples=3)


def sample(
    index, *, device_id="ac_01", boot_id=None, compressor_on=True, sequence=None, **readings
):
    data = copy.deepcopy(BASE)
    data["timestamp"] = (
        (datetime(2026, 10, 26, tzinfo=timezone.utc) + timedelta(seconds=index))
        .isoformat()
        .replace("+00:00", "Z")
    )
    data["device_id"] = device_id
    if boot_id is not None:
        data["metadata"]["boot_id"] = boot_id
    data["metadata"]["sequence"] = index if sequence is None else sequence
    data["id"] = str(uuid5(NAMESPACE_DNS, f"{device_id}:{data['metadata']['boot_id']}:{index}"))
    data["data"]["actuators"]["compressor_on"] = compressor_on
    data["data"]["readings"].update(readings)
    data["data"]["quality"]["missing_fields"] = [
        name for name in SENSORS if data["data"]["readings"][name] is None
    ]
    return parse_event(json.dumps(data))


def test_batch_and_live_share_causal_features():
    events = [sample(i, current_a=5 + i) for i in range(5)]
    live = FeatureWindow(CONFIG)
    assert [live.push(e) for e in events] == extract_batch(events, CONFIG)
    prefix = extract_batch(events[:3], CONFIG)
    assert prefix == extract_batch(events, CONFIG)[:3]
    vector = prefix[-1].values
    assert vector[FEATURE_NAMES.index("current_a_mean")] == 6
    assert vector[FEATURE_NAMES.index("current_a_slope_per_s")] == 1


def test_duplicates_and_backlog_do_not_mutate_a_window():
    live = FeatureWindow(CONFIG)
    for i in range(3):
        result = live.push(sample(i))
    assert result.status == "valid"
    assert live.push(sample(2)).status == "ignored"
    assert live.push(sample(0)).status == "ignored"
    assert live.push(sample(20)).status == "warming_up"


def test_missing_is_not_treated_as_zero():
    results = extract_batch([sample(i, current_a=None) for i in range(3)], CONFIG)
    assert results[-1].status == "insufficient_data"
    assert results[-1].values is None


def test_restart_and_operating_transitions_reset_features():
    live = FeatureWindow(CONFIG)
    for i in range(3):
        result = live.push(sample(i))
    assert result.status == "valid"
    assert live.push(sample(3, compressor_on=False)).status == "inactive"
    assert live.push(sample(4)).status == "warming_up"
    for i in [5, 6]:
        result = live.push(sample(i))
    assert result.status == "valid"
    assert (
        live.push(sample(7, boot_id=str(uuid5(NAMESPACE_DNS, "newboot")), sequence=0)).status
        == "warming_up"
    )


def test_device_windows_are_isolated_and_bounded():
    live = FeatureWindow(FeatureConfig(min_span_seconds=2, min_samples=3, max_devices=1))
    live.push(sample(0))
    with pytest.raises(ValueError, match="capacity"):
        live.push(sample(1, device_id="ac_02"))
    live.forget("ac_01")
    assert live.push(sample(1, device_id="ac_02")).status == "warming_up"


def test_sample_cap_does_not_claim_a_longer_time_window():
    config = FeatureConfig(min_span_seconds=3, min_samples=2, max_samples=2)
    results = extract_batch([sample(i) for i in range(20)], config)
    assert all(result.status == "warming_up" for result in results)


@pytest.mark.parametrize(
    "config",
    [
        {"max_gap_seconds": float("nan")},
        {"window_seconds": float("inf")},
        {"min_samples": True},
        {"max_samples": 3.5},
        {"max_devices": 0},
    ],
)
def test_window_configuration_must_be_finite_and_bounded(config):
    with pytest.raises(ValueError):
        FeatureConfig(**config)
