import json
import logging
import time
import urllib.error
import urllib.request

import pytest

from smartfan_common.reliability.runtime import HealthState, JsonFormatter, health_server
from smartfan_common.reliability.store import backoff_seconds


def test_backoff_is_bounded_and_jitter_is_validated():
    assert [backoff_seconds(i) for i in range(1, 7)] == [1, 5, 30, 30, 30, 30]
    assert backoff_seconds(3, -0.2) == 24
    assert backoff_seconds(3, 0.2) == 36
    for attempt, jitter in [(0, 0), (1, 0.3), (1, float("nan"))]:
        with pytest.raises(ValueError):
            backoff_seconds(attempt, jitter)


def test_json_log_does_not_emit_freeform_exception_or_secret_fields():
    record = logging.LogRecord("writer", logging.ERROR, "test", 1, "sensitive-message", (), None)
    record.event = "retry"
    record.correlation_id = "trace-id"
    record.password = "sensitive-password"
    record.reason_code = {"unexpected": "sensitive-value"}
    value = JsonFormatter().format(record)
    assert "sensitive" not in value
    assert json.loads(value)["correlation_id"] == "trace-id"


def test_health_is_distinct_from_dependency_readiness():
    state = HealthState()
    assert state.snapshot()[0] == 200
    assert state.snapshot(True)[0] == 503
    state.tick(postgres=False)
    assert state.snapshot()[0] == 200
    assert state.snapshot(True)[0] == 503
    state.tick(postgres=True)
    assert state.snapshot(True)[0] == 200
    expired = HealthState(max_age_seconds=0.001)
    time.sleep(0.005)
    assert expired.snapshot()[0] == 503


def test_real_health_server_reports_only_bounded_public_state():
    state = HealthState()
    server = health_server(state, host="127.0.0.1", port=0)
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(base + "/health", timeout=2) as response:
            assert json.load(response)["live"]
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + "/ready", timeout=2)
        assert error.value.code == 503
        state.tick(postgres=True)
        with urllib.request.urlopen(base + "/ready", timeout=2) as response:
            assert json.load(response)["ready"]
    finally:
        server.shutdown()
        server.server_close()
