"""Bounded broker loop; heavy computation runs in an independently fenced child."""

import signal
import threading
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

from .supervisor import Supervisor, stop_process


def main() -> None:
    logger = configure_logging("jobs-worker")
    secrets = Path("/run/secrets")
    engine = engine_for("jobs-worker", secrets / "postgres_jobs-worker")
    store = DurableStore(engine, "jobs-worker")
    supervisor = Supervisor(store, Path("/artifacts"))
    stop = threading.Event()
    health = HealthState()
    server = health_server(health)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    broker = None
    recovery = True
    try:
        while not stop.is_set():
            try:
                if recovery:
                    supervisor.recover()
                    recovery = False
                broker = connect_amqp("jobs-worker", secrets / "rabbit_jobs-worker")
                channel = broker.channel()
                channel.basic_qos(prefetch_count=1)
                publisher = ConfirmedPublisher(channel)

                def receive(ch: Any, method: Any, properties: Any, body: bytes) -> None:
                    supervisor.receive(
                        body,
                        method.routing_key,
                        properties.user_id,
                        properties.message_id,
                    )
                    ch.basic_ack(method.delivery_tag)

                channel.basic_consume("q.jobs.generate", receive, auto_ack=False)
                channel.basic_consume("q.jobs.train", receive, auto_ack=False)
                while not stop.is_set():
                    broker.process_data_events(time_limit=0.1)
                    supervisor.tick()
                    supervisor.enqueue_activation()
                    for _ in range(8):
                        if not publisher.publish_one(store):
                            break
                    health.tick(postgres=True, rabbitmq=True, supervisor=True)
            except (
                pika.exceptions.AMQPError,
                SQLAlchemyError,
                OSError,
                QuotaExceeded,
                LostLease,
                RuntimeError,
                ValueError,
            ):
                health.tick(postgres=False, rabbitmq=False, supervisor=False)
                if supervisor.work is not None:
                    stop_process(supervisor.work.process)
                recovery = True
                logger.warning(
                    "jobs_reconnecting", extra={"event": "jobs_reconnecting"}
                )
                if broker is not None and broker.is_open:
                    broker.close()
                stop.wait(1)
    finally:
        supervisor.close()
        if broker is not None and broker.is_open:
            broker.close()
        server.shutdown()
        server.server_close()
        engine.dispose()


if __name__ == "__main__":
    main()
