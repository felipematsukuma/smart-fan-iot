"""Confirmed publication. PG completion always follows broker confirmation."""

from pathlib import Path

import pika

from .database import ROLES
from .store import DurableStore


def connect_amqp(
    owner: str, password_file: Path, host: str = "rabbitmq"
) -> pika.BlockingConnection:
    if owner not in ROLES:
        raise ValueError("Unknown AMQP service owner")
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host,
            virtual_host="/smartfan",
            credentials=pika.PlainCredentials(owner, password_file.read_text().strip()),
            heartbeat=30,
            blocked_connection_timeout=5,
            socket_timeout=3,
            stack_timeout=10,
            connection_attempts=1,
        )
    )


class ConfirmedPublisher:
    def __init__(self, channel: pika.adapters.blocking_connection.BlockingChannel):
        self.channel = channel
        self.channel.confirm_delivery()

    def publish_one(self, store: DurableStore) -> bool:
        delivery = store.claim("outbox", lease_seconds=30)
        if delivery is None:
            return False
        try:
            self.channel.basic_publish(
                exchange=delivery.exchange,
                routing_key=delivery.route,
                body=delivery.payload,
                properties=pika.BasicProperties(
                    content_type="application/json", delivery_mode=2, message_id=delivery.event_id
                ),
                mandatory=True,
            )
        except (pika.exceptions.AMQPError, OSError):
            store.retry(delivery, "broker_unavailable")
            raise
        # A crash after confirm leaves the same bytes for re-publication.
        store.finish(delivery)
        return True
