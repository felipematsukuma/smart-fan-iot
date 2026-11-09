"""Registry metadata, grants, revisions and disabled-scope behavior on real PG."""
# ruff: noqa: F811

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from smartfan_common.reliability.store import DurableStore
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from starlette.websockets import WebSocketDisconnect
from test_api_integration import api, headers, login  # noqa: F401
from test_gateway_integration import command_for
from test_reliability_integration import database, reset_disposable_rows  # noqa: F401

from services.gateway.bridge import GatewayBridge
from services.simulator.device import SimulatorDevice
from services.simulator.physics import PlantConfig

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/postgres_bootstrap").exists(),
    reason="Requires isolated real PostgreSQL",
)


def new_device(client, token):
    identity = "ac_" + uuid4().hex[:12]
    response = client.post(
        "/api/v1/devices",
        headers=headers(token),
        json={"id": identity, "name": "Split de teste", "zone": "sala"},
    )
    assert response.status_code == 201
    return response.json()


def test_registry_roles_identity_units_pagination_and_duplicate(api, database):
    client, _, _, _ = api
    admin = login(api)
    device = new_device(client, admin)
    assert device["boot_id"] is None and device["last_sample_at"] is None
    assert len(device["sensor_ids"]) == 5 and len(device["actuator_ids"]) == 2
    assert device["sensor_units"]["vibration_rms_mm_s"] == "mm/s"
    assert all(
        identity.startswith(device["id"] + "_")
        for identity in device["sensor_ids"].values()
    )
    assert (
        client.post(
            "/api/v1/devices",
            headers=headers(admin),
            json={"id": device["id"], "name": "Duplicate", "zone": "sala"},
        ).status_code
        == 409
    )
    for name in ["operador", "visualizador"]:
        token = login(api, name)
        assert (
            client.get(
                "/api/v1/devices/" + device["id"], headers=headers(token)
            ).status_code
            == 200
        )
        assert (
            client.patch(
                "/api/v1/devices/" + device["id"],
                headers=headers(token),
                json={"expected_revision": 1, "enabled": False},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/devices",
                headers=headers(token),
                json={"id": "forbidden", "name": "Denied", "zone": "sala"},
            ).status_code
            == 403
        )
    first = client.get("/api/v1/devices?limit=1", headers=headers(admin)).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = client.get(
        "/api/v1/devices?limit=1&after=" + first["next_cursor"], headers=headers(admin)
    ).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert (
        client.delete(
            "/api/v1/devices/" + device["id"], headers=headers(admin)
        ).status_code
        == 405
    )
    _, engines = database
    with pytest.raises(DBAPIError), engines["api"].begin() as conn:
        conn.execute(text("DELETE FROM app.devices WHERE id=:id"), {"id": device["id"]})


def test_configuration_versions_conflicts_immutable_identity_and_validation(
    api, database
):
    client, _, _, _ = api
    token = login(api)
    device = new_device(client, token)
    path = "/api/v1/devices/" + device["id"]
    invalid_changes: list[dict[str, object]] = [
        {"zone": "elsewhere"},
        {"id": "changed"},
        {"expected_revision": True, "name": "No"},
        {"profile": {"healthy_ranges": {"current_a": {"minimum": 5, "maximum": 1}}}},
        {"profile": {"healthy_ranges": {"current_a": {"minimum": -1, "maximum": 12}}}},
    ]
    for changes in invalid_changes:
        assert (
            client.patch(
                path, headers=headers(token), json={"expected_revision": 1, **changes}
            ).status_code
            == 422
        )
    updated = client.patch(
        path,
        headers=headers(token),
        json={
            "expected_revision": 1,
            "name": "Renamed",
            "profile": {**device["profile"], "expected_life_hours": 40000},
        },
    )
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert updated.json()["sensor_ids"] == device["sensor_ids"]
    assert (
        client.patch(
            path,
            headers=headers(token),
            json={"expected_revision": 1, "enabled": False},
        ).status_code
        == 409
    )
    _, engines = database
    with engines["api"].connect() as conn:
        rows = conn.execute(
            text(
                "SELECT revision,configuration FROM app.device_configurations WHERE device_id=:id ORDER BY revision"
            ),
            {"id": device["id"]},
        ).all()
        assert (
            len(rows) == 2
            and rows[0][1]["expected_life_hours"] == 30000
            and rows[1][1]["expected_life_hours"] == 40000
        )
    with pytest.raises(DBAPIError), engines["api"].begin() as conn:
        conn.execute(
            text("UPDATE app.device_configurations SET configuration=configuration")
        )


