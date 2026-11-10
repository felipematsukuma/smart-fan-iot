"""Registered prediction consumer, bounded batch processing and confirmed publication."""

import signal
import threading
import time
from pathlib import Path
from typing import Any

import pika
from smartfan_common.influx_v2 import InfluxHTTP
from smartfan_common.reliability.amqp import ConfirmedPublisher, connect_amqp
from smartfan_common.reliability.database import engine_for
from smartfan_common.reliability.runtime import (
    HealthState,
    configure_logging,
    health_server,
)
from smartfan_common.reliability.store import DurableStore, LostLease, QuotaExceeded
from sqlalchemy.exc import SQLAlchemyError

from .models import ModelRuntime
from .window import Windows
from .worker import Inference


def main() -> None:
    logger = configure_logging("inference")
    secrets = Path("/run/secrets")
    engine = engine_for("inference", secrets / "postgres_inference")
    store = DurableStore(engine, "inference")
    models = ModelRuntime(store, Path("/artifacts"))
    worker = Inference(store, models, Windows(InfluxHTTP(Path("/run/influx/token"))))
    stop = threading.Event()
    health = HealthState()
    server = health_server(health)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    broker = None
    next_sync = 0.0
    try:
        while not stop.is_set():
            try:
                models.synchronize()
                broker = connect_amqp("inference", secrets / "rabbit_inference")
                channel = broker.channel()
                channel.basic_qos(prefetch_count=32)
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

                channel.basic_consume("q.inference", receive, auto_ack=False)
                while not stop.is_set():
                    broker.process_data_events(time_limit=0.05)
                    if time.monotonic() >= next_sync:
                        models.synchronize()
                        next_sync = time.monotonic() + 1
                    for _ in range(32):
                        delivery = store.claim()
                        if delivery is None:
                            break
                        try:
                            worker.process(delivery)
                        except (ValueError, TypeError, KeyError):
                            store.retry(
                                delivery, "invalid_inference_result", permanent=True
                            )
                    for _ in range(32):
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
                    "inference_reconnecting", extra={"event": "inference_reconnecting"}
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
