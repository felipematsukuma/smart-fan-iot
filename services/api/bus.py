"""One broker thread per API process; WebSocket delivery follows SQL commit."""

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import pika
from smartfan_common.reliability.amqp import ConfirmedPublisher, connect_amqp
from smartfan_common.reliability.store import QuotaExceeded
from sqlalchemy.exc import SQLAlchemyError

from .realtime import EventStore
from .stream import Hub


class ApiBus:
    def __init__(self, events: EventStore, hub: Hub, loop: asyncio.AbstractEventLoop):
        self.events, self.hub, self.loop = events, hub, loop
        self.stop = threading.Event()
        self.connected = False
        self.tick = 0.0
        self.thread = threading.Thread(target=self.run, daemon=True, name="api-amqp")

    @property
    def ready(self) -> bool:
        return self.connected and time.monotonic() - self.tick < 15

    def run(self) -> None:
        broker = None
        try:
            while not self.stop.is_set():
                try:
                    broker = connect_amqp("api", Path("/run/secrets/rabbit_api"))
                    channel = broker.channel()
                    channel.basic_qos(prefetch_count=32)
                    publisher = ConfirmedPublisher(channel)

                    def receive(
                        ch: Any, method: Any, properties: Any, body: bytes
                    ) -> None:
                        event, backlog = self.events.receive(
                            body,
                            method.routing_key,
                            properties.user_id,
                            properties.message_id,
                        )
                        ch.basic_ack(method.delivery_tag)
                        if event is not None or backlog:
                            self.loop.call_soon_threadsafe(
                                self.hub.offer, event, backlog
                            )

                    channel.basic_consume("q.events.api", receive, auto_ack=False)
                    while not self.stop.is_set():
                        broker.process_data_events(time_limit=0.1)
                        for _ in range(8):
                            if not publisher.publish_one(self.events.store):
                                break
                        self.connected = True
                        self.tick = time.monotonic()
                except (
                    pika.exceptions.AMQPError,
                    OSError,
                    SQLAlchemyError,
                    QuotaExceeded,
                ):
                    self.connected = False
                    if broker is not None and broker.is_open:
                        broker.close()
                    self.stop.wait(1)
        finally:
            self.connected = False
            if broker is not None and broker.is_open:
                broker.close()
