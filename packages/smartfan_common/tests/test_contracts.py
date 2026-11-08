import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from smartfan_common.contracts import (
    command_expired,
    event_fresh,
    mqtt_topic,
    parse_event,
    parse_mqtt_event,
    routing_key,
)
from smartfan_common.topology import QUEUES

CASES = json.loads((Path(__file__).parents[1] / "fixtures/events.v1.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_wire_examples(case):
    payload = json.dumps(case["value"])
    if case["valid"]:
        event = parse_event(payload)
        assert parse_event(event.model_dump_json()) == event
    else:
        with pytest.raises(ValidationError):
            parse_event(payload)


def test_expiry_and_freshness_use_injected_clock():
    now = datetime(2026, 10, 26, 15, 0, 10, tzinfo=timezone.utc)
    command = parse_event(json.dumps(next(c["value"] for c in CASES if c["name"] == "command")))
    assert command_expired(command, now)
    sample = parse_event(json.dumps(CASES[0]["value"]))
    assert not event_fresh(sample, now)
    assert event_fresh(sample, now, max_age_seconds=10)
    assert routing_key(sample) == ("smartfan.events", "telemetry.raw.lab_a.hvac.ac_01")


def test_native_nonfinite_values_cannot_enter_wire():
    for invalid in [float("nan"), float("inf"), float("-inf")]:
        value = copy.deepcopy(CASES[0]["value"])
        value["data"]["readings"]["current_a"] = invalid
        with pytest.raises(ValidationError):
            parse_event(json.dumps(value))


def test_gateway_cannot_cross_device_topics_or_republish_internal_events():
    sample = parse_event(json.dumps(CASES[0]["value"]))
    assert mqtt_topic(sample) == "devices/ac_01/telemetry"
    assert parse_mqtt_event(mqtt_topic(sample), sample.model_dump_json()) == sample
    with pytest.raises(ValueError, match="differ"):
        parse_mqtt_event("devices/ac_02/telemetry", sample.model_dump_json())
    for name in ["persisted", "insight", "generate", "train", "model"]:
        event = parse_event(json.dumps(next(c["value"] for c in CASES if c["name"] == name)))
        with pytest.raises(ValueError, match="no device MQTT"):
            mqtt_topic(event)


def test_routes_have_an_actual_consumer_binding():
    def matches(binding, key):
        left, right = binding.split("."), key.split(".")
        return len(left) == len(right) and all(a == "*" or a == b for a, b in zip(left, right))

    for case in CASES:
        if not case["valid"]:
            continue
        event = parse_event(json.dumps(case["value"]))
        exchange, key = routing_key(event)
        assert any(
            q.exchange == exchange and any(matches(b, key) for b in q.bindings) for q in QUEUES
        ), key
    assert len({q.consumer for q in QUEUES}) >= 4
    assert all(q.prefetch == 1 for q in QUEUES if q.name.startswith("q.jobs."))


def test_command_lifetime_and_freshness_boundaries():
    command = parse_event(json.dumps(next(c["value"] for c in CASES if c["name"] == "command")))
    timestamp = datetime(2026, 10, 26, 15, tzinfo=timezone.utc)
    assert not command_expired(command, timestamp)
    assert command_expired(command, timestamp + timedelta(seconds=10))
    sample = parse_event(json.dumps(CASES[0]["value"]))
    assert not event_fresh(sample, timestamp - timedelta(microseconds=1))
    with pytest.raises(ValueError, match="aware"):
        command_expired(command, timestamp.replace(tzinfo=None))
