"""One local generation, two waiting requests, durable limits and fenced cleanup."""

import asyncio
import hashlib
import importlib
import time
from contextlib import suppress
from io import BufferedRandom
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi.responses import StreamingResponse
from smartfan_common.influx_v2 import InfluxHTTP
from smartfan_common.reliability.leases import ResourceLeases, ResourceToken
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from .assistant_context import MODEL, ChatRequest, compact, messages, summary
from .auth import Principal, audit
from .errors import Problem
from .ollama import Ollama


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def sse(kind: str, content: dict) -> bytes:
    return ("event: " + kind + "\ndata: " + compact(content) + "\n\n").encode()


class Assistant:
    def __init__(
        self,
        engine: Engine,
        influx: InfluxHTTP | None,
        runtime: Path | None = None,
        ollama: Ollama | None = None,
    ):
        self.engine = engine
        self.influx = influx
        self.runtime = runtime
        self.ollama = ollama or Ollama()
        self.leases = ResourceLeases(engine, "api")
        self.instance = str(uuid4())
        self.lock: BufferedRandom | None = None
        self.pending = 0
        self.gate = asyncio.Semaphore(1)
        self.admission = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        self.tokens: set[str] = set()
        self.reserved: dict[str, tuple[Principal, str]] = {}
        self.ready = False

    async def start(self):
        if self.runtime is not None:
            fcntl: Any = importlib.import_module("fcntl")

            self.runtime.mkdir(parents=True, exist_ok=True)
            self.lock = (self.runtime / ".api.lock").open("a+b")
            # Never unlink this inode; no new API recovers a still-running owner.
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.ready = True
        await self.recover()

    def resource(self):
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT holder_service,owner_instance_id,generation,state FROM transport.resource_leases WHERE resource='heavy'"
                )
            ).first()
        return row

    async def recover(self):
        row = await asyncio.to_thread(self.resource)
        if (
            row
            and row[0] == "api"
            and row[3] != "released"
            and str(row[1]) not in self.tokens
        ):
            if not await self.ollama.unload():
                self.ready = False
                return
            token = ResourceToken("heavy", str(row[1]), "api", row[2])
            await asyncio.to_thread(self.leases.release_after_confirmed_stop, token)
        self.ready = True
        await asyncio.to_thread(self.reconcile_requests)

    def reconcile_requests(self):
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.assistant_requests SET outcome='failed',reason_code='api_interrupted',finished_at=clock_timestamp() WHERE instance_id<>:instance AND outcome IN ('queued','running')"
                ),
                {"instance": self.instance},
            )

    def admit(self, principal: Principal, body: ChatRequest, correlation: str) -> str:
        identity = str(uuid4())
        with self.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(734123)"))
            counts = conn.execute(
                text(
                    "SELECT count(*) FILTER(WHERE actor_user_id=:actor AND created_at>clock_timestamp()-interval '1 minute'),count(*) FROM app.assistant_requests WHERE created_at>clock_timestamp()-interval '10 minutes'"
                ),
                {"actor": principal.id},
            ).one()
            if counts[0] >= 5 or counts[1] >= 20:
                raise Problem(
                    429,
                    "assistant_rate_limit",
                    "Limite de perguntas atingido; aguarde antes de tentar novamente.",
                )
            resource = conn.execute(
                text(
                    "SELECT holder_service,state FROM transport.resource_leases WHERE resource='heavy'"
                )
            ).first()
            if resource and resource[1] != "released" and resource[0] != "api":
                raise Problem(
                    503,
                    "heavy_job_active",
                    "Assistente temporariamente indisponível durante job pesado.",
                )
            conn.execute(
                text(
                    "INSERT INTO app.assistant_requests(id,actor_user_id,instance_id,device_id,question_sha256,summary_sha256,sources,model) VALUES(:id,:actor,:instance,:device,:hash,:empty,'[]',:model)"
                ),
                {
                    "id": identity,
                    "actor": principal.id,
                    "instance": self.instance,
                    "device": body.device_id,
                    "hash": digest(body.question),
                    "empty": "0" * 64,
                    "model": MODEL,
                },
            )
            audit(
                conn,
                principal.id,
                "assistant.requested",
                "assistant",
                identity,
                correlation,
                {"device_id": body.device_id, "model": MODEL},
            )
        return identity

    async def reserve(
        self, principal: Principal, body: ChatRequest, correlation: str
    ) -> str:
        async with self.admission:
            return await self._reserve(principal, body, correlation)

    async def _reserve(
        self, principal: Principal, body: ChatRequest, correlation: str
    ) -> str:
        if not self.pending:
            await self.recover()
        if not self.ready:
            raise Problem(
                503,
                "assistant_recovering",
                "Assistente em recuperação; liberação de recursos ainda não confirmada.",
            )
        if self.pending >= 3:
            raise Problem(
                429,
                "assistant_queue_full",
                "Uma conversa ativa e duas aguardando; tente novamente depois.",
            )
        self.pending += 1
        try:
            identity = await asyncio.to_thread(self.admit, principal, body, correlation)
            self.reserved[identity] = (principal, correlation)
            return identity
        except BaseException:
            self.pending -= 1
            raise

    def save_context(self, identity: str, context: dict):
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.assistant_requests SET outcome='running',summary_sha256=:hash,sources=CAST(:sources AS jsonb) WHERE id=:id"
                ),
                {
                    "id": identity,
                    "hash": digest(compact(context)),
                    "sources": compact(context.get("sources", [])),
                },
            )

    def valid_session(self, principal: Principal) -> bool:
        with self.engine.connect() as conn:
            return (
                conn.execute(
                    text(
                        "SELECT 1 FROM app.sessions s JOIN app.users u ON u.id=s.user_id WHERE s.id=:id AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp() AND u.enabled AND u.auth_version=:version"
                    ),
                    {"id": principal.session_id, "version": principal.auth_version},
                ).first()
                is not None
            )

    async def renew(self, token: ResourceToken, principal: Principal):
        while True:
            await asyncio.sleep(5)
            try:
                if not await asyncio.to_thread(
                    self.leases.renew, token
                ) or not await asyncio.to_thread(self.valid_session, principal):
                    return
            except (SQLAlchemyError, OSError):
                return

    def finish(
        self,
        identity: str,
        principal: Principal,
        correlation: str,
        outcome: str,
        reason: str | None,
        started: float,
        first_ms: int | None,
        tokens: int,
        answer: str,
        token: ResourceToken | None,
    ):
        with self.engine.begin() as conn:
            if outcome == "completed":
                authority = conn.execute(
                    text(
                        "SELECT 1 FROM transport.resource_leases WHERE resource='heavy' AND holder_service='api' AND owner_instance_id=:owner AND generation=:generation AND state='active' AND expires_at>clock_timestamp() FOR UPDATE"
                    ),
                    {
                        "owner": token.owner_instance_id if token else None,
                        "generation": token.generation if token else None,
                    },
                ).first()
                if not authority:
                    outcome, reason = "failed", "resource_lease_lost"
            duration = round((time.monotonic() - started) * 1000)
            conn.execute(
                text(
                    "UPDATE app.assistant_requests SET outcome=:outcome,finished_at=clock_timestamp(),duration_ms=:duration,first_token_ms=:first,tokens=:tokens,response_sha256=:hash,reason_code=:reason WHERE id=:id AND instance_id=:instance"
                ),
                {
                    "id": identity,
                    "instance": self.instance,
                    "outcome": outcome,
                    "duration": duration,
                    "first": first_ms,
                    "tokens": tokens,
                    "hash": digest(answer),
                    "reason": reason,
                },
            )
            audit(
                conn,
                principal.id,
                "assistant." + outcome,
                "assistant",
                identity,
                correlation,
                {
                    "model": MODEL,
                    "duration_ms": duration,
                    "tokens": tokens,
                    "reason_code": reason,
                },
                "success" if outcome == "completed" else "failure",
            )
        return outcome

    async def run(
        self,
        queue: asyncio.Queue,
        identity: str,
        principal: Principal,
        body: ChatRequest,
        correlation: str,
    ):
        started = time.monotonic()
        token = None
        first_ms = None
        tokens = 0
        answer = ""
        outcome = "failed"
        reason: str | None = "local_model_unavailable"
        stopped = False
        active = False
        acquired = False
        renewal: asyncio.Task | None = None
        generation: asyncio.Task | None = None
        try:
            async with asyncio.timeout(90):
                await queue.put(
                    (
                        "meta",
                        {"state": "queued", "request_id": identity, "model": MODEL},
                    )
                )
                await self.gate.acquire()
                acquired = True
                token = await asyncio.to_thread(self.leases.acquire, identity, "chat")
                if token is None:
                    raise Problem(
                        503,
                        "heavy_resource_busy",
                        "Recurso pesado ocupado ou em recuperação.",
                    )
                active = True
                self.tokens.add(identity)
                renewal = asyncio.create_task(self.renew(token, principal))

                async def generate():
                    nonlocal first_ms, tokens, answer, stopped
                    context = await asyncio.to_thread(
                        summary, self.engine, body.device_id, self.influx
                    )
                    prompt, turns = messages(body, context)
                    await asyncio.to_thread(self.save_context, identity, context)
                    await queue.put(
                        (
                            "meta",
                            {
                                "state": "warming",
                                "request_id": identity,
                                "model": MODEL,
                                "summary": context,
                                "history_turns": turns,
                            },
                        )
                    )
                    stream = self.ollama.stream(prompt)
                    generation_started = time.monotonic()
                    try:
                        while True:
                            if first_ms is None:
                                packet = await asyncio.wait_for(
                                    anext(stream),
                                    timeout=max(
                                        0.01,
                                        30 - (time.monotonic() - generation_started),
                                    ),
                                )
                            else:
                                packet = await anext(stream)
                            if packet.get("delta"):
                                if first_ms is None:
                                    first_ms = round(
                                        (time.monotonic() - generation_started) * 1000
                                    )
                                answer += packet["delta"]
                                await queue.put(("delta", {"text": packet["delta"]}))
                            if packet.get("done"):
                                stopped = True
                                tokens = packet["tokens"]
                                if not answer.strip():
                                    raise ValueError("Empty local answer")
                                return
                    finally:
                        await stream.aclose()

                generation = asyncio.create_task(generate())
                done, _ = await asyncio.wait(
                    {generation, renewal}, return_when=asyncio.FIRST_COMPLETED
                )
                if renewal in done:
                    raise Problem(
                        503,
                        "resource_or_session_lost",
                        "Geração interrompida por perda de sessão ou de recursos.",
                    )
                await generation
                outcome, reason = "completed", None
        except asyncio.CancelledError:
            outcome, reason = "cancelled", "client_disconnected"
        except TimeoutError:
            reason = "local_model_timeout"
        except Problem as failure:
            reason = failure.code
        except (
            httpx.HTTPError,
            SQLAlchemyError,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            StopAsyncIteration,
        ):
            reason = "local_model_unavailable"
        finally:
            for task in (generation, renewal):
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task
            if active and not stopped:
                stopped = await self.ollama.unload()
            try:
                outcome = await asyncio.to_thread(
                    self.finish,
                    identity,
                    principal,
                    correlation,
                    outcome,
                    reason,
                    started,
                    first_ms,
                    tokens,
                    answer,
                    token,
                )
            except (SQLAlchemyError, OSError):
                outcome, reason = "failed", "audit_unavailable"
            if token and stopped:
                try:
                    await asyncio.to_thread(
                        self.leases.release_after_confirmed_stop, token
                    )
                except (SQLAlchemyError, OSError):
                    self.ready = False
            elif active:
                self.ready = False
            if acquired:
                self.gate.release()
            self.tokens.discard(identity)
            self.pending -= 1
            terminal = (
                (
                    "done",
                    {
                        "request_id": identity,
                        "model": MODEL,
                        "first_token_ms": first_ms,
                        "tokens": tokens,
                    },
                )
                if outcome == "completed"
                else (
                    "error",
                    {
                        "code": reason or "resource_lease_lost",
                        "message": "Resposta interrompida. Consulte o estado dos recursos e tente novamente.",
                    },
                )
            )
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(terminal)

    async def stream(
        self, identity: str, principal: Principal, body: ChatRequest, correlation: str
    ):
        self.reserved.pop(identity, None)
        queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        task = asyncio.create_task(
            self.run(queue, identity, principal, body, correlation)
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        try:
            while True:
                try:
                    kind, value = await asyncio.wait_for(queue.get(), timeout=5)
                    yield sse(kind, value)
                    if kind in ("done", "error"):
                        break
                except TimeoutError:
                    yield b": heartbeat\n\n"
        finally:
            if not task.cancelling():
                task.cancel()
            # Stop/upstream proof and fenced cleanup must outlive browser disconnect.
            with suppress(asyncio.CancelledError):
                await asyncio.shield(task)

    async def abandon(self, identity: str):
        reserved = self.reserved.pop(identity, None)
        if reserved is None:
            return
        self.pending -= 1
        principal, correlation = reserved
        with suppress(SQLAlchemyError, OSError):
            await asyncio.to_thread(
                self.finish,
                identity,
                principal,
                correlation,
                "cancelled",
                "stream_not_started",
                time.monotonic(),
                None,
                0,
                "",
                None,
            )

    async def close(self):
        for identity in tuple(self.reserved):
            await self.abandon(identity)
        for task in tuple(self.tasks):
            if not task.cancelling():
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.ollama.close()
        if self.lock:
            self.lock.close()


class AssistantResponse(StreamingResponse):
    def __init__(
        self,
        service: Assistant,
        identity: str,
        principal: Principal,
        body: ChatRequest,
        correlation: str,
    ):
        self.service, self.identity = service, identity
        super().__init__(
            service.stream(identity, principal, body, correlation),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Even a disconnect while sending response headers releases admission.
            await asyncio.shield(self.service.abandon(self.identity))
