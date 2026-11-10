"""Real AMQP inference account -> API consumer -> authenticated WebSocket."""

import json
import time
import urllib.request
from pathlib import Path

import pytest
from websockets.sync.client import connect
from websockets.typing import Origin

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/initial_viewer_password").exists(),
    reason="Requires the running Compose API and actual inference service",
)


def test_actual_inference_frame_reaches_authorized_socket():
    def request(path, body=None, token=None):
        headers = {
            "Content-Type": "application/json",
            "Origin": "http://localhost:8080",
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(
            "http://api:8000/api/v1" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response) if response.status != 204 else None

    token = request(
        "/auth/login",
        {
            "username": "visualizador",
            "password": Path("/run/secrets/initial_viewer_password")
            .read_text()
            .strip(),
        },
    )["access_token"]
    try:
        ticket = request("/auth/ws-ticket", {"devices": ["ac_01"]}, token)["ticket"]
        with connect(
            "ws://api:8000/ws", origin=Origin("http://localhost:8080"), open_timeout=5
        ) as socket:
            socket.send(
                json.dumps(
                    {"type": "authenticate", "ticket": ticket, "devices": ["ac_01"]}
                )
            )
            assert json.loads(socket.recv(timeout=5))["type"] == "authenticated"
            assert json.loads(socket.recv(timeout=5))["type"] == "snapshot"
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                event = json.loads(socket.recv(timeout=5))
                if event.get("type") == "ping":
                    socket.send(json.dumps({"type": "pong", "id": event["id"]}))
                elif event.get("tipo") == "frame.ready":
                    assert event["tipo"] == "frame.ready"
                    assert event["metadata"]["producer"] == "inference"
                    assert (
                        event["conteudo"]["source_event_id"]
                        == event["conteudo"]["telemetry"]["source_event_id"]
                    )
                    assert set(event["conteudo"]["telemetry"]) == {
                        "source_event_id",
                        "readings",
                        "actuators",
                        "quality",
                    }
                    if event["conteudo"]["insight"]["status"] == "valid":
                        assert event["conteudo"]["insight"]["model_version"]
                    break
            else:
                raise AssertionError("No correlated live frame")
    finally:
        request("/auth/logout", {}, token)
