"""Bounded writer runtime with manual AMQP acknowledgements and reconnects."""

import signal
import threading
import urllib.error
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

from .worker import Writer


def main() -> None:
    logger = configure_logging("writer")
    secrets = Path("/run/secrets")
    engine = engine_for("writer", secrets / "postgres_writer")
    store = DurableStore(engine, "writer")
    worker = Writer(store, InfluxHTTP(Path("/run/influx/token")))
    stop = threading.Event()
    health = HealthState()
    server = health_server(health)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    broker = None
    try:
        while not stop.is_set():
            try:
                broker = connect_amqp("writer", secrets / "rabbit_writer")
                channel = broker.channel()
                channel.basic_qos(prefetch_count=32)
                publisher = ConfirmedPublisher(channel)

                def on_message(
                    ch: Any, method: Any, properties: Any, body: bytes
                ) -> None:
                    worker.receive(
                        body,
                        method.routing_key,
                        properties.user_id,
                        properties.message_id,
                    )
                    ch.basic_ack(method.delivery_tag)

                channel.basic_consume("q.telemetry.writer", on_message, auto_ack=False)
                idle = True
                while not stop.is_set():
                    broker.process_data_events(time_limit=0.05 if idle else 0)
                    active = False
                    influx_ready = worker.influx.healthy()
                    for _ in range(8):
                        if not influx_ready:
                            break
                        delivery = store.claim("inbox")
                        if delivery is None:
                            break
                        active = True
                        try:
                            worker.process(delivery)
                        except urllib.error.HTTPError as error:
                            if error.code in (400, 413, 422):
                                store.retry(
                                    delivery, "influx_rejected_point", permanent=True
                                )
                            else:
                                store.retry(
                                    delivery,
                                    "influx_unavailable",
                                    dependency_failure=True,
                                )
                                influx_ready = False
                                break
                        except (OSError, TimeoutError):
                            store.retry(
                                delivery, "influx_unavailable", dependency_failure=True
                            )
                            influx_ready = False
                            break
                        except (ValueError, TypeError):
                            store.retry(
                                delivery, "invalid_point_identity", permanent=True
                            )
                    active = bool(publisher.publish_batch(store, limit=8)) or active
                    idle = not active
                    health.tick(postgres=True, rabbitmq=True, influxdb=influx_ready)
            except (
                pika.exceptions.AMQPError,
                SQLAlchemyError,
                OSError,
                QuotaExceeded,
                LostLease,
            ):
                health.tick(postgres=False, rabbitmq=False, influxdb=False)
                logger.warning(
                    "writer_reconnecting", extra={"event": "writer_reconnecting"}
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
