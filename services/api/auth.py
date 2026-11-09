"""PostgreSQL identities, bounded authentication and revocable JWT sessions."""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from .errors import Problem
from .security import (
    BCRYPT_COST,
    Role,
    check_password,
    decode_token,
    hash_password,
    keyed_identity,
)


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    role: Role
    auth_version: int
    session_id: str
    expires_at: datetime


def audit(
    conn: Connection,
    actor: str | None,
    action: str,
    entity: str,
    identity: str | None,
    correlation: str,
    details: dict | None = None,
    outcome: str = "success",
) -> None:
    conn.execute(
        text(
            "INSERT INTO app.audit(id,actor_user_id,action,entity_type,entity_id,correlation_id,details,outcome) VALUES(:id,:actor,:action,:entity,:identity,:correlation,CAST(:details AS jsonb),:outcome)"
        ),
        {
            "id": str(uuid4()),
            "actor": actor,
            "action": action,
            "entity": entity,
            "identity": identity,
            "correlation": correlation,
            "details": json.dumps(details or {}),
            "outcome": outcome,
        },
    )


def seed_users(engine: Engine, directory: Path) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(734119)"))
        for username, role, filename in (
            ("admin", "administrador", "initial_admin_password"),
            ("operador", "operador", "initial_operator_password"),
            ("visualizador", "visualizador", "initial_viewer_password"),
        ):
            existing = (
                conn.execute(
                    text("SELECT id,password_hash FROM app.users WHERE username=:name"),
                    {"name": username},
                )
                .mappings()
                .first()
            )
            initial = (directory / filename).read_text().strip()
            if existing is not None:
                previous = bytes(existing["password_hash"])
                parts = previous.split(b"$")
                if (
                    len(parts) == 4
                    and parts[2] != f"{BCRYPT_COST:02}".encode()
                    and check_password(initial, previous)
                ):
                    conn.execute(
                        text("UPDATE app.users SET password_hash=:hash WHERE id=:id"),
                        {"hash": hash_password(initial), "id": existing["id"]},
                    )
                    audit(
                        conn,
                        None,
                        "user.hash_policy",
                        "user",
                        str(existing["id"]),
                        str(uuid4()),
                        {"cost": BCRYPT_COST},
                    )
                continue
            identity = str(uuid4())
            conn.execute(
                text(
                    "INSERT INTO app.users(id,username,password_hash,role) VALUES(:id,:name,:hash,:role)"
                ),
                {
                    "id": identity,
                    "name": username,
                    "hash": hash_password(initial),
                    "role": role,
                },
            )
            audit(
                conn,
                None,
                "user.bootstrap",
                "user",
                identity,
                str(uuid4()),
                {"role": role},
            )


