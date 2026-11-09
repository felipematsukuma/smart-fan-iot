"""Real API-account AMQP command -> running gateway -> MQTT -> simulator -> PG ACK."""

import queue
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import paho.mqtt.client as mqtt
import pika
import pytest
from smartfan_common.contracts_v2 import (
    CommandAckV2,
    CommandRequestedV2,
    DeviceStateV2,
    EventV2,
    TelemetrySampleV2,
    parse_event_v2,
    serialize_event_v2,
)
from smartfan_common.reliability.amqp import connect_amqp
from smartfan_common.reliability.database import engine_for
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not Path("/run/secrets/rabbit_api").exists(),
    reason="Requires running Docker gateway and scoped test credentials",
)


def test_running_gateway_round_trip_and_duplicate():
    secrets = Path("/run/secrets")
    received: queue.Queue[EventV2] = queue.Queue()
    connected = threading.Event()
    client = mqtt.Client(client_id="test_observer_" + uuid4().hex)
    client.username_pw_set("gateway", (secrets / "mqtt_gateway").read_text().strip())

    def on_connect(c, u, f, rc):
        assert rc == 0
        c.subscribe(
            [
                ("devices/ac_01/state", 1),
                ("devices/ac_01/acks", 1),
                ("devices/ac_01/telemetry", 1),
            ]
        )
        connected.set()

    client.on_connect = on_connect
    client.on_message = lambda c, u, m: received.put(parse_event_v2(m.payload))
    client.connect("mosquitto", 1883, 15)
    client.loop_start()
    broker = connect_amqp("api", secrets / "rabbit_api")
    channel = broker.channel()
    channel.confirm_delivery()
    engine = engine_for("gateway", secrets / "postgres_gateway")
    state = None

    def wait_for(predicate):
        nonlocal state
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            event = received.get(timeout=max(0.01, deadline - time.monotonic()))
            if isinstance(event, DeviceStateV2):
                state = event
            if predicate(event):
                return event
        raise AssertionError("No expected device event")

    def send(revision, fan):
        now = datetime.now(UTC)
        identity = str(uuid4())
        assert state is not None
        event = CommandRequestedV2.model_validate(
            {
                "id": identity,
                "schema_version": "2.0",
                "timestamp": now.isoformat().replace("+00:00", "Z"),
                "tipo": "command.requested",
                "dispositivo": "ac_01",
                "correlation_id": identity,
                "metadata": {
                    "producer": "api",
                    "causation_id": None,
                    "zone": "quarto",
                    "equipment_type": "ac_split_onoff",
                },
                "conteudo": {
                    "command_id": identity,
                    "target_boot_id": state.metadata.boot_id,
                    "revision": revision,
                    "desired": {"compressor_on": False, "condenser_fan_on": fan},
                    "mode": "auto",
                    "expires_at": (now + timedelta(seconds=15))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "reason_code": "gateway_probe",
                },
            }
        )
        raw = serialize_event_v2(event)
        publish(raw, identity)
        return identity, raw

    def publish(raw, identity):
        channel.basic_publish(
            "smartfan.events",
            "command.ac_01",
            raw,
            mandatory=True,
            properties=pika.BasicProperties(
                user_id="api",
                message_id=identity,
                delivery_mode=2,
                content_type="application/json",
            ),
        )

    cleanup_revision = None
    try:
        assert connected.wait(5)
        wait_for(lambda e: isinstance(e, TelemetrySampleV2) and state is not None)
        assert state is not None and state.conteudo.last_revision is not None
        revision = state.conteudo.last_revision + 1
        identity, raw = send(revision, True)
        cleanup_revision = revision + 1
        ack = wait_for(
            lambda e: isinstance(e, CommandAckV2) and e.conteudo.command_id == identity
        )
        assert ack.tipo == "command.applied"
        wait_for(
            lambda e: (
                isinstance(e, TelemetrySampleV2)
                and e.conteudo.actuators.condenser_fan_on
            )
        )
        publish(raw, identity)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with engine.connect() as conn:
                row = conn.execute(
                    text(
                        "SELECT i.state,r.ack_event_id FROM transport.inbox i JOIN transport.command_results r ON r.command_id=i.event_id WHERE i.owner='gateway' AND i.event_id=:id"
                    ),
                    {"id": identity},
                ).first()
            if row and row[0] == "completed":
                assert str(row[1]) == ack.id
                break
            time.sleep(0.2)
        else:
            raise AssertionError("Physical ACK not durably completed")
    finally:
        if cleanup_revision is not None:
            identity, _ = send(cleanup_revision, False)
            wait_for(
                lambda e: (
                    isinstance(e, CommandAckV2) and e.conteudo.command_id == identity
                )
            )
        client.disconnect()
        client.loop_stop()
        broker.close()
        engine.dispose()
