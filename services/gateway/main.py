"""MQTT application receipts and confirmed AMQP forwarding, with durable retries."""

import signal
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import pika
from smartfan_common.contracts_v2 import CommandRequestedV2, parse_event_v2
from smartfan_common.reliability.amqp import ConfirmedPublisher, connect_amqp
from smartfan_common.reliability.database import engine_for
from smartfan_common.reliability.runtime import (
    HealthState,
    configure_logging,
    health_server,
)
from smartfan_common.reliability.store import DurableStore, LostLease, QuotaExceeded
from smartfan_common.routing_v2 import mqtt_topic_v2
from sqlalchemy.exc import SQLAlchemyError

from .bridge import GatewayBridge


def main() -> None:
    logger = configure_logging("gateway")
    secrets = Path("/run/secrets")
    engine = engine_for("gateway", secrets / "postgres_gateway")
    store = DurableStore(engine, "gateway")
    bridge = GatewayBridge(store)
    client = mqtt.Client(client_id="gateway", clean_session=False)
    client.username_pw_set("gateway", (secrets / "mqtt_gateway").read_text().strip())
    client.reconnect_delay_set(1, 30)
    client.max_inflight_messages_set(20)
    client.max_queued_messages_set(128)
    connected, stop = threading.Event(), threading.Event()
    database_ready = threading.Event()
    health = HealthState()
    server = health_server(health)

    def on_connect(c: Any, u: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            c.subscribe(
                [
                    (f"devices/+/{suffix}", 1)
                    for suffix in ("telemetry", "state", "availability", "acks")
                ]
            )
            connected.set()

    def on_message(c: Any, u: Any, message: Any) -> None:
        try:
            receipt = bridge.receive_device(message.topic, message.payload)
            database_ready.set()
            if receipt:
                c.publish(receipt[0], receipt[1], qos=1, retain=False)
        except (SQLAlchemyError, QuotaExceeded, ValueError):
            database_ready.clear()
            logger.warning(
                "device_receive_pending", extra={"event": "device_receive_pending"}
            )

    client.on_connect, client.on_message = on_connect, on_message
    client.on_disconnect = lambda *_: connected.clear()
    client.connect_async("mosquitto", 1883, 15)
    client.loop_start()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    connection = None
    try:
        while not stop.is_set():
            try:
                connection = connect_amqp("gateway", secrets / "rabbit_gateway")
                channel = connection.channel()
                channel.basic_qos(prefetch_count=1)
                publisher = ConfirmedPublisher(channel)

                def on_command(
                    ch: Any, method: Any, properties: Any, body: bytes
                ) -> None:
                    bridge.receive_command(body, method.routing_key, properties.user_id)
                    ch.basic_ack(method.delivery_tag)

                channel.basic_consume("q.commands.gateway", on_command, auto_ack=False)
                idle = True
                while not stop.is_set():
                    connection.process_data_events(time_limit=0.1 if idle else 0)
                    active = False
                    for _ in range(32):
                        delivery = store.claim("inbox")
                        if delivery is None:
                            break
                        if delivery is not None:
                            active = True
                            event = parse_event_v2(delivery.payload)
                            if not isinstance(
                                event, CommandRequestedV2
                            ) or bridge.has_result(event.id):
                                store.finish(delivery)
                            elif not bridge.dispatchable(event, datetime.now(UTC)):
                                store.retry(delivery, "command_expired", permanent=True)
                            elif not connected.is_set() or not bridge.ready_for(
                                event, datetime.now(UTC)
                            ):
                                store.retry(delivery, "device_not_ready")
                            else:
                                if not bridge.dispatchable(event, datetime.now(UTC)):
                                    store.retry(
                                        delivery, "command_expired", permanent=True
                                    )
                                    continue
                                # MQTT PUBACK is NOT execution confirmation. The durable
                                # simulator ACK will finish this inbox on the next retry.
                                result = client.publish(
                                    mqtt_topic_v2(event),
                                    delivery.payload,
                                    qos=1,
                                    retain=False,
                                )
                                store.retry(
                                    delivery,
                                    "awaiting_device_ack"
                                    if result.rc == mqtt.MQTT_ERR_SUCCESS
                                    else "mqtt_unavailable",
                                )
                    active = bool(publisher.publish_batch(store, limit=8)) or active
                    idle = not active
                    health.tick(
                        mqtt=connected.is_set(),
                        postgres=database_ready.is_set(),
                        rabbitmq=True,
                    )
            except (
                pika.exceptions.AMQPError,
                OSError,
                SQLAlchemyError,
                QuotaExceeded,
                LostLease,
            ):
                health.tick(mqtt=connected.is_set(), postgres=False, rabbitmq=False)
                logger.warning(
                    "gateway_reconnecting", extra={"event": "gateway_reconnecting"}
                )
                if connection is not None and connection.is_open:
                    connection.close()
                stop.wait(1)
    finally:
        if connection is not None and connection.is_open:
            connection.close()
        client.disconnect()
        client.loop_stop()
        server.shutdown()
        server.server_close()
        engine.dispose()


if __name__ == "__main__":
    main()