def test_concurrent_updates_have_one_winner_and_no_lost_configuration(api):
    client, _, _, _ = api
    token = login(api)
    device = new_device(client, token)
    path = "/api/v1/devices/" + device["id"]

    def update(name):
        return client.patch(
            path, headers=headers(token), json={"expected_revision": 1, "name": name}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(update, ["First", "Second"]))
    assert sorted(statuses) == [200, 409]
    versions = client.get(
        path + "/configurations?limit=1", headers=headers(token)
    ).json()
    assert versions["items"][0]["revision"] == 2 and versions["next_cursor"] == 2
    previous = client.get(
        path + "/configurations?before=2", headers=headers(token)
    ).json()
    assert previous["items"][0]["revision"] == 1


def test_disabled_metadata_blocks_new_commands_and_live_but_preserves_history(
    api, database, tmp_path
):
    client, _, _, _ = api
    token = login(api)
    admin, engines = database
    device = SimulatorDevice(tmp_path / "registered.sqlite3", PlantConfig())
    bridge = GatewayBridge(DurableStore(engines["gateway"], "gateway"))
    now = datetime.now(UTC)
    assert (
        bridge.receive_device("devices/ac_01/telemetry", device.sample(now)) is not None
    )
    original = client.get("/api/v1/devices/ac_01", headers=headers(token)).json()
    ticket = client.post(
        "/api/v1/auth/ws-ticket",
        headers={**headers(token), "Origin": "http://localhost:8080"},
        json={"devices": ["ac_01"]},
    ).json()["ticket"]
    try:
        with client.websocket_connect(
            "/ws", headers={"Origin": "http://localhost:8080"}
        ) as socket:
            socket.send_json(
                {"type": "authenticate", "ticket": ticket, "devices": ["ac_01"]}
            )
            assert socket.receive_json()["type"] == "authenticated"
            socket.receive_json()
            response = client.patch(
                "/api/v1/devices/ac_01",
                headers=headers(token),
                json={"expected_revision": original["revision"], "enabled": False},
            )
            assert response.status_code == 200
            assert (
                client.post(
                    "/api/v1/auth/ws-ticket",
                    headers={**headers(token), "Origin": "http://localhost:8080"},
                    json={"devices": ["ac_01"]},
                ).status_code
                == 403
            )
            assert (
                client.get(
                    "/api/v1/snapshot?device=ac_01", headers=headers(token)
                ).status_code
                == 403
            )
            command = command_for(device, now)
            assert not bridge.receive_command(
                command.model_dump_json().encode(), "command.ac_01", "api"
            )
            assert not bridge.ready_for(command, now)
            # Disabled registration does not cause a permanent simulator spool loop.
            assert (
                bridge.receive_device("devices/ac_01/telemetry", device.sample(now))
                is not None
            )

            class Historical:
                def chart_query(self, *args):
                    return "chart"

                def energy_query(self, *args):
                    return "energy"

                def query(self, kind):
                    return []

            client.app.state.influx = Historical()
            assert (
                client.get(
                    "/api/v1/devices/ac_01/metrics", headers=headers(token)
                ).status_code
                == 200
            )
            with pytest.raises(WebSocketDisconnect):
                while True:
                    event = socket.receive_json()
                    if event.get("type") == "ping":
                        socket.send_json({"type": "pong", "id": event["id"]})
    finally:
        with admin.begin() as conn:
            conn.execute(text("UPDATE app.devices SET enabled=true WHERE id='ac_01'"))
