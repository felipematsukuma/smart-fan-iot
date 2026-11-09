"""Registered manual-ack control consumer and confirmed outbox dispatcher."""

import signal
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pika
from smartfan_common.reliability.amqp import ConfirmedPublisher, connect_amqp
from smartfan_common.reliability.database import engine_for
from smartfan_common.reliability.runtime import (
    HealthState,
    configure_logging,
    health_server,
)
from smartfan_common.reliability.store import DurableStore, LostLease, QuotaExceeded
from sqlalchemy.exc import SQLAlchemyError

from .domain import CommandService
from .worker import Controller


def main() -> None:
    logger = configure_logging("control")
    engine = engine_for("control", Path("/run/secrets/postgres_control"))
    store = DurableStore(engine, "control")
    worker = Controller(store)
    stop = threading.Event()
    health = HealthState()
    server = health_server(health)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    broker = None
    try:
        while not stop.is_set():
            try:
                broker = connect_amqp("control", Path("/run/secrets/rabbit_control"))
                channel = broker.channel()
                channel.basic_qos(prefetch_count=16)
                publisher = ConfirmedPublisher(channel)

                def receive(ch: Any, method: Any, properties: Any, body: bytes) -> None:
                    worker.receive(
                        body,
                        method.routing_key,
                        properties.user_id,
                        properties.message_id,
                    )
                    ch.basic_ack(method.delivery_tag)
                    health.tick(postgres=True, rabbitmq=True)

                channel.basic_consume("q.control", receive, auto_ack=False)
                while not stop.is_set():
                    broker.process_data_events(time_limit=0.1)
                    with store.transaction() as conn:
                        CommandService.expire(conn, datetime.now(UTC))
                    for _ in range(16):
                        if not publisher.publish_one(store):
                            break
                    health.tick(postgres=True, rabbitmq=True)
            except (
                pika.exceptions.AMQPError,
                SQLAlchemyError,
                OSError,
                QuotaExceeded,
                LostLease,
            ):
                health.tick(postgres=False, rabbitmq=False)
                logger.warning(
                    "control_reconnecting", extra={"event": "control_reconnecting"}
                )
                if broker is not None and broker.is_open:
                    broker.close()
                stop.wait(1)
    finally:
        if broker is not None and broker.is_open:
            broker.close()
        server.shutdown()
        server.server_close()
        engine.dispose()


if __name__ == "__main__":
    main()
