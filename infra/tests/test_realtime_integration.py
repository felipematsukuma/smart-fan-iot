"""Real PostgreSQL snapshots and ASGI WebSockets with scoped one-use tickets."""
# ruff: noqa: F811

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.contracts_v2 import (
    FrameReadyV2,
    TelemetrySampleV2,
    parse_event_v2,
    serialize_event_v2,
)
from smartfan_common.reliability.origins import record_origin
from smartfan_common.reliability.store import DurableStore
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect
from test_api_integration import api, headers, login  # noqa: F401
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

from services.simulator.device import SimulatorDevice
from services.simulator.physics import PlantConfig

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated real PostgreSQL",
)


@pytest.fixture
def stream(api, database, tmp_path):
    client, auth, _, _ = api
    admin, engines = database
    device = SimulatorDevice(tmp_path / "stream.sqlite3", PlantConfig())
    now = datetime.now(UTC)
    raw = device.sample(now)
    sample = parse_event_v2(raw)
    assert isinstance(sample, TelemetrySampleV2)
    gateway = DurableStore(engines["gateway"], "gateway")
    with gateway.transaction() as conn:
        gateway.receive(sample.id, raw, "devices/ac_01/telemetry", connection=conn)
        record_origin(conn, sample)
    observed = gateway.received_at(sample.id)
    with admin.begin() as conn:
        conn.execute(text("TRUNCATE app.event_snapshots"))
        conn.execute(
            text(
                "INSERT INTO transport.device_presence(device_id,zone,boot_id,boot_seen_at,last_sample_at) VALUES(:id,:zone,:boot,:time,:time)"
            ),
            {"id": "ac_01", "zone": "quarto", "boot": device.boot_id, "time": now},
        )
    data = sample.model_dump()
    data.update(id=str(uuid4()), tipo="frame.ready")
    assert observed is not None
    data["metadata"].update(
        producer="inference", observed_at=observed.isoformat().replace("+00:00", "Z")
    )
    telemetry = data["conteudo"]
    telemetry["source_event_id"] = sample.id
    data["conteudo"] = {
        "source_event_id": sample.id,
        "telemetry": telemetry,
        "insight": {
            "status": "model_unavailable",
            "model_version": None,
            "feature_version": "hvac-window-v1",
            "health_score": None,
            "rul_calendar_hours": None,
        },
    }
    frame = FrameReadyV2.model_validate(data)
    token = login(api, "visualizador")
    yield client, auth, frame, token, observed
    device.close()


def ticket(client, token):
    response = client.post(
        "/api/v1/auth/ws-ticket",
        headers={**headers(token), "Origin": "http://localhost:8080"},
        json={"devices": ["ac_01"]},
    )
    assert response.status_code == 200
    return response.json()["ticket"]


def test_snapshot_origin_deduplication_and_observation_provenance(stream):
    client, _, frame, token, _ = stream
    events = client.app.state.events
    raw = serialize_event_v2(frame)
    assert events.receive(raw, "frame.ac_01", "api", frame.id) == (None, False)
    accepted, backlog = events.receive(raw, "frame.ac_01", "inference", frame.id)
    assert accepted is not None and not backlog
    assert events.receive(raw, "frame.ac_01", "inference", frame.id) == (None, False)
    retimed = frame.model_dump()
    retimed["id"] = str(uuid4())
    retimed["timestamp"] = retimed["metadata"]["observed_at"]
    retimed_event = FrameReadyV2.model_validate(retimed)
    assert events.receive(
        serialize_event_v2(retimed_event), "frame.ac_01", "inference", retimed_event.id
    ) == (None, False)
    altered = frame.model_dump()
    altered["id"] = str(uuid4())
    altered["conteudo"]["telemetry"]["readings"]["power_w"] = 123.0
    altered_event = FrameReadyV2.model_validate(altered)
    assert events.receive(
        serialize_event_v2(altered_event), "frame.ac_01", "inference", altered_event.id
    ) == (None, False)
    snapshot = client.get("/api/v1/snapshot", headers=headers(token)).json()
    assert len(snapshot["events"]) == 1 and snapshot["events"][0]["id"] == frame.id
    assert (
        client.get("/api/v1/snapshot?device=other", headers=headers(token)).status_code
        == 403
    )
    changed = frame.model_dump()
    changed["id"] = str(uuid4())
    changed["metadata"]["observed_at"] = (
        (datetime.now(UTC) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    )
    forged = FrameReadyV2.model_validate(changed)
    assert events.receive(
        serialize_event_v2(forged), "frame.ac_01", "inference", forged.id
    ) == (None, False)


def test_ticket_second_use_and_forbidden_subscription(stream):
    client, _, _, token, _ = stream
    opaque = ticket(client, token)
    with client.websocket_connect(
        "/ws", headers={"origin": "http://localhost:8080"}
    ) as socket:
        socket.send_json(
            {"type": "authenticate", "ticket": opaque, "devices": ["ac_01"]}
        )
        assert socket.receive_json()["type"] == "authenticated"
        assert socket.receive_json()["type"] == "snapshot"
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                "/ws", headers={"origin": "http://localhost:8080"}
            ) as second,
        ):
            second.send_json(
                {"type": "authenticate", "ticket": opaque, "devices": ["ac_01"]}
            )
            second.receive_json()
        socket.send_json({"type": "subscribe", "devices": ["other"]})
        with pytest.raises(WebSocketDisconnect):
            while True:
                packet = socket.receive_json()
                if packet.get("type") == "ping":
                    socket.send_json({"type": "pong", "id": packet["id"]})


def test_logout_closes_socket_and_query_auth_is_rejected(stream):
    client, _, _, token, _ = stream
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "/ws?token=forbidden", headers={"origin": "http://localhost:8080"}
        ),
    ):
        pass
    opaque = ticket(client, token)
    with client.websocket_connect(
        "/ws", headers={"origin": "http://localhost:8080"}
    ) as socket:
        socket.send_json({"type": "authenticate", "ticket": opaque})
        assert socket.receive_json()["type"] == "authenticated"
        socket.receive_json()
        client.post("/api/v1/auth/logout", headers=headers(token))
        with pytest.raises(WebSocketDisconnect):
            while True:
                packet = socket.receive_json()
                if packet.get("type") == "ping":
                    socket.send_json({"type": "pong", "id": packet["id"]})
