import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from smartfan_common.contracts import parse_event
from smartfan_common.contracts_v2 import (
    CommandRequestedV2,
    TelemetrySampleV2,
    command_expired_v2,
    event_fresh_v2,
    parse_event_v2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.features import FeatureWindow
from smartfan_common.features_v2 import FeatureWindowV2, iter_features_v2
from smartfan_common.routing_v2 import (
    QUEUES_V2,
    mqtt_topic_v2,
    parse_mqtt_event_v2,
    routing_key_v2,
)

CASES = json.loads((Path(__file__).parents[1] / "fixtures/events.v2.json").read_text())


def example(name):
    return copy.deepcopy(next(c["value"] for c in CASES if c["name"] == name))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_v2_shared_acceptance_cases(case):
    if case["valid"]:
        event = parse_event_v2(json.dumps(case["value"]))
        assert parse_event_v2(serialize_event_v2(event)) == event
    else:
        with pytest.raises((ValueError, ValidationError)):
            parse_event_v2(json.dumps(case["value"]))


def test_no_implicit_v1_v2_conversion():
    with pytest.raises(ValidationError):
        parse_event(json.dumps(example("sample")))
    v1 = json.loads((Path(__file__).parents[1] / "fixtures/events.v1.json").read_text())[0]
    with pytest.raises(ValidationError):
        parse_event_v2(json.dumps(v1["value"]))


def test_time_helpers_use_real_aware_clock():
    event = parse_event_v2(json.dumps(example("command")))
    assert isinstance(event, CommandRequestedV2)
    now = datetime(2026, 11, 8, 22, 0, 0, tzinfo=timezone.utc)
    assert not command_expired_v2(event, now)
    assert command_expired_v2(event, now + timedelta(seconds=15))
    assert event_fresh_v2(event, now)
    assert not event_fresh_v2(event, now - timedelta(seconds=1))
    assert not event_fresh_v2(event, now + timedelta(seconds=7))
    with pytest.raises(ValueError):
        command_expired_v2(event, datetime(2026, 11, 8))


def test_wire_limits_and_hash_of_exact_bytes():
    raw = serialize_event_v2(parse_event_v2(json.dumps(example("sample"))))
    assert payload_sha256(raw) != payload_sha256(raw + b" ")
    with pytest.raises(ValueError, match="normal"):
        parse_event_v2(raw + b" " * 16384)
    with pytest.raises(ValueError, match="transport"):
        parse_event_v2(raw + b" " * 32768)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_sensor_is_rejected(number):
    value = example("sample")
    value["conteudo"]["readings"]["current_a"] = number
    with pytest.raises(ValidationError):
        parse_event_v2(json.dumps(value))


def test_every_amqp_event_has_binding_and_internal_data_never_goes_to_mqtt():
    def matches(binding, key):
        if binding == "#":
            return True
        a, b = binding.split("."), key.split(".")
        return len(a) == len(b) and all(x == "*" or x == y for x, y in zip(a, b))

    for case in CASES:
        if not case["valid"]:
            continue
        event = parse_event_v2(json.dumps(case["value"]))
        if event.tipo == "transport.received":
            with pytest.raises(ValueError):
                routing_key_v2(event)
        else:
            exchange, key = routing_key_v2(event)
            assert any(
                q.exchange == exchange and any(matches(b, key) for b in q.bindings)
                for q in QUEUES_V2
            ), key
        if event.tipo in (
            "telemetry.persisted",
            "frame.ready",
            "insight.predicted",
            "job.train",
            "model.available",
        ):
            with pytest.raises(ValueError):
                mqtt_topic_v2(event)
    event = parse_event_v2(json.dumps(example("sample")))
    assert mqtt_topic_v2(event) == "devices/ac_01/telemetry"
    assert parse_mqtt_event_v2(mqtt_topic_v2(event), serialize_event_v2(event)) == event
    with pytest.raises(ValueError):
        parse_mqtt_event_v2("devices/ac_02/telemetry", serialize_event_v2(event))


def test_v2_batch_and_live_use_identical_causal_kernel():
    values = []
    start = datetime(2026, 11, 8, 22, tzinfo=timezone.utc)
    for index in range(40):
        value = example("sample")
        value["timestamp"] = (
            (start + timedelta(seconds=2 * index)).isoformat().replace("+00:00", "Z")
        )
        value["metadata"]["sequence"] = index
        value["conteudo"]["readings"]["current_a"] = 4 + index / 10
        event = parse_event_v2(json.dumps(value))
        assert isinstance(event, TelemetrySampleV2)
        values.append(event)
    online = FeatureWindowV2()
    live = [online.push(e) for e in values]
    assert live == list(iter_features_v2(values))
    assert live[-1].status == "valid"
    assert len(live[-1].values) == 18
    assert online.push(values[-1]).status == "ignored"
    off = example("sample")
    off["timestamp"] = (start + timedelta(seconds=80)).isoformat().replace("+00:00", "Z")
    off["metadata"]["sequence"] = 40
    off["conteudo"]["actuators"]["compressor_on"] = False
    event = parse_event_v2(json.dumps(off))
    assert isinstance(event, TelemetrySampleV2)
    assert online.push(event).status == "inactive"
    # Same measured values in v1 feed exactly the same domain kernel.
    old = json.loads((Path(__file__).parents[1] / "fixtures/events.v1.json").read_text())[0][
        "value"
    ]
    kernel = FeatureWindow()
    for v2, expected in zip(values, live):
        old.update(timestamp=v2.timestamp, device_id=v2.dispositivo)
        old["metadata"].update(boot_id=v2.metadata.boot_id, sequence=v2.metadata.sequence)
        old["data"] = v2.conteudo.model_dump()
        assert kernel.push(parse_event(json.dumps(old))) == expected
