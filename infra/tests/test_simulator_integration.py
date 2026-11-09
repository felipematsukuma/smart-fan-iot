"""Real MQTT device edge; the test gateway fixture commits receipts in PG."""

import queue
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import paho.mqtt.client as mqtt
import pytest
from smartfan_common.contracts_v2 import (
    EVENT_V2_ADAPTER,
    CommandAckV2,
    DeviceStateV2,
    EventV2,
    TelemetrySampleV2,
    serialize_event_v2,
)
from smartfan_common.reliability.amqp import ConfirmedPublisher, connect_amqp
from smartfan_common.reliability.database import engine_for
from smartfan_common.reliability.store import DurableStore, Outbound
from smartfan_common.routing_v2 import parse_mqtt_event_v2, routing_key_v2
from sqlalchemy import text

SECRETS = Path("/run/secrets")
pytestmark = pytest.mark.skipif(
    not (SECRETS / "mqtt_gateway").exists(),
    reason="Requires real MQTT device and scoped test credentials",
)


def test_live_device_command_ack_and_durable_receipt():
    events: queue.Queue[tuple[EventV2, bytes]] = queue.Queue()
    connected = threading.Event()
    client = mqtt.Client(
        client_id="test_gateway_" + uuid4().hex, protocol=mqtt.MQTTv311
    )
    client.username_pw_set("gateway", (SECRETS / "mqtt_gateway").read_text().strip())
    latest_state: DeviceStateV2 | None = None

    def on_connect(c, u, f, rc):
        assert rc == 0
        c.subscribe(
            [
                ("devices/ac_01/telemetry", 1),
                ("devices/ac_01/state", 1),
                ("devices/ac_01/acks", 1),
            ]
        )
        connected.set()

    def on_message(c, u, m):
        events.put((parse_mqtt_event_v2(m.topic, m.payload), m.payload))

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mosquitto", 1883, 15)
    client.loop_start()

    def wait_for(
        predicate: Callable[[EventV2], bool], timeout: float = 15
    ) -> tuple[EventV2, bytes]:
        nonlocal latest_state
        deadline = time.monotonic() + timeout
        while True:
            event, raw = events.get(timeout=max(0.01, deadline - time.monotonic()))
            if isinstance(event, DeviceStateV2) and (
                latest_state is None
                or datetime.fromisoformat(event.timestamp)
                >= datetime.fromisoformat(latest_state.timestamp)
            ):
                latest_state = event
            if predicate(event):
                return event, raw
            if time.monotonic() >= deadline:
                raise AssertionError("No matching live event before deadline")

    def send(boot, revision, fan):
        identity = str(uuid4())
        now = datetime.now(UTC)
        event = EVENT_V2_ADAPTER.validate_python(
            {
                "id": identity,
                "schema_version": "2.0",
                "timestamp": now.isoformat().replace("+00:00", "Z"),
                "tipo": "command.requested",
                "dispositivo": "ac_01",
                "correlation_id": None,
                "metadata": {
                    "producer": "api",
                    "causation_id": None,
                    "zone": "quarto",
                    "equipment_type": "ac_split_onoff",
                },
                "conteudo": {
                    "command_id": identity,
                    "target_boot_id": boot,
                    "revision": revision,
                    "desired": {"compressor_on": False, "condenser_fan_on": fan},
                    "mode": "auto",
                    "expires_at": (now + timedelta(seconds=15))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "reason_code": "integration_probe",
                },
            }
        )
        payload = serialize_event_v2(event)
        client.publish("devices/ac_01/commands", payload, qos=1).wait_for_publish(
            timeout=3
        )
        return identity, payload

    engine = None
    broker = None
    cleanup = None
    try:
        assert connected.wait(5)
        sample, raw = wait_for(
            lambda e: (
                isinstance(e, TelemetrySampleV2)
                and 0
                <= (
                    datetime.now(UTC) - datetime.fromisoformat(e.timestamp)
                ).total_seconds()
                < 6
                and latest_state is not None
                and latest_state.metadata.boot_id == e.metadata.boot_id
                and latest_state.conteudo.last_revision is not None
            )
        )
        # This fixture is not the M04 gateway service. It uses the real M02
        # transaction/outbox so its receipt never invents durable acceptance.
        assert isinstance(sample, TelemetrySampleV2)
        assert (
            latest_state is not None and latest_state.conteudo.last_revision is not None
        )
        engine = engine_for("gateway", SECRETS / "postgres_gateway")
        store = DurableStore(engine, "gateway")
        exchange, key = routing_key_v2(sample)
        store.receive(
            sample.id,
            raw,
            "devices/ac_01/telemetry",
            outgoing=[Outbound(sample.id, raw, exchange, key)],
        )
        broker = connect_amqp("gateway", SECRETS / "rabbit_gateway")
        publisher = ConfirmedPublisher(broker.channel())
        while publisher.publish_one(store):
            pass
        # Gateway can use its own inbox timestamp; writers read the restricted view.
        with engine.connect() as connection:
            observed = connection.execute(
                text(
                    "SELECT observed_at FROM transport.inbox WHERE owner='gateway' AND event_id=:id"
                ),
                {"id": sample.id},
            ).scalar_one()
        receipt = EVENT_V2_ADAPTER.validate_python(
            {
                "id": str(uuid4()),
                "schema_version": "2.0",
                "timestamp": observed.isoformat().replace("+00:00", "Z"),
                "tipo": "transport.received",
                "dispositivo": "ac_01",
                "correlation_id": None,
                "metadata": {
                    "producer": "gateway",
                    "causation_id": sample.id,
                    "boot_id": sample.metadata.boot_id,
                    "sequence": sample.metadata.sequence,
                    "zone": "quarto",
                    "equipment_type": "ac_split_onoff",
                    "clock_scale": 1,
                    "observed_at": observed.isoformat().replace("+00:00", "Z"),
                },
                "conteudo": {
                    "source_event_id": sample.id,
                    "status": "durably_received",
                },
            }
        )
        client.publish(
            "devices/ac_01/receipts", serialize_event_v2(receipt), qos=1
        ).wait_for_publish(timeout=3)
        revision = latest_state.conteudo.last_revision + 1
        command_id, payload = send(sample.metadata.boot_id, revision, True)
        cleanup = (sample.metadata.boot_id, revision + 1)
        result, _ = wait_for(
            lambda e: (
                isinstance(e, CommandAckV2) and e.conteudo.command_id == command_id
            )
        )
        assert isinstance(result, CommandAckV2) and result.tipo == "command.applied"
        assert result.conteudo.observed.condenser_fan_on
        wait_for(
            lambda e: (
                isinstance(e, TelemetrySampleV2)
                and e.metadata.boot_id == sample.metadata.boot_id
                and e.conteudo.actuators.condenser_fan_on
                and e.conteudo.readings.power_w is not None
                and e.conteudo.readings.power_w > 0
            )
        )
        client.publish("devices/ac_01/commands", payload, qos=1).wait_for_publish(
            timeout=3
        )
        repeated, _ = wait_for(
            lambda e: (
                isinstance(e, CommandAckV2) and e.conteudo.command_id == command_id
            )
        )
        assert repeated.id == result.id
    finally:
        if cleanup is not None:
            identity, _ = send(*cleanup, False)
            result, _ = wait_for(
                lambda e: (
                    isinstance(e, CommandAckV2) and e.conteudo.command_id == identity
                )
            )
            assert result.tipo == "command.applied"
        client.disconnect()
        client.loop_stop()
        if broker is not None:
            broker.close()
        if engine is not None:
            engine.dispose()
