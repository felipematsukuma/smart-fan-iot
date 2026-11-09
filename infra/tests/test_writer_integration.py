"""Real InfluxDB in a disposable bucket and PG in a disposable database."""
# ruff: noqa: F811

import json
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import (
    TelemetrySampleV2,
    parse_event_v2,
    serialize_event_v2,
)
from smartfan_common.influx_v2 import InfluxHTTP
from smartfan_common.reliability.store import DurableStore, LostLease
from sqlalchemy import text
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

from services.simulator.device import SimulatorDevice
from services.simulator.physics import PlantConfig
from services.writer.worker import PointCollision, Writer

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/influx_admin_token").exists(),
    reason="Requires real isolated Docker integration services",
)


@pytest.fixture(scope="module")
def influx():
    headers = {
        "Authorization": "Token "
        + Path("/run/secrets/influx_admin_token").read_text().strip(),
        "Content-Type": "application/json",
    }

    def request(path, method="GET", body=None):
        req = urllib.request.Request(
            "http://influxdb:8086/api/v2/" + path,
            method=method,
            headers=headers,
            data=json.dumps(body).encode() if body else None,
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response) if response.status != 204 else None

    org = request("orgs?org=smartfan")["orgs"][0]["id"]
    name = "test_writer_" + uuid4().hex
    bucket = request(
        "buckets",
        "POST",
        {
            "orgID": org,
            "name": name,
            "retentionRules": [{"type": "expire", "everySeconds": 86400}],
        },
    )
    client = InfluxHTTP(Path("/run/secrets/influx_admin_token"), bucket=name)
    try:
        yield client
    finally:
        request("buckets/" + bucket["id"], "DELETE")


def accept(engines, worker, event):
    raw = serialize_event_v2(event)
    DurableStore(engines["gateway"], "gateway").receive(
        event.id, raw, f"devices/{event.dispositivo}/telemetry"
    )
    assert worker.receive(
        raw,
        f"telemetry.{event.metadata.zone}.hvac.{event.dispositivo}",
        "gateway",
        event.id,
    )
    delivery = worker.store.claim("inbox")
    assert delivery is not None
    return delivery


def test_crash_after_influx_before_pg_replays_one_point(database, influx, tmp_path):
    admin, engines = database
    store = DurableStore(engines["writer"], "writer")
    worker = Writer(store, influx)
    device = SimulatorDevice(tmp_path / "device.sqlite3", PlantConfig())
    try:
        now = datetime.now(UTC)
        event = parse_event_v2(device.sample(now))
        delivery = accept(engines, worker, event)
        real_write = influx.write

        def cut_after_write(lines, bucket=None):
            real_write(lines, bucket)
            with admin.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE transport.inbox SET leased_until=clock_timestamp()-interval '1 second' WHERE owner='writer'"
                    )
                )

        influx.write = cut_after_write
        with pytest.raises(LostLease):
            worker.process(delivery)
        assert store.pending_outbox() == []
        influx.write = real_write
        replay = store.claim("inbox")
        assert replay is not None
        worker.process(replay)
        assert len(store.pending_outbox()) == 1
        points = influx.query(
            influx.history_query("ac_01", now, now + timedelta(microseconds=1))
        )
        assert len(points) == 1 and points[0]["event_id"] == event.id
        raw = serialize_event_v2(event)
        assert worker.receive(raw, "telemetry.quarto.hvac.ac_01", None, event.id)
        assert store.claim("inbox") is None
    finally:
        influx.write = real_write
        device.close()


def test_collision_preserves_original_and_missing_is_absent(database, influx, tmp_path):
    _, engines = database
    store = DurableStore(engines["writer"], "writer")
    worker = Writer(store, influx)
    device = SimulatorDevice(tmp_path / "device.sqlite3", PlantConfig())
    try:
        now = datetime.now(UTC)
        original = parse_event_v2(device.sample(now)).model_dump()
        original["conteudo"]["readings"]["current_a"] = None
        original["conteudo"]["quality"]["missing_fields"] = ["current_a"]
        event = TelemetrySampleV2.model_validate(original)
        worker.process(accept(engines, worker, event))
        collision = event.model_dump()
        collision["id"] = str(uuid4())
        collision["conteudo"]["readings"]["current_a"] = 50.0
        collision["conteudo"]["quality"]["missing_fields"] = []
        delivery = accept(engines, worker, TelemetrySampleV2.model_validate(collision))
        with pytest.raises(PointCollision):
            worker.process(delivery)
        store.retry(delivery, "point_collision", permanent=True)
        points = influx.query(
            influx.history_query("ac_01", now, now + timedelta(microseconds=1))
        )
        assert len(points) == 1 and points[0]["event_id"] == event.id
        assert (
            not points[0].get("current_a")
            and points[0]["missing_fields"] == "current_a"
        )
    finally:
        device.close()


