"""PostgreSQL inbox/outbox with atomic decisions, quotas and fencing.

ACK upstream only after this transaction (including any caller transaction)
commits. Never hold a SQL transaction open while waiting on an external broker.
"""

import base64
import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, text

from .database import ROLES

Table = Literal["inbox", "outbox"]


class LostLease(RuntimeError):
    pass


class QuotaExceeded(RuntimeError):
    pass


class IdentityConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Outbound:
    event_id: str
    payload: bytes
    exchange: str
    routing_key: str


@dataclass(frozen=True)
class Delivery:
    owner: str
    table: Table
    event_id: str
    payload: bytes
    generation: int
    attempts: int
    route: str
    exchange: str
    observed_at: datetime


def backoff_seconds(attempt: int, jitter: float = 0) -> float:
    if attempt < 1 or not -0.2 <= jitter <= 0.2:
        raise ValueError("Invalid retry parameters")
    return (1, 5, 30)[min(attempt - 1, 2)] * (1 + jitter)


def _uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Expected canonical UUID")
    return value


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("Invalid reason/owner identifier")
    return value


class DurableStore:
    def __init__(self, engine: Engine, owner: str, quota_bytes: int = 1024**3):
        if owner not in ROLES or quota_bytes < 1:
            raise ValueError("Invalid store owner/quota")
        self.engine, self.owner, self.quota_bytes = engine, owner, quota_bytes

    @contextmanager
    def transaction(self, connection: Connection | None = None) -> Iterator[Connection]:
        if connection is not None:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:owner),734114)"), {"owner": self.owner}
            )
            yield connection
        else:
            with self.engine.begin() as conn:
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:owner),734114)"),
                    {"owner": self.owner},
                )
                yield conn

    def _now(self, conn: Connection) -> datetime:
        return cast(datetime, conn.execute(text("SELECT clock_timestamp()")).scalar_one())

    def _capacity(self, conn: Connection, extra: int) -> None:
        used = conn.execute(
            text("""
            SELECT COALESCE(sum(n),0) FROM (
              SELECT octet_length(payload)+256 n FROM transport.inbox WHERE owner=:owner AND state IN ('pending','working')
              UNION ALL SELECT octet_length(payload)+256 FROM transport.outbox WHERE owner=:owner AND state IN ('pending','working')
              UNION ALL SELECT octet_length(payload)+256 FROM transport.failures WHERE owner=:owner
            ) sizes
        """),
            {"owner": self.owner},
        ).scalar_one()
        if int(used) + extra + 256 > self.quota_bytes:
            raise QuotaExceeded("Durable pending-data quota exhausted; pause acceptance")

    def _enqueue(self, conn: Connection, outgoing: Outbound) -> None:
        _uuid(outgoing.event_id)
        if not outgoing.payload or len(outgoing.payload) > 32768:
            raise ValueError("Invalid outgoing payload size")
        if (
            not outgoing.exchange
            or len(outgoing.exchange) > 128
            or not outgoing.routing_key
            or len(outgoing.routing_key) > 256
        ):
            raise ValueError("Invalid outgoing route")
        digest = hashlib.sha256(outgoing.payload).hexdigest()
        old = (
            conn.execute(
                text(
                    "SELECT sha256,exchange,routing_key FROM transport.outbox WHERE owner=:owner AND event_id=:id"
                ),
                {"owner": self.owner, "id": outgoing.event_id},
            )
            .mappings()
            .first()
        )
        if old:
            if (old["sha256"], old["exchange"], old["routing_key"]) != (
                digest,
                outgoing.exchange,
                outgoing.routing_key,
            ):
                raise IdentityConflict("Outgoing identity already has different bytes/route")
            return
        self._capacity(conn, len(outgoing.payload))
        conn.execute(
            text("""INSERT INTO transport.outbox(owner,event_id,sha256,payload,exchange,routing_key)
            VALUES(:owner,:id,:hash,:body,:exchange,:key)"""),
            {
                "owner": self.owner,
                "id": outgoing.event_id,
                "hash": digest,
                "body": outgoing.payload,
                "exchange": outgoing.exchange,
                "key": outgoing.routing_key,
            },
        )

    def enqueue(self, outgoing: Outbound, connection: Connection | None = None) -> None:
        with self.transaction(connection) as conn:
            self._enqueue(conn, outgoing)

    def receive(
        self,
        event_id: str,
        payload: bytes,
        route: str,
        *,
        outgoing: Sequence[Outbound] = (),
        connection: Connection | None = None,
    ) -> Literal["accepted", "duplicate", "conflict"]:
        _uuid(event_id)
        if not payload or len(payload) > 32768 or not route or len(route) > 256:
            raise ValueError("Invalid incoming payload/route")
        digest = hashlib.sha256(payload).hexdigest()
        with self.transaction(connection) as conn:
            old = (
                conn.execute(
                    text(
                        "SELECT sha256,route FROM transport.inbox WHERE owner=:owner AND event_id=:id"
                    ),
                    {"owner": self.owner, "id": event_id},
                )
                .mappings()
                .first()
            )
            if old:
                if old["sha256"] != digest or old["route"] != route:
                    self._failure(conn, event_id, payload, route, "identity_conflict", 0)
                    return "conflict"
                return "duplicate"
            self._capacity(conn, len(payload))
            conn.execute(
                text("""INSERT INTO transport.inbox(owner,event_id,sha256,payload,route)
                VALUES(:owner,:id,:hash,:body,:route)"""),
                {
                    "owner": self.owner,
                    "id": event_id,
                    "hash": digest,
                    "body": payload,
                    "route": route,
                },
            )
            for event in outgoing:
                self._enqueue(conn, event)
            return "accepted"

    def claim(self, table: Table = "inbox", lease_seconds: int = 30) -> Delivery | None:
        if table not in ("inbox", "outbox") or not 1 <= lease_seconds <= 300:
            raise ValueError("Invalid claim settings")
        with self.transaction() as conn:
            now = self._now(conn)
            row = (
                conn.execute(
                    text(f"""SELECT * FROM transport.{table}
                WHERE owner=:owner AND available_at<=:now AND
                (state='pending' OR (state='working' AND leased_until<=:now))
                ORDER BY available_at,event_id FOR UPDATE SKIP LOCKED LIMIT 1"""),
                    {"owner": self.owner, "now": now},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            if (
                table == "inbox"
                and row["attempts"] >= 5
                and not row.get("dependency_failure", False)
            ):
                self._failure(
                    conn,
                    str(row["event_id"]),
                    bytes(row["payload"]),
                    row["route"],
                    "attempts_exhausted",
                    row["attempts"],
                )
                conn.execute(
                    text(
                        "UPDATE transport.inbox SET state='failed',finished_at=:now WHERE owner=:owner AND event_id=:id"
                    ),
                    {"owner": self.owner, "id": row["event_id"], "now": now},
                )
                return None
            conn.execute(
                text(f"""UPDATE transport.{table} SET state='working',attempts=attempts+1,
                generation=generation+1,leased_until=:expiry WHERE owner=:owner AND event_id=:id"""),
                {
                    "owner": self.owner,
                    "id": row["event_id"],
                    "expiry": now + timedelta(seconds=lease_seconds),
                },
            )
            return Delivery(
                self.owner,
                table,
                str(row["event_id"]),
                bytes(row["payload"]),
                row["generation"] + 1,
                row["attempts"] + 1,
                row.get("route", row.get("routing_key", "")),
                row.get("exchange", ""),
                row["observed_at"],
            )

    def claim_publication(self, lease_seconds: int = 30) -> Delivery | None:
        rows = self.claim_publications(limit=1, lease_seconds=lease_seconds)
        return rows[0] if rows else None

    def claim_publications(self, limit: int = 8, lease_seconds: int = 30) -> list[Delivery]:
        """One transaction claims a bounded, ordered batch; each row keeps its fence."""
        if not 1 <= lease_seconds <= 300 or not 1 <= limit <= 32:
            raise ValueError("Invalid publication lease")
        with self.transaction() as conn:
            rows = (
                conn.execute(
                    text("""WITH moment AS MATERIALIZED (SELECT clock_timestamp() AS at),
                candidate AS (
                  SELECT event_id FROM transport.outbox,moment
                  WHERE owner=:owner AND available_at<=moment.at
                    AND (state='pending' OR (state='working' AND leased_until<=moment.at))
                  ORDER BY available_at,event_id FOR UPDATE OF outbox SKIP LOCKED LIMIT :limit
                )
                UPDATE transport.outbox AS o SET state='working',attempts=o.attempts+1,
                  generation=o.generation+1,leased_until=(SELECT at FROM moment)+:seconds*interval '1 second'
                FROM candidate WHERE o.owner=:owner AND o.event_id=candidate.event_id
                RETURNING o.*"""),
                    {"owner": self.owner, "seconds": lease_seconds, "limit": limit},
                )
                .mappings()
                .all()
            )
            return [
                Delivery(
                    self.owner,
                    "outbox",
                    str(row["event_id"]),
                    bytes(row["payload"]),
                    row["generation"],
                    row["attempts"],
                    row["routing_key"],
                    row["exchange"],
                    row["observed_at"],
                )
                for row in sorted(rows, key=lambda row: (row["available_at"], str(row["event_id"])))
            ]

    def finish_published(self, delivery: Delivery) -> None:
        self.finish_publications([delivery])

    def finish_publications(self, deliveries: Sequence[Delivery]) -> None:
        """Only after broker confirm: atomic generation/state/deadline check + finish.

        This path has no business callbacks. Inbox effects retain the two checks in
        finish(); a lost/expired publication lease still rolls back and may replay.
        """
        if not deliveries:
            return
        if len(deliveries) > 32 or any(
            delivery.owner != self.owner or delivery.table != "outbox" for delivery in deliveries
        ):
            raise LostLease("Publication belongs to another owner or table")
        with self.transaction() as conn:
            finished = conn.execute(
                text("""UPDATE transport.outbox AS o SET state='completed',finished_at=clock_timestamp(),leased_until=NULL
                FROM unnest(CAST(:ids AS uuid[]),CAST(:generations AS bigint[])) AS claimed(id,generation)
                WHERE o.owner=:owner AND o.event_id=claimed.id AND o.generation=claimed.generation
                  AND o.state='working' AND o.leased_until>clock_timestamp() RETURNING o.event_id"""),
                {
                    "owner": self.owner,
                    "ids": [delivery.event_id for delivery in deliveries],
                    "generations": [delivery.generation for delivery in deliveries],
                },
            ).all()
            if len(finished) != len(deliveries):
                raise LostLease("Publication lease was lost or expired")

    def _owned(self, conn: Connection, delivery: Delivery) -> datetime:
        if delivery.owner != self.owner or delivery.table not in ("inbox", "outbox"):
            raise LostLease("Delivery belongs to another owner")
        now = self._now(conn)
        owned = conn.execute(
            text(f"""SELECT 1 FROM transport.{delivery.table}
            WHERE owner=:owner AND event_id=:id AND generation=:generation
            AND state='working' AND leased_until>:now FOR UPDATE"""),
            {
                "owner": self.owner,
                "id": delivery.event_id,
                "generation": delivery.generation,
                "now": now,
            },
        ).first()
        if owned is None:
            raise LostLease("Delivery lease was lost or expired")
        return now

    def finish(
        self,
        delivery: Delivery,
        *,
        outgoing: Sequence[Outbound] = (),
        effects: Callable[[Connection], None] | None = None,
    ) -> None:
        with self.transaction() as conn:
            now = self._owned(conn, delivery)
            if effects is not None:
                effects(conn)
            for event in outgoing:
                self._enqueue(conn, event)
            now = self._owned(conn, delivery)
            conn.execute(
                text(f"""UPDATE transport.{delivery.table} SET state='completed',
                finished_at=:now,leased_until=NULL WHERE owner=:owner AND event_id=:id"""),
                {"owner": self.owner, "id": delivery.event_id, "now": now},
            )

    def renew(self, delivery: Delivery, lease_seconds: int = 30) -> bool:
        if not 1 <= lease_seconds <= 300:
            raise ValueError("Invalid delivery lease deadline")
        try:
            with self.transaction() as conn:
                now = self._owned(conn, delivery)
                conn.execute(
                    text(
                        f"UPDATE transport.{delivery.table} SET leased_until=:expiry WHERE owner=:owner AND event_id=:id"
                    ),
                    {
                        "owner": self.owner,
                        "id": delivery.event_id,
                        "expiry": now + timedelta(seconds=lease_seconds),
                    },
                )
            return True
        except LostLease:
            return False

    def retry(
        self,
        delivery: Delivery,
        reason_code: str,
        *,
        permanent: bool = False,
        jitter: float = 0,
        dependency_failure: bool = False,
    ) -> None:
        _identifier(reason_code)
        delay = backoff_seconds(delivery.attempts, jitter)
        with self.transaction() as conn:
            now = self._owned(conn, delivery)
            if permanent or (
                delivery.table == "inbox" and delivery.attempts >= 5 and not dependency_failure
            ):
                self._failure(
                    conn,
                    delivery.event_id,
                    delivery.payload,
                    delivery.route,
                    reason_code,
                    delivery.attempts,
                )
                state = "failed"
            else:
                state = "pending"
            conn.execute(
                text(
                    "UPDATE transport.inbox SET dependency_failure=:dependency WHERE owner=:owner AND event_id=:id"
                )
                if delivery.table == "inbox"
                else text("SELECT 1"),
                {"owner": self.owner, "id": delivery.event_id, "dependency": dependency_failure}
                if delivery.table == "inbox"
                else {},
            )
            conn.execute(
                text(f"""UPDATE transport.{delivery.table} SET state=:state,
                reason_code=:reason,available_at=:due,leased_until=NULL,finished_at=:finished
                WHERE owner=:owner AND event_id=:id"""),
                {
                    "owner": self.owner,
                    "id": delivery.event_id,
                    "state": state,
                    "reason": reason_code,
                    "due": now + timedelta(seconds=delay),
                    "finished": now if state == "failed" else None,
                },
            )

    def _failure(
        self,
        conn: Connection,
        event_id: str,
        payload: bytes,
        route: str,
        reason: str,
        attempts: int,
    ) -> str:
        digest = hashlib.sha256(payload).hexdigest()
        failure_id = str(uuid5(NAMESPACE_URL, f"{self.owner}:{event_id}:{digest}:{route}:{reason}"))
        existing = conn.execute(
            text("SELECT 1 FROM transport.failures WHERE owner=:owner AND failure_id=:id"),
            {"owner": self.owner, "id": failure_id},
        ).first()
        if existing:
            return failure_id
        self._capacity(conn, len(payload))
        conn.execute(
            text("""INSERT INTO transport.failures(owner,failure_id,event_id,sha256,payload,route,reason_code,attempts)
            VALUES(:owner,:id,:source,:hash,:body,:route,:reason,:attempts)"""),
            {
                "owner": self.owner,
                "id": failure_id,
                "source": event_id,
                "hash": digest,
                "body": payload,
                "route": route,
                "reason": reason,
                "attempts": attempts,
            },
        )
        now = self._now(conn).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        event = {
            "id": failure_id,
            "schema_version": "2.0",
            "timestamp": now,
            "tipo": "message.quarantined",
            "dispositivo": None,
            "correlation_id": None,
            "metadata": {"producer": self.owner, "causation_id": event_id},
            "conteudo": {
                "failure_id": failure_id,
                "owner": self.owner,
                "reason_code": reason,
                "original_sha256": digest,
                "original_bytes_b64": base64.b64encode(payload).decode()
                if len(payload) <= 16384
                else None,
                "original_ref": failure_id if len(payload) > 16384 else None,
                "original_route": route,
                "attempts": attempts,
            },
        }
        raw = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
        self._enqueue(conn, Outbound(failure_id, raw, "smartfan.dlx", "failure." + self.owner))
        return failure_id

    def quarantine(self, payload: bytes, route: str, reason_code: str) -> str:
        _identifier(reason_code)
        if len(payload) > 32768 or not route or len(route) > 256:
            raise ValueError("Invalid quarantine size/route")
        source = str(uuid5(NAMESPACE_URL, hashlib.sha256(payload).hexdigest()))
        with self.transaction() as conn:
            return self._failure(conn, source, payload, route, reason_code, 0)

    def counts(self) -> Mapping[str, int]:
        with self.engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT state,count(*) FROM transport.inbox WHERE owner=:owner GROUP BY state"
                ),
                {"owner": self.owner},
            )
            return {str(state): int(count) for state, count in result}

    def receipt_time(self, event_id: str) -> datetime | None:
        _uuid(event_id)
        with self.engine.connect() as conn:
            return cast(
                datetime | None,
                conn.execute(
                    text("SELECT observed_at FROM transport.receipts WHERE event_id=:id"),
                    {"id": event_id},
                ).scalar_one_or_none(),
            )

    def received_at(self, event_id: str, connection: Connection | None = None) -> datetime | None:
        _uuid(event_id)
        with self.transaction(connection) as conn:
            return cast(
                datetime | None,
                conn.execute(
                    text(
                        "SELECT observed_at FROM transport.inbox WHERE owner=:owner AND event_id=:id"
                    ),
                    {"owner": self.owner, "id": event_id},
                ).scalar_one_or_none(),
            )

    def pending_outbox(self) -> list[Mapping[str, Any]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT event_id,exchange,routing_key,state FROM transport.outbox WHERE owner=:owner AND state!='completed' ORDER BY observed_at LIMIT 100"
                ),
                {"owner": self.owner},
            ).mappings()
            return [{str(key): value for key, value in row.items()} for row in rows]

    def prune_terminal_payloads(self) -> None:
        """Privileged SQL function scopes retention to the authenticated DB role."""
        with self.engine.begin() as conn:
            conn.execute(text("SELECT transport.prune_terminals()"))
