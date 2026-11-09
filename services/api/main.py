"""Versioned FastAPI boundary with revocable sessions and append-only audit."""

import asyncio
import base64
import html
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, Query, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from smartfan_common.control import CommandIntent, RuleUpdate
from smartfan_common.device_registry import DeviceCreate, DeviceUpdate
from smartfan_common.influx_v2 import InfluxHTTP
from smartfan_common.lab_config import LabConfig
from smartfan_common.reliability.database import engine_for
from smartfan_common.reliability.runtime import configure_logging
from smartfan_common.reliability.store import DurableStore
from smartfan_common.training_config import TrainingRequest
from smartfan_common.ws_protocol import TicketRequest
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from services.control.domain import (
    PUBLIC_COLUMNS,
    CommandService,
    ControlError,
    public_command,
)

from .auth import AuthService, Principal
from .bus import ApiBus
from .commands import get_rule, update_rule
from .devices import DeviceRegistry
from .errors import Problem
from .history import metrics
from .lab import Lab
from .messaging import FailureJournal, Management
from .models import Models
from .realtime import EventStore
from .security import Role, password_bytes
from .stream import Hub


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    password: SecretStr = Field(min_length=1, max_length=72)


class PublicProblem(BaseModel):
    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    instance: str
    code: str
    correlation_id: UUID
    errors: list[dict[str, str]] | None = None


class UserCreate(Login):
    role: Role

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: SecretStr) -> SecretStr:
        password_bytes(value.get_secret_value(), strong=True)
        return value

    @field_validator("username")
    @classmethod
    def normalized_username(cls, value: str) -> str:
        return value.lower()


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Role | None = None
    enabled: bool | None = None
    password: SecretStr | None = None

    @model_validator(mode="after")
    def changes_required(self) -> "UserUpdate":
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("Provide at least one non-null change")
        if self.password:
            password_bytes(self.password.get_secret_value(), strong=True)
        return self


def problem_response(
    request: Request, error: Problem, errors: list | None = None
) -> JSONResponse:
    body = {
        "type": "urn:smartfan:problem:" + error.code.replace("_", "-"),
        "title": error.title,
        "status": error.status,
        "detail": error.detail,
        "instance": request.url.path,
        "code": error.code,
        "correlation_id": request.state.correlation_id,
    }
    if errors:
        body["errors"] = errors
    headers = {
        "Cache-Control": "no-store",
        "X-Correlation-ID": request.state.correlation_id,
    }
    if error.status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if error.status == 429:
        headers["Retry-After"] = "900"
    return JSONResponse(
        body,
        status_code=error.status,
        media_type="application/problem+json",
        headers=headers,
    )