def test_no_matching_gateway_hash_and_scoped_token(database):
    _, engines = database
    worker = Writer(
        DurableStore(engines["writer"], "writer"),
        InfluxHTTP(Path("/run/secrets/influx_admin_token")),
    )
    assert not worker.receive(
        b"{}", "telemetry.quarto.hvac.ac_01", "gateway", str(uuid4())
    )
    scoped = InfluxHTTP(Path("/credentials/writer/token"))
    with pytest.raises(urllib.error.HTTPError) as error:
        scoped.query('from(bucket:"live") |> range(start:-1m) |> limit(n:1)')
    assert error.value.code in (401, 403, 404)
    with pytest.raises(urllib.error.HTTPError) as error:
        scoped.write(
            b"test value=1.0 " + str(int(datetime.now(UTC).timestamp() * 1e9)).encode(),
            bucket="lab",
        )
    assert error.value.code in (401, 403, 404)


def test_dependency_retries_never_discard_valid_accepted_payload(database):
    admin, engines = database
    store = DurableStore(engines["writer"], "writer")
    identity = str(uuid4())
    store.receive(identity, b"accepted-payload", "test")
    for _ in range(7):
        delivery = store.claim("inbox")
        assert delivery is not None
        store.retry(delivery, "influx_unavailable", dependency_failure=True)
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE transport.inbox SET available_at=clock_timestamp() WHERE owner='writer'"
                )
            )
    assert store.counts().get("pending") == 1


def test_real_history_pagination_and_chart(database, influx, tmp_path):
    _, engines = database
    worker = Writer(DurableStore(engines["writer"], "writer"), influx)
    device = SimulatorDevice(
        tmp_path / "history.sqlite3", PlantConfig(), device_id="ac_history"
    )
    now = datetime.now(UTC)
    try:
        ids = []
        for offset in (-10, -5, 0):
            event = parse_event_v2(device.sample(now + timedelta(seconds=offset)))
            ids.append(event.id)
            worker.process(accept(engines, worker, event))
        begin, end = now - timedelta(seconds=11), now + timedelta(seconds=1)
        first = influx.query(influx.history_query("ac_history", begin, end, 2))
        assert [point["event_id"] for point in first] == ids[:2]
        last = first[-1]
        cursor = (
            datetime.fromisoformat(last["_time"]),
            last["zone"],
            last["equipment_type"],
        )
        second = influx.query(
            influx.history_query("ac_history", begin, end, 2, after=cursor)
        )
        assert [point["event_id"] for point in second] == ids[2:]
        chart = influx.query(influx.chart_query("ac_history", begin, end, 10))
        assert 1 <= len(chart) <= 10 and "current_a" in chart[0]
    finally:
        device.close()


def test_flux_energy_preserves_missing_boot_and_gap_boundaries(
    database, influx, tmp_path
):
    _, engines = database
    worker = Writer(DurableStore(engines["writer"], "writer"), influx)
    device = SimulatorDevice(
        tmp_path / "energy.sqlite3", PlantConfig(), device_id="ac_energy"
    )
    base = datetime.now(UTC) - timedelta(seconds=60)
    try:
        for index, offset in enumerate((0, 2, 4, 6, 8, 20)):
            data = parse_event_v2(
                device.sample(base + timedelta(seconds=offset))
            ).model_dump()
            data["conteudo"]["readings"]["power_w"] = None if index == 2 else 1000.0
            if index >= 4:
                data["metadata"]["boot_id"] = "22222222-2222-4222-8222-222222222222"
            worker.process(
                accept(engines, worker, TelemetrySampleV2.model_validate(data))
            )
        summary = influx.query(
            influx.energy_query(
                "ac_energy", base - timedelta(seconds=1), base + timedelta(seconds=21)
            )
        )
        assert len(summary) == 1
        assert float(summary[0]["energy_wh"]) == pytest.approx(1000 * 2 / 3600)
        assert int(summary[0]["missing_samples"]) == 1
        assert float(summary[0]["covered_seconds"]) == 2
        assert int(summary[0]["discarded_intervals"]) == 2
    finally:
        device.close()
