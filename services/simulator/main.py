"""Live software device with bounded MQTT retries and a durable application spool."""

import os
import signal
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from smartfan_common.contracts_v2 import (
    CommandAckV2,
    CommandRequestedV2,
    TransportReceiptV2,
    parse_event_v2,
)
from smartfan_common.reliability.runtime import (
    HealthState,
    configure_logging,
    health_server,
)
from smartfan_common.routing_v2 import parse_mqtt_event_v2

from .device import SimulatorDevice, SpoolFull
from .physics import PlantConfig


def utc_now() -> datetime:
    return datetime.now(UTC)


def main() -> None:
    logger = configure_logging("simulator")
    config = PlantConfig.model_validate(
        {
            "scenario": os.environ.get("SIM_SCENARIO", "healthy"),
            "initial_damage": float(os.environ.get("SIM_INITIAL_DAMAGE", "0")),
            "damage_per_operating_hour": float(
                os.environ.get("SIM_DAMAGE_RATE", "0.00005")
            ),
        }
    )
    device_id = os.environ.get("SIM_DEVICE_ID", "ac_01")
    device = SimulatorDevice(
        Path(os.environ.get("SIM_SPOOL", "/data/device.sqlite3")), config, device_id
    )
    client = mqtt.Client(
        client_id="simulator_" + device_id, clean_session=False, protocol=mqtt.MQTTv311
    )
    client.username_pw_set(
        "simulator_" + device_id,
        Path(os.environ.get("MQTT_PASSWORD_FILE", "/run/secrets/mqtt_password"))
        .read_text()
        .strip(),
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.max_inflight_messages_set(20)
    client.max_queued_messages_set(128)
    client.will_set(
        f"devices/{device_id}/availability",
        device.availability(utc_now(), "offline", will=True),
        qos=1,
        retain=True,
    )
    connected, stop = threading.Event(), threading.Event()
    health = HealthState()
    server = health_server(health)

    def on_connect(client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc != 0:
            connected.clear()
            return
        client.subscribe(
            [(f"devices/{device_id}/commands", 1), (f"devices/{device_id}/receipts", 1)]
        )
        connected.set()
        try:
            device.availability(utc_now(), "online")
            device.report_state(utc_now())
        except (ValueError, SpoolFull, sqlite3.Error):
            logger.warning(
                "device_initial_report_pending",
                extra={
                    "event": "device_initial_report_pending",
                    "device_id": device_id,
                },
            )
        logger.info(
            "mqtt_connected", extra={"event": "mqtt_connected", "device_id": device_id}
        )

    def on_disconnect(client: Any, userdata: Any, rc: int) -> None:
        connected.clear()
        if not stop.is_set():
            try:
                # Paho 1.6 keeps these values for the NEXT CONNECT. Give each
                # connection a distinct will ID; configuration time is not loss time.
                client.will_set(
                    f"devices/{device_id}/availability",
                    device.availability(utc_now(), "offline", will=True),
                    qos=1,
                    retain=True,
                )
            except (ValueError, sqlite3.Error):
                logger.warning(
                    "next_will_pending",
                    extra={"event": "next_will_pending", "device_id": device_id},
                )

    def on_message(client: Any, userdata: Any, message: Any) -> None:
        try:
            event = parse_mqtt_event_v2(message.topic, message.payload)
            if event.dispositivo != device_id:
                raise ValueError("Wrong device")
            if isinstance(event, TransportReceiptV2):
                device.receipt(event.conteudo.source_event_id)
            elif isinstance(event, CommandRequestedV2):
                result = parse_event_v2(device.command(message.payload, utc_now()))
                if isinstance(result, CommandAckV2):
                    logger.info(
                        "command_result",
                        extra={
                            "event": result.tipo,
                            "event_id": result.id,
                            "correlation_id": result.correlation_id
                            or result.conteudo.command_id,
                            "device_id": device_id,
                            "reason_code": result.conteudo.reason_code,
                        },
                    )
        except (ValueError, SpoolFull, sqlite3.Error):
            logger.warning(
                "device_input_rejected",
                extra={"event": "device_input_rejected", "device_id": device_id},
            )

    client.on_connect, client.on_disconnect, client.on_message = (
        on_connect,
        on_disconnect,
        on_message,
    )
    client.connect_async(os.environ.get("MQTT_HOST", "mosquitto"), 1883, keepalive=15)
    client.loop_start()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    previous = time.monotonic()
    next_sample = previous
    next_purge = previous
    spool_ready = True
    try:
        while not stop.wait(0.2):
            now, epoch = time.monotonic(), time.time()
            if now >= next_sample:
                try:
                    device.sample(utc_now(), min(5.0, max(0.0, now - previous)))
                    spool_ready = True
                except (SpoolFull, sqlite3.Error):
                    spool_ready = False
                    logger.warning(
                        "spool_paused",
                        extra={"event": "spool_paused", "device_id": device_id},
                    )
                previous, next_sample = now, now + 2
            if connected.is_set():
                for identity, topic, payload, retain in device.pending(epoch):
                    result = client.publish(topic, payload, qos=1, retain=retain)
                    if result.rc == mqtt.MQTT_ERR_SUCCESS:
                        device.sent(identity, epoch)
            if now >= next_purge:
                device.purge_ledger(epoch)
                next_purge = now + 3600
            health.tick(mqtt=connected.is_set(), spool=spool_ready)
    finally:
        if connected.is_set():
            try:
                payload = device.availability(utc_now(), "offline")
                result = client.publish(
                    f"devices/{device_id}/availability", payload, qos=1, retain=True
                )
                result.wait_for_publish(timeout=2)
            except (ValueError, SpoolFull, sqlite3.Error, RuntimeError):
                pass
        client.disconnect()
        client.loop_stop()
        server.shutdown()
        server.server_close()
        device.close()


if __name__ == "__main__":
    main()