class AuthService:
    def __init__(
        self,
        engine: Engine,
        key: bytes,
        cost: int = BCRYPT_COST,
        progressive_delay: bool = True,
    ):
        if len(key) < 32:
            raise ValueError("JWT signing key must contain at least 256 bits")
        self.engine, self.key, self.cost, self.progressive_delay = (
            engine,
            key,
            cost,
            progressive_delay,
        )
        self._dummy = hash_password(secrets.token_urlsafe(24), cost)

    def _reserve_login(
        self, username: str, ip: str, correlation: str
    ) -> tuple[str, int]:
        identity = keyed_identity(self.key, "identity", username)
        address = keyed_identity(self.key, "ip", ip)
        blocked = False
        attempt = str(uuid4())
        with self.engine.begin() as conn:
            for lock in sorted((identity, address)):
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:key),734117)"),
                    {"key": lock},
                )
            failures = conn.execute(
                text(
                    "SELECT count(*) FILTER(WHERE identity_hash=:identity),count(*) FILTER(WHERE ip_hash=:ip) FROM app.login_attempts WHERE failed AND created_at>clock_timestamp()-interval '15 minutes' AND (identity_hash=:identity OR ip_hash=:ip)"
                ),
                {"identity": identity, "ip": address},
            ).one()
            if failures[0] >= 5 or failures[1] >= 30:
                blocked = True
                rate_identity = address if failures[1] >= 30 else identity
                recent = conn.execute(
                    text(
                        "SELECT 1 FROM app.audit WHERE action='auth.rate_limited' AND entity_id=:identity AND created_at>clock_timestamp()-interval '15 minutes' LIMIT 1"
                    ),
                    {"identity": rate_identity},
                ).scalar_one_or_none()
                if not recent:
                    audit(
                        conn,
                        None,
                        "auth.rate_limited",
                        "login",
                        rate_identity,
                        correlation,
                        outcome="denied",
                    )
            else:
                conn.execute(
                    text(
                        "INSERT INTO app.login_attempts(id,identity_hash,ip_hash) VALUES(:id,:identity,:ip)"
                    ),
                    {"id": attempt, "identity": identity, "ip": address},
                )
        if blocked:
            raise Problem(
                429,
                "login_rate_limited",
                "Muitas tentativas. Aguarde antes de tentar novamente.",
            )
        return attempt, int(failures[0])

    def login(self, username: str, password: str, ip: str, correlation: str) -> dict:
        username = username.strip().lower()
        attempt, failures = self._reserve_login(username, ip, correlation)
        if self.progressive_delay and failures:
            time.sleep(min(1.6, 0.1 * 2**failures))
        with self.engine.connect() as conn:
            user = (
                conn.execute(
                    text("SELECT * FROM app.users WHERE username=:name"),
                    {"name": username},
                )
                .mappings()
                .first()
            )
        valid = check_password(
            password, bytes(user["password_hash"]) if user else self._dummy
        )
        with self.engine.begin() as conn:
            current = (
                conn.execute(
                    text("SELECT * FROM app.users WHERE username=:name FOR UPDATE"),
                    {"name": username},
                )
                .mappings()
                .first()
            )
            if (
                not valid
                or not user
                or not current
                or not current["enabled"]
                or current["auth_version"] != user["auth_version"]
                or current["password_hash"] != user["password_hash"]
            ):
                audit(
                    conn,
                    None,
                    "auth.login_failed",
                    "login",
                    str(current["id"]) if current else None,
                    correlation,
                    outcome="denied",
                )
                denied = True
            else:
                denied = False
                conn.execute(
                    text("UPDATE app.login_attempts SET failed=false WHERE id=:id"),
                    {"id": attempt},
                )
                now = datetime.now(UTC).replace(microsecond=0)
                expires = now + timedelta(minutes=30)
                session = str(uuid4())
                conn.execute(
                    text(
                        "INSERT INTO app.sessions(id,user_id,auth_version,expires_at) VALUES(:id,:user,:version,:expires)"
                    ),
                    {
                        "id": session,
                        "user": str(current["id"]),
                        "version": current["auth_version"],
                        "expires": expires,
                    },
                )
                claims = {
                    "sub": str(current["id"]),
                    "role": current["role"],
                    "jti": session,
                    "auth_version": current["auth_version"],
                    "iss": "smartfan-aiot",
                    "aud": "smartfan-web",
                    "iat": int(now.timestamp()),
                    "exp": int(expires.timestamp()),
                }
                token = jwt.encode(claims, self.key, algorithm="HS256")
                audit(
                    conn,
                    str(current["id"]),
                    "auth.login",
                    "session",
                    session,
                    correlation,
                )
        if denied:
            raise Problem(401, "invalid_credentials", "Usuário ou senha inválidos.")
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 1800,
            "expires_at": expires.isoformat().replace("+00:00", "Z"),
        }

    def authenticate(self, token: str) -> Principal:
        try:
            claims = decode_token(token, self.key)
        except (jwt.PyJWTError, ValueError):
            raise Problem(
                401, "invalid_session", "Sessão inválida ou expirada."
            ) from None
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    text("""SELECT u.*,s.expires_at FROM app.users u JOIN app.sessions s ON s.user_id=u.id
                WHERE u.id=:user AND s.id=:session AND u.enabled AND s.revoked_at IS NULL
                AND s.expires_at>clock_timestamp() AND u.auth_version=:version AND s.auth_version=u.auth_version AND u.role=:role"""),
                    {
                        "user": claims.sub,
                        "session": claims.jti,
                        "version": claims.auth_version,
                        "role": claims.role,
                    },
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Problem(401, "invalid_session", "Sessão inválida ou expirada.")
        return Principal(
            str(row["id"]),
            row["username"],
            row["role"],
            row["auth_version"],
            claims.jti,
            row["expires_at"],
        )

    def logout(self, principal: Principal, correlation: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE app.sessions SET revoked_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": principal.session_id},
            )
            audit(
                conn,
                principal.id,
                "auth.logout",
                "session",
                principal.session_id,
                correlation,
            )

    def ticket(self, principal: Principal, origin: str, correlation: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.engine.begin() as conn:
            inserted = conn.execute(
                text(
                    "INSERT INTO app.ws_tickets(token_hash,session_id,origin,expires_at) SELECT :hash,id,:origin,LEAST(expires_at,clock_timestamp()+interval '30 seconds') FROM app.sessions WHERE id=:session AND revoked_at IS NULL AND expires_at>clock_timestamp()"
                ),
                {
                    "hash": hashlib.sha256(token.encode()).hexdigest(),
                    "origin": origin,
                    "session": principal.session_id,
                },
            )
            if inserted.rowcount != 1:
                raise Problem(401, "invalid_session", "Sessão inválida ou expirada.")
            audit(
                conn,
                principal.id,
                "auth.ws_ticket",
                "session",
                principal.session_id,
                correlation,
            )
        return token

    def consume_ticket(self, token: str, origin: str) -> Principal:
        if not 32 <= len(token) <= 128:
            raise Problem(401, "invalid_ticket", "Ticket inválido ou expirado.")
        with self.engine.begin() as conn:
            row = (
                conn.execute(
                    text("""UPDATE app.ws_tickets t SET consumed_at=clock_timestamp() FROM app.sessions s,app.users u
                WHERE t.token_hash=:hash AND t.origin=:origin AND t.consumed_at IS NULL AND t.expires_at>clock_timestamp()
                AND s.id=t.session_id AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp()
                AND u.id=s.user_id AND u.enabled AND u.auth_version=s.auth_version
                RETURNING u.id,u.username,u.role,u.auth_version,s.id AS session_id,s.expires_at"""),
                    {
                        "hash": hashlib.sha256(token.encode()).hexdigest(),
                        "origin": origin,
                    },
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Problem(401, "invalid_ticket", "Ticket inválido ou expirado.")
        return Principal(
            str(row["id"]),
            row["username"],
            row["role"],
            row["auth_version"],
            str(row["session_id"]),
            row["expires_at"],
        )

    @staticmethod
    def require_admin(principal: Principal) -> None:
        if principal.role != "administrador":
            raise Problem(403, "role_forbidden", "Esta operação exige administrador.")

    def create_user(
        self,
        principal: Principal,
        username: str,
        password: str,
        role: Role,
        correlation: str,
    ) -> dict:
        self.require_admin(principal)
        hashed = hash_password(password, self.cost)
        identity = str(uuid4())
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO app.users(id,username,password_hash,role) VALUES(:id,:name,:hash,:role)"
                    ),
                    {"id": identity, "name": username, "hash": hashed, "role": role},
                )
                audit(
                    conn,
                    principal.id,
                    "user.created",
                    "user",
                    identity,
                    correlation,
                    {"role": role},
                )
        except IntegrityError:
            raise Problem(
                409, "username_exists", "Nome de usuário indisponível."
            ) from None
        return {"id": identity, "username": username, "role": role, "enabled": True}

    def update_user(
        self, principal: Principal, identity: str, changes: dict, correlation: str
    ) -> None:
        self.require_admin(principal)
        hashed = (
            hash_password(changes["password"], self.cost)
            if "password" in changes
            else None
        )
        with self.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(734119)"))
            current = (
                conn.execute(
                    text("SELECT * FROM app.users WHERE id=:id FOR UPDATE"),
                    {"id": identity},
                )
                .mappings()
                .first()
            )
            if current is None:
                raise Problem(404, "user_not_found", "Usuário não encontrado.")
            role = changes.get("role", current["role"])
            enabled = changes.get("enabled", current["enabled"])
            if (
                current["role"] == "administrador"
                and current["enabled"]
                and (role != "administrador" or not enabled)
            ):
                count = conn.execute(
                    text(
                        "SELECT count(*) FROM app.users WHERE role='administrador' AND enabled"
                    )
                ).scalar_one()
                if count <= 1:
                    raise Problem(
                        409,
                        "last_administrator",
                        "Mantenha pelo menos um administrador ativo.",
                    )
            conn.execute(
                text(
                    "UPDATE app.users SET role=:role,enabled=:enabled,password_hash=COALESCE(:hash,password_hash),auth_version=auth_version+1,updated_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": identity, "role": role, "enabled": enabled, "hash": hashed},
            )
            conn.execute(
                text(
                    "UPDATE app.sessions SET revoked_at=clock_timestamp() WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"id": identity},
            )
            audit(
                conn,
                principal.id,
                "user.updated",
                "user",
                identity,
                correlation,
                {
                    "role": role,
                    "enabled": enabled,
                    "password_changed": hashed is not None,
                },
            )
