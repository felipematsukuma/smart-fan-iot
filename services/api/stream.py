"""Bounded WebSocket sessions with one-use tickets and periodic revocation checks."""

import asyncio
import time
from dataclasses import dataclass, field
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from smartfan_common.contracts_v2 import EventV2, JobProgressV2, ModelActivatedV2
from smartfan_common.ws_protocol import (
    CLIENT_PACKET,
    Authenticate,
    Authenticated,
    Ping,
    Pong,
    Subscribe,
)
from sqlalchemy.exc import SQLAlchemyError

from .auth import AuthService, Principal
from .errors import Problem
from .realtime import EventStore, utc_now, wire_time


@dataclass(eq=False)
class Client:
    principal: Principal
    devices: tuple[str, ...]
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=32))
    overloaded: bool = False
    skipped: int = 0


class Hub:
    def __init__(self):
        self.clients: set[Client] = set()
        self.pending: dict[str, int] = {}

    def offer(self, event: EventV2 | None, backlog: bool = False) -> None:
        for client in self.clients:
            if event is None:
                continue
            if isinstance(event, (JobProgressV2, ModelActivatedV2)):
                if client.principal.role != "administrador":
                    continue
            elif event.dispositivo not in client.devices:
                continue
            if backlog:
                client.skipped += 1
                continue
            try:
                client.queue.put_nowait(event.model_dump(mode="json"))
            except asyncio.QueueFull:
                client.overloaded = True

    async def endpoint(
        self,
        socket: WebSocket,
        auth: AuthService,
        events: EventStore,
        origins: tuple[str, ...],
    ) -> None:
        origin = socket.headers.get("origin")
        address = socket.client.host if socket.client else "unknown"
        if origin not in origins or socket.query_params:
            await socket.close(code=1008)
            return
        if sum(self.pending.values()) >= 16 or self.pending.get(address, 0) >= 4:
            await socket.close(code=1013)
            return
        self.pending[address] = self.pending.get(address, 0) + 1
        client = None
        receiver = None
        pending = True
        try:
            await socket.accept()
            raw = await asyncio.wait_for(socket.receive_text(), timeout=5)
            if len(raw.encode()) > 8192:
                raise ValueError("Control packet too large")
            packet = CLIENT_PACKET.validate_json(raw)
            if not isinstance(packet, Authenticate):
                raise TypeError("Authentication must be first")
            principal = await asyncio.wait_for(
                asyncio.to_thread(auth.consume_ticket, packet.ticket, origin), timeout=2
            )
            scope = principal.device_scope or ()
            selected = (
                tuple(dict.fromkeys(packet.devices))
                if packet.devices is not None
                else scope
            )
            if not set(selected) <= set(scope):
                raise ValueError("Subscription exceeds issued ticket scope")
            await asyncio.to_thread(events.authorize, list(selected))
            if (
                len(self.clients) >= 32
                or sum(c.principal.id == principal.id for c in self.clients) >= 3
            ):
                await socket.close(code=1013)
                return
            client = Client(principal, selected)
            self.clients.add(client)
            self.pending[address] -= 1
            pending = False
            await asyncio.wait_for(
                socket.send_json(
                    Authenticated(server_time=wire_time(utc_now())).model_dump()
                ),
                timeout=2,
            )
            snapshot = await asyncio.to_thread(events.snapshot, selected)
            await asyncio.wait_for(
                socket.send_json(snapshot.model_dump(mode="json")), timeout=2
            )
            last_seen = time.monotonic()
            last_ping = last_check = 0.0
            ping_id = None
            receiver = asyncio.create_task(socket.receive_text())
            while True:
                now = time.monotonic()
                if client.overloaded or now - last_seen > 45:
                    await asyncio.wait_for(socket.close(code=1013), timeout=1)
                    return
                if now - last_check >= 1:
                    valid = await asyncio.wait_for(
                        asyncio.to_thread(auth.session_valid, principal), timeout=2
                    )
                    if not valid:
                        await asyncio.wait_for(socket.close(code=1008), timeout=1)
                        return
                    # Disabling a device revokes an already-open scope as well.
                    await asyncio.wait_for(
                        asyncio.to_thread(events.authorize, client.devices), timeout=2
                    )
                    last_check = now
                if now - last_ping >= 15:
                    ping_id = str(uuid4())
                    await asyncio.wait_for(
                        socket.send_json({"type": "ping", "id": ping_id}), timeout=2
                    )
                    last_ping = now
                if receiver.done():
                    raw = receiver.result()
                    if len(raw.encode()) > 8192:
                        raise ValueError("Control packet too large")
                    message = CLIENT_PACKET.validate_json(raw)
                    if isinstance(message, Pong) and message.id == ping_id:
                        last_seen = now
                    elif isinstance(message, Ping):
                        last_seen = now
                        await asyncio.wait_for(
                            socket.send_json({"type": "pong", "id": message.id}),
                            timeout=2,
                        )
                    elif isinstance(message, Subscribe):
                        if not set(message.devices) <= set(scope):
                            raise ValueError("Forbidden subscription")
                        client.devices = await asyncio.to_thread(
                            events.authorize, message.devices
                        )
                        snapshot = await asyncio.to_thread(
                            events.snapshot, client.devices
                        )
                        await asyncio.wait_for(
                            socket.send_json(snapshot.model_dump(mode="json")),
                            timeout=2,
                        )
                    else:
                        raise ValueError("Invalid stream control")
                    receiver = asyncio.create_task(socket.receive_text())
                if client.skipped:
                    await asyncio.wait_for(
                        socket.send_json(
                            {
                                "type": "notice",
                                "code": "backlog_skipped",
                                "count": client.skipped,
                            }
                        ),
                        timeout=2,
                    )
                    client.skipped = 0
                for _ in range(8):
                    try:
                        message = client.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    await asyncio.wait_for(socket.send_json(message), timeout=2)
                await asyncio.sleep(0.05)
        except (TimeoutError, ValueError, TypeError, Problem, SQLAlchemyError):
            try:
                await asyncio.wait_for(socket.close(code=1008), timeout=1)
            except (RuntimeError, WebSocketDisconnect, TimeoutError):
                pass
        except WebSocketDisconnect:
            pass
        finally:
            if receiver is not None:
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
            if client is not None:
                self.clients.discard(client)
            if pending:
                self.pending[address] -= 1
            if not self.pending.get(address):
                self.pending.pop(address, None)