class BodyLimit:
    def __init__(self, app: Any, limit: int = 16384):
        self.app, self.limit = app, limit

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        chunks = []
        total = 0
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=5)
            except TimeoutError:
                request = Request(scope)
                await problem_response(
                    request,
                    Problem(408, "request_timeout", "Tempo limite da requisição."),
                )(scope, receive, send)
                return
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.limit:
                await problem_response(
                    Request(scope),
                    Problem(
                        413, "body_too_large", "Corpo da requisição excede o limite."
                    ),
                )(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        supplied = False

        async def replay() -> dict:
            nonlocal supplied
            if supplied:
                return await receive()
            supplied = True
            return {
                "type": "http.request",
                "body": b"".join(chunks),
                "more_body": False,
            }

        await self.app(scope, replay, send)


def create_app(
    engine: Engine | None = None,
    key: bytes | None = None,
    origins: tuple[str, ...] | None = None,
    auth: AuthService | None = None,
    realtime: bool | None = None,
    influx: InfluxHTTP | None = None,
    management: Management | None = None,
    artifacts_root: Path = Path("/artifacts"),
) -> FastAPI:
    logger = configure_logging("api")
    database = (
        engine
        if engine is not None
        else engine_for("api", Path("/run/secrets/postgres_api"))
    )
    signing = (
        key
        if key is not None
        else Path("/run/secrets/jwt_signing_key").read_bytes().strip()
    )
    allowed = origins or tuple(
        os.environ.get(
            "WEB_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
        ).split(",")
    )
    if any(
        origin == "*"
        or not origin.startswith(("http://localhost:", "http://127.0.0.1:", "https://"))
        for origin in allowed
    ):
        raise ValueError("Configure explicit local or HTTPS web origins")
    events = EventStore(DurableStore(database, "api"))
    hub = Hub()
    enabled = realtime if realtime is not None else engine is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bus = ApiBus(events, hub, asyncio.get_running_loop()) if enabled else None
        app.state.bus = bus
        if bus:
            bus.thread.start()
        try:
            yield
        finally:
            if bus:
                bus.stop.set()
                await asyncio.to_thread(bus.thread.join, 10)
            if engine is None:
                database.dispose()

    application = FastAPI(
        title="Smart Fan AIoT — Ar-condicionado",
        version="2.0.0",
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        responses={
            status: {
                "description": "Erro padronizado",
                "content": {
                    "application/problem+json": {
                        "schema": PublicProblem.model_json_schema()
                    }
                },
            }
            for status in (400, 401, 403, 408, 409, 413, 422, 429, 500, 503)
        },
    )
    application.state.auth = auth or AuthService(database, signing)
    application.state.engine = database
    application.state.origins = allowed
    application.state.events = events
    registry = DeviceRegistry(database)
    commands = CommandService(events.store)
    journal = FailureJournal(database)
    lab = Lab(events.store)
    models = Models(events.store)
    monitor = management or (
        Management(Path("/run/secrets/rabbit_api-monitor")) if enabled else None
    )
    application.state.hub = hub
    application.state.bus = None
    application.state.influx = influx or (
        InfluxHTTP(Path("/run/influx/token"), timeout=10) if enabled else None
    )
    application.add_middleware(BodyLimit)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Idempotency-Key",
            "X-Correlation-ID",
        ],
        expose_headers=["X-Correlation-ID", "Location"],
    )

    @application.middleware("http")
    async def boundary(request: Request, call_next):
        incoming = request.headers.get("x-correlation-id", "")
        try:
            correlation = str(UUID(incoming)) if len(incoming) == 36 else str(uuid4())
        except ValueError:
            correlation = str(uuid4())
        request.state.correlation_id = correlation
        before = time.monotonic()
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed:
            response = problem_response(
                request, Problem(403, "origin_forbidden", "Origem não permitida.")
            )
        else:
            response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            "http_request",
            extra={
                "event": "http_request",
                "correlation_id": correlation,
                "duration_ms": round((time.monotonic() - before) * 1000, 2),
                "outcome": str(response.status_code),
            },
        )
        return response

    @application.exception_handler(Problem)
    async def on_problem(request: Request, error: Problem):
        return problem_response(request, error)

    @application.exception_handler(RequestValidationError)
    async def on_validation(request: Request, error: RequestValidationError):
        return problem_response(
            request,
            Problem(422, "validation_error", "Dados inválidos."),
            [
                {
                    "field": ".".join(str(part) for part in item["loc"])[:128],
                    "code": item["type"],
                }
                for item in error.errors()
            ],
        )

    @application.exception_handler(SQLAlchemyError)
    async def on_database(request: Request, error: SQLAlchemyError):
        return problem_response(
            request,
            Problem(
                503,
                "database_unavailable",
                "Banco de dados temporariamente indisponível.",
            ),
        )

    @application.exception_handler(HTTPException)
    async def on_http(request: Request, error: HTTPException):
        return problem_response(
            request,
            Problem(error.status_code, "http_error", "Requisição não atendida."),
        )

    @application.exception_handler(Exception)
    async def on_unknown(request: Request, error: Exception):
        return problem_response(
            request,
            Problem(500, "internal_error", "Não foi possível concluir a operação."),
        )

    bearer = HTTPBearer(auto_error=False)

    def current(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> Principal:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise Problem(401, "authentication_required", "Autenticação necessária.")
        return application.state.auth.authenticate(credentials.credentials)

    def admin(principal: Annotated[Principal, Depends(current)]) -> Principal:
        application.state.auth.require_admin(principal)
        return principal

    def operator(principal: Annotated[Principal, Depends(current)]) -> Principal:
        if principal.role not in ("operador", "administrador"):
            raise Problem(
                403, "role_forbidden", "Ação exige operador ou administrador."
            )
        return principal

    @application.get("/health")
    def health():
        return {"status": "alive"}

    @application.get(
        "/api/v1/docs", response_class=HTMLResponse, include_in_schema=False
    )
    def documentation():
        schema = application.openapi()
        return (
            '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>API AIoT v2</title><main><h1>API AIoT v2</h1><p>Especificação versionada. Operações protegidas exigem Authorization Bearer.</p><p><a href="/api/v1/openapi.json">Baixar OpenAPI JSON</a></p><pre>'
            + html.escape(json.dumps(schema, ensure_ascii=False, indent=2))
            + "</pre></main></html>"
        )

    @application.get("/ready")
    def ready():
        with database.connect() as conn:
            exists = conn.execute(
                text("SELECT to_regclass('app.users') IS NOT NULL")
            ).scalar_one()
        if not exists:
            raise Problem(503, "schema_unavailable", "Migrações pendentes.")
        if enabled and (
            application.state.bus is None or not application.state.bus.ready
        ):
            raise Problem(
                503, "messaging_unavailable", "Mensageria temporariamente indisponível."
            )
        return {"status": "ready", "dependencies": {"postgres": True}}

    @application.post("/api/v1/auth/login")
    def login(body: Login, request: Request):
        address = request.client.host if request.client else "unknown"
        return application.state.auth.login(
            body.username,
            body.password.get_secret_value(),
            address,
            request.state.correlation_id,
        )

    @application.get("/api/v1/auth/me")
    def me(principal: Annotated[Principal, Depends(current)]):
        return {
            "id": principal.id,
            "username": principal.username,
            "role": principal.role,
            "expires_at": principal.expires_at,
        }

    @application.post("/api/v1/auth/logout", status_code=204)
    def logout(request: Request, principal: Annotated[Principal, Depends(current)]):
        application.state.auth.logout(principal, request.state.correlation_id)
        return Response(status_code=204)

    @application.post("/api/v1/auth/ws-ticket")
    def ticket(
        request: Request,
        principal: Annotated[Principal, Depends(current)],
        body: TicketRequest | None = None,
    ):
        origin = request.headers.get("origin")
        if origin not in allowed:
            raise Problem(403, "origin_forbidden", "Origem não permitida.")
        value = application.state.auth.ticket(
            principal,
            origin,
            request.state.correlation_id,
            events.authorize(body.devices if body else None),
        )
        return {"ticket": value, "expires_in": 30}

    @application.get("/api/v1/snapshot")
    def snapshot(
        principal: Annotated[Principal, Depends(current)],
        device: Annotated[list[str] | None, Query(max_length=100)] = None,
    ):
        return events.snapshot(events.authorize(device)).model_dump(mode="json")

    @application.get("/api/v1/devices")
    def device_list(
        principal: Annotated[Principal, Depends(current)],
        after: str = Query(default="", max_length=32, pattern=r"^[A-Za-z0-9_-]*$"),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        return registry.list(after, limit)

    @application.get("/api/v1/devices/{identity}")
    def device_get(identity: str, principal: Annotated[Principal, Depends(current)]):
        return registry.get(identity)

    @application.get("/api/v1/devices/{identity}/configurations")
    def device_versions(
        identity: str,
        principal: Annotated[Principal, Depends(current)],
        before: int = Query(default=2147483647, ge=1, le=2147483647),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        registry.get(identity)
        with database.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT revision,configuration,created_at FROM app.device_configurations WHERE device_id=:id AND revision<:before ORDER BY revision DESC LIMIT :limit"
                    ),
                    {"id": identity, "before": before, "limit": limit + 1},
                )
                .mappings()
                .all()
            )
        return {
            "items": [dict(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["revision"] if len(rows) > limit else None,
        }

    @application.post("/api/v1/devices", status_code=201)
    def device_create(
        body: DeviceCreate,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        return registry.create(body, principal, request.state.correlation_id)

    @application.patch("/api/v1/devices/{identity}")
    def device_update(
        identity: str,
        body: DeviceUpdate,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        return registry.update(identity, body, principal, request.state.correlation_id)

    @application.get("/api/v1/devices/{identity}/rule")
    def rule_get(identity: str, principal: Annotated[Principal, Depends(current)]):
        registry.get(identity)
        return get_rule(database, identity)

    @application.patch("/api/v1/devices/{identity}/rule")
    def rule_edit(
        identity: str,
        body: RuleUpdate,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        return update_rule(
            database, identity, body, principal, request.state.correlation_id
        )

    @application.post("/api/v1/devices/{identity}/commands", status_code=202)
    def command_create(
        identity: str,
        body: CommandIntent,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(operator)],
        idempotency_key: Annotated[
            str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
        ],
    ):
        try:
            result = commands.manual(
                identity,
                body,
                principal.id,
                idempotency_key,
                request.state.correlation_id,
            )
        except ControlError as error:
            raise Problem(409, error.code, error.message) from None
        response.headers["Location"] = "/api/v1/commands/" + result["id"]
        return result

    @application.get("/api/v1/commands/{identity}")
    def command_get(identity: UUID, principal: Annotated[Principal, Depends(current)]):
        with database.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT " + PUBLIC_COLUMNS + " FROM app.commands WHERE id=:id"
                    ),
                    {"id": str(identity)},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Problem(404, "command_not_found", "Comando não encontrado.")
        return public_command(row)

    @application.get("/api/v1/devices/{identity}/commands")
    def command_list(
        identity: str,
        principal: Annotated[Principal, Depends(current)],
        limit: int = Query(default=20, ge=1, le=100),
        before: UUID | None = None,
    ):
        registry.get(identity)
        with database.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT "
                        + PUBLIC_COLUMNS
                        + " FROM app.commands WHERE device_id=:id AND (:before IS NULL OR (created_at,id)<(SELECT created_at,id FROM app.commands WHERE id=CAST(:before AS uuid) AND device_id=:id)) ORDER BY created_at DESC,id DESC LIMIT :limit"
                    ),
                    {
                        "id": identity,
                        "before": str(before) if before else None,
                        "limit": limit + 1,
                    },
                )
                .mappings()
                .all()
            )
        return {
            "items": [public_command(row) for row in rows[:limit]],
            "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
        }

    @application.get("/api/v1/devices/{identity}/control")
    def control_state(identity: str, principal: Annotated[Principal, Depends(current)]):
        registry.get(identity)
        with database.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT o.sampled_at,o.telemetry,o.boot_id,p.boot_id AS current_boot,p.mode,p.manual_cooling_block,p.last_revision FROM app.control_observations o JOIN transport.device_status p USING(device_id) WHERE o.device_id=:id"
                    ),
                    {"id": identity},
                )
                .mappings()
                .first()
            )
        if row is None:
            return {"fresh": False, "observation": None}
        return {
            "fresh": row["boot_id"] == row["current_boot"]
            and 0
            <= (
                datetime.now(row["sampled_at"].tzinfo) - row["sampled_at"]
            ).total_seconds()
            <= 6,
            "observation": {
                **dict(row),
                "boot_id": str(row["boot_id"]),
                "current_boot": str(row["current_boot"]),
            },
        }

    @application.get("/api/v1/lab/defaults")
    def lab_defaults(principal: Annotated[Principal, Depends(admin)]):
        config = LabConfig()
        return {
            "configuration": config.model_dump(),
            "rows": config.total,
            "estimated_bytes": config.estimated_bytes,
        }

    @application.post("/api/v1/lab/estimate")
    def lab_estimate(body: LabConfig, principal: Annotated[Principal, Depends(admin)]):
        return {
            "rows": body.total,
            "estimated_bytes": body.estimated_bytes,
            "samples_per_equipment": body.samples_per_equipment,
        }

    @application.post("/api/v1/lab/jobs", status_code=202)
    def lab_create(
        body: LabConfig,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(admin)],
        idempotency_key: Annotated[
            str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
        ],
    ):
        job = lab.create(body, principal, idempotency_key, request.state.correlation_id)
        response.headers["Location"] = "/api/v1/jobs/" + str(job["id"])
        return job

    @application.get("/api/v1/jobs")
    def jobs_list(
        principal: Annotated[Principal, Depends(admin)],
        limit: int = Query(default=50, ge=1, le=100),
        before: UUID | None = None,
        kind: Literal["generate", "train"] | None = None,
    ):
        return lab.jobs(before, limit, kind)

    @application.get("/api/v1/jobs/{identity}")
    def job_get(identity: UUID, principal: Annotated[Principal, Depends(admin)]):
        return lab.job(identity)

    @application.post("/api/v1/jobs/{identity}/cancel", status_code=202)
    def job_cancel(
        identity: UUID,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        return lab.cancel(identity, principal, request.state.correlation_id)

    @application.get("/api/v1/datasets/{identity}")
    def dataset_get(identity: UUID, principal: Annotated[Principal, Depends(admin)]):
        return lab.dataset(identity)

    @application.get("/api/v1/datasets/{identity}/preview")
    def dataset_preview(
        identity: UUID,
        principal: Annotated[Principal, Depends(admin)],
        limit: int = Query(default=20, ge=1, le=200),
    ):
        dataset = lab.dataset(identity)
        if dataset["status"] != "completed":
            raise Problem(409, "dataset_not_ready", "Dataset ainda não está completo.")
        from .lab import preview

        return preview(artifacts_root / "datasets" / str(identity), dataset, limit)

    @application.post("/api/v1/training/jobs", status_code=202)
    def training_create(
        body: TrainingRequest,
        request: Request,
        response: Response,
        principal: Annotated[Principal, Depends(admin)],
        idempotency_key: Annotated[
            str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
        ],
    ):
        result = models.train(
            body, principal, idempotency_key, request.state.correlation_id
        )
        response.headers["Location"] = "/api/v1/jobs/" + str(result["id"])
        return result

    @application.get("/api/v1/models")
    def models_list(
        principal: Annotated[Principal, Depends(admin)],
        limit: int = Query(default=50, ge=1, le=100),
        before: str | None = Query(
            default=None, max_length=64, pattern=r"^mdl_[a-f0-9]{32}$"
        ),
    ):
        return models.list(limit, before)

    @application.get("/api/v1/models/{version}")
    def model_get(version: str, principal: Annotated[Principal, Depends(admin)]):
        return models.get(version)

    @application.get("/api/v1/models/{version}/card")
    def model_card(version: str, principal: Annotated[Principal, Depends(admin)]):
        model = models.get(version)
        if model["status"] != "completed":
            raise Problem(409, "model_not_ready", "Model card ainda indisponível.")
        try:
            raw = (
                artifacts_root / "models" / model["version"] / "model-card.md"
            ).read_bytes()
            if len(raw) > 16384:
                raise ValueError("Card size exceeded")
            return {"markdown": raw.decode("utf-8")}
        except (OSError, ValueError):
            raise Problem(
                503, "artifact_unavailable", "Model card indisponível."
            ) from None

    class PromotionRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        request_id: UUID
        expected_revision: int = Field(strict=True, ge=0)

    @application.post("/api/v1/models/{version}/promote", status_code=202)
    def model_promote(
        version: str,
        body: PromotionRequest,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        return models.promote(
            version,
            body.request_id,
            body.expected_revision,
            principal,
            request.state.correlation_id,
        )

    @application.get("/api/v1/messaging")
    def messaging_snapshot(principal: Annotated[Principal, Depends(admin)]):
        if monitor is None:
            raise Problem(
                503, "messaging_unavailable", "Mensageria temporariamente indisponível."
            )
        return monitor.snapshot()

    @application.get("/api/v1/messaging/failures")
    def messaging_failures(
        principal: Annotated[Principal, Depends(admin)],
        limit: int = Query(default=50, ge=1, le=100),
        before: UUID | None = None,
    ):
        return journal.page(limit, before)

    class ReplayRequest(BaseModel):
        model_config = ConfigDict(extra="forbid")
        request_id: UUID

    @application.post("/api/v1/messaging/failures/{identity}/replay", status_code=202)
    def messaging_replay(
        identity: UUID,
        body: ReplayRequest,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        return journal.replay(
            identity, body.request_id, principal.id, request.state.correlation_id
        )

    @application.websocket("/ws")
    async def websocket(socket: WebSocket):
        await hub.endpoint(socket, application.state.auth, events, allowed)

    @application.get("/api/v1/devices/{identity}/metrics")
    def history_metrics(
        identity: str,
        principal: Annotated[Principal, Depends(current)],
        hours: Annotated[int, Query(ge=1, le=168)] = 24,
    ):
        registry.get(identity)
        if application.state.influx is None:
            raise Problem(
                503, "history_unavailable", "Histórico temporariamente indisponível."
            )
        return metrics(application.state.influx, identity, hours)

    def page(table: str, columns: str, limit: int, cursor: str | None) -> dict:
        parameters: dict = {"limit": limit + 1}
        where = ""
        if cursor:
            try:
                decoded = json.loads(
                    base64.b64decode(
                        cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
                    )
                )
                if (
                    not isinstance(decoded, list)
                    or len(decoded) != 2
                    or not all(isinstance(value, str) for value in decoded)
                ):
                    raise ValueError("Invalid cursor structure")
                stamp, identity = decoded
                stamp = datetime.fromisoformat(stamp)
                if stamp.tzinfo is None:
                    raise ValueError("Naive cursor")
                identity = str(UUID(identity))
            except (ValueError, TypeError):
                raise Problem(
                    422, "invalid_cursor", "Cursor de paginação inválido."
                ) from None
            parameters.update(stamp=stamp, identity=identity)
            where = "WHERE (created_at,id)<(:stamp,:identity)"
        with database.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        f"SELECT {columns} FROM app.{table} {where} ORDER BY created_at DESC,id DESC LIMIT :limit"
                    ),
                    parameters,
                )
                .mappings()
                .all()
            )
        items = [dict(row) for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        [last["created_at"].isoformat(), str(last["id"])]
                    ).encode()
                )
                .decode()
                .rstrip("=")
            )
        return {"items": items, "next_cursor": next_cursor}

    @application.get("/api/v1/users")
    def users(
        principal: Annotated[Principal, Depends(admin)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=256)] = None,
    ):
        return page(
            "users", "id,username,role,enabled,created_at,updated_at", limit, cursor
        )

    @application.post("/api/v1/users", status_code=201)
    def create_user(
        body: UserCreate,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        return application.state.auth.create_user(
            principal,
            body.username,
            body.password.get_secret_value(),
            body.role,
            request.state.correlation_id,
        )

    @application.patch("/api/v1/users/{identity}", status_code=204)
    def update_user(
        identity: UUID,
        body: UserUpdate,
        request: Request,
        principal: Annotated[Principal, Depends(admin)],
    ):
        changes = body.model_dump(exclude_unset=True)
        if body.password:
            changes["password"] = body.password.get_secret_value()
        application.state.auth.update_user(
            principal, str(identity), changes, request.state.correlation_id
        )
        return Response(status_code=204)

    @application.get("/api/v1/audit")
    def audit_page(
        principal: Annotated[Principal, Depends(admin)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Query(max_length=256)] = None,
    ):
        return page(
            "audit",
            "id,actor_user_id,(SELECT username FROM app.users u WHERE u.id=app.audit.actor_user_id) AS actor_username,action,entity_type,entity_id,outcome,correlation_id,details,created_at",
            limit,
            cursor,
        )

    return application
