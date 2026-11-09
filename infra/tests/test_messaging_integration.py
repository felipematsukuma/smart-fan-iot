"""Failure previews never expose source bodies; replay preserves original writer identity."""
# ruff: noqa: F811

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import parse_event_v2
from smartfan_common.reliability.store import DurableStore, LostLease
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text
from test_api_integration import api, headers, login  # noqa:F401
from test_reliability_integration import database, reset_disposable_rows  # noqa:F401
from test_writer_integration import influx  # noqa:F401

from services.simulator.device import SimulatorDevice
from services.simulator.physics import PlantConfig
from services.writer.worker import Writer

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires real isolated PG and InfluxDB",
)


def test_failure_preview_is_allowlisted_and_all_messaging_routes_are_admin_only(
    api, database
):
    client, _, _, _ = api
    _, engines = database
    private = secrets.token_urlsafe(24)
    store = DurableStore(engines["writer"], "writer")
    store.quarantine(
        json.dumps(
            {"password": private, "token": private, "conteudo": private}
        ).encode(),
        "invalid." + private,
        "invalid_telemetry_origin",
    )
    for name in ["operador", "visualizador"]:
        token = login(api, name)
        assert (
            client.get("/api/v1/messaging", headers=headers(token)).status_code == 403
        )
        assert (
            client.get("/api/v1/messaging/failures", headers=headers(token)).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/messaging/failures/" + str(uuid4()) + "/replay",
                headers=headers(token),
                json={"request_id": str(uuid4())},
            ).status_code
            == 403
        )
    token = login(api)
    response = client.get("/api/v1/messaging/failures", headers=headers(token))
    assert response.status_code == 200 and private not in response.text
    item = response.json()["items"][0]
    assert item["preview"] == {} and item["can_replay"] is False
    assert not {"payload", "original_bytes_b64", "route", "sha256"} & item.keys()
    assert (
        client.post(
            "/api/v1/messaging/failures/" + item["id"] + "/replay",
            headers=headers(token),
            json={"request_id": str(uuid4())},
        ).status_code
        == 409
    )


def test_valid_writer_replay_is_fenced_idempotent_audited_and_does_not_duplicate_point(
    api, database, influx, tmp_path, monkeypatch
):
    client, _, _, _ = api
    admin, engines = database
    device = SimulatorDevice(tmp_path / "replay.sqlite3", PlantConfig())
    raw = device.sample(datetime.now(UTC))
    event = parse_event_v2(raw)
    DurableStore(engines["gateway"], "gateway").receive(
        event.id, raw, "devices/ac_01/telemetry"
    )
    store = DurableStore(engines["writer"], "writer")
    worker = Writer(store, influx)
    assert worker.receive(raw, routing_key_v2(event)[1], "gateway", event.id)
    delivery = store.claim()
    assert delivery is not None
    original_finish = store.finish

    def interrupted(*args, **kwargs):
        raise RuntimeError("Interrupted after Influx write, before SQL completion")

    monkeypatch.setattr(store, "finish", interrupted)
    with pytest.raises(RuntimeError):
        worker.process(delivery)
    monkeypatch.setattr(store, "finish", original_finish)
    store.retry(delivery, "influx_rejected_point", permanent=True)
    token = login(api)
    item = client.get("/api/v1/messaging/failures", headers=headers(token)).json()[
        "items"
    ][0]
    assert item["can_replay"] is True
    request = str(uuid4())
    path = "/api/v1/messaging/failures/" + item["id"] + "/replay"
    first = client.post(path, headers=headers(token), json={"request_id": request})
    assert first.status_code == 202 and first.json()["status"] == "requested"
    assert (
        client.post(path, headers=headers(token), json={"request_id": request}).json()[
            "status"
        ]
        == "already_requested"
    )
    assert (
        client.post(
            path, headers=headers(token), json={"request_id": str(uuid4())}
        ).status_code
        == 409
    )
    repeated = store.claim()
    assert repeated is not None
    assert (
        repeated.payload == raw
        and repeated.event_id == event.id
        and repeated.generation > delivery.generation
    )
    with pytest.raises(LostLease):
        store.finish(delivery)
    worker.process(repeated)
    assert store.counts() == {"completed": 1}
    counts = influx.query(
        f'from(bucket:{json.dumps(influx.bucket)}) |> range(start:-1h) |> filter(fn:(r)=>r._measurement=="hvac_telemetry" and r._field=="event_id") |> count()'
    )
    assert sum(int(row["_value"]) for row in counts) == 1
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM transport.influx_points")
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM app.audit WHERE action='failure.replay_requested'"
                )
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(text("SELECT count(*) FROM transport.failures")).scalar_one()
            == 1
        )
    with engines["api"].begin() as conn:
        changed = conn.execute(
            text("UPDATE transport.inbox SET state='pending' WHERE owner='writer'")
        )
        assert (
            changed.rowcount == 0
        )  # RLS hides other services' rows rather than raising.
    device.close()


def test_function_cannot_replay_command_or_unjournaled_data(api, database):
    client, _, _, _ = api
    admin, engines = database
    store = DurableStore(engines["writer"], "writer")
    raw = json.dumps(
        {
            "id": str(uuid4()),
            "tipo": "command.requested",
            "metadata": {"producer": "api"},
        }
    ).encode()
    identity = json.loads(raw)["id"]
    store.receive(identity, raw, "command.ac_01")
    claimed = store.claim()
    assert claimed is not None
    store.retry(claimed, "attempts_exhausted", permanent=True)
    token = login(api)
    item = client.get("/api/v1/messaging/failures", headers=headers(token)).json()[
        "items"
    ][0]
    assert (
        client.post(
            "/api/v1/messaging/failures/" + item["id"] + "/replay",
            headers=headers(token),
            json={"request_id": str(uuid4())},
        ).status_code
        == 409
    )
    with admin.connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM transport.inbox WHERE owner='writer' AND state='failed'"
                )
            ).scalar_one()
            == 1
        )


def test_monitor_account_reads_real_queue_counts_but_cannot_get_dlq():
    if not Path("/run/secrets/rabbit_api-monitor").exists():
        pytest.skip("Scoped monitor mount required")
    import base64
    import urllib.error
    import urllib.request

    from services.api.messaging import Management

    monitor = Management(Path("/run/secrets/rabbit_api-monitor"))
    result = monitor.snapshot()
    assert len(result["queues"]) == 8 and result["source"] == "rabbitmq_management"
    assert monitor.snapshot() == result
    credential = Path("/run/secrets/rabbit_api-monitor").read_text().strip()
    request = urllib.request.Request(
        "http://rabbitmq:15672/api/queues/%2Fsmartfan/q.dlq/get",
        method="POST",
        headers={
            "Authorization": "Basic "
            + base64.b64encode(("api-monitor:" + credential).encode()).decode(),
            "Content-Type": "application/json",
        },
        data=b'{"count":1,"ackmode":"ack_requeue_true","encoding":"auto"}',
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request, timeout=3)
    assert error.value.code in (401, 403)
