"""Atomic simulated state + command ledger + durable MQTT spool in SQLite."""

import hashlib
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from smartfan_common.contracts_v2 import (
    EVENT_V2_ADAPTER,
    CommandRequestedV2,
    EventV2,
    command_expired_v2,
    parse_event_v2,
    serialize_event_v2,
)
from smartfan_common.routing_v2 import mqtt_topic_v2

from .physics import PlantConfig, PlantState, advance


class SpoolFull(RuntimeError):
    pass


class SimulatorDevice:
    def __init__(
        self,
        path: Path,
        config: PlantConfig | None = None,
        device_id: str = "ac_01",
        zone: str = "quarto",
        quota_bytes: int = 512 * 1024**2,
    ):
        if (
            not all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", v) for v in (device_id, zone))
            or quota_bytes < 1
        ):
            raise ValueError("Invalid simulator identity or quota")
        self.config = config or PlantConfig()
        self.device_id, self.zone, self.quota_bytes = device_id, zone, quota_bytes
        self.boot_id = str(uuid4())
        self._lock = threading.RLock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            path, check_same_thread=False, isolation_level=None, timeout=3
        )
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=3000;
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS spool(id TEXT PRIMARY KEY,topic TEXT NOT NULL,payload BLOB NOT NULL,retain INTEGER NOT NULL,last_sent REAL NOT NULL DEFAULT 0,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,ack BLOB NOT NULL,created REAL NOT NULL);
        """)
        with self._transaction() as conn:
            state = self._state(conn)
            if state.compressor_on:
                state.last_off_epoch = datetime.now(UTC).timestamp()
            state.compressor_on = state.condenser_fan_on = False
            state.reason_code = "boot_safe_off"
            self._save(conn, state)
            conn.execute("INSERT OR REPLACE INTO metadata VALUES('sequence','0')")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
                self.db.execute("COMMIT")
            except BaseException:
                if self.db.in_transaction:
                    self.db.execute("ROLLBACK")
                raise

    def _state(self, conn: sqlite3.Connection) -> PlantState:
        row = conn.execute("SELECT value FROM metadata WHERE key='state'").fetchone()
        return (
            PlantState.model_validate_json(row[0])
            if row
            else PlantState(damage=self.config.initial_damage)
        )

    def _save(self, conn: sqlite3.Connection, state: PlantState) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO metadata VALUES('state',?)",
            (state.model_dump_json(),),
        )

    def state(self) -> PlantState:
        with self._transaction() as conn:
            return self._state(conn)

    def _event(
        self,
        conn: sqlite3.Connection,
        kind: str,
        content: dict[str, Any],
        now: datetime,
        correlation: str | None = None,
        causation: str | None = None,
    ) -> EventV2:
        if now.tzinfo is None:
            raise ValueError("Simulator clock must be timezone aware")
        row = conn.execute("SELECT value FROM metadata WHERE key='sequence'").fetchone()
        sequence = int(row[0]) + 1
        conn.execute(
            "UPDATE metadata SET value=? WHERE key='sequence'", (str(sequence),)
        )
        return EVENT_V2_ADAPTER.validate_python(
            {
                "id": str(uuid4()),
                "schema_version": "2.1" if kind == "device.state" else "2.0",
                "timestamp": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "tipo": kind,
                "dispositivo": self.device_id,
                "correlation_id": correlation,
                "metadata": {
                    "producer": "simulator",
                    "causation_id": causation,
                    "boot_id": self.boot_id,
                    "sequence": sequence,
                    "zone": self.zone,
                    "equipment_type": "ac_split_onoff",
                    "clock_scale": 1,
                },
                "conteudo": content,
            }
        )

    def _queue(
        self, conn: sqlite3.Connection, event: EventV2, raw: bytes | None = None
    ) -> bytes:
        body = raw if raw is not None else serialize_event_v2(event)
        existing = conn.execute(
            "SELECT payload FROM spool WHERE id=?", (event.id,)
        ).fetchone()
        if existing:
            if bytes(existing[0]) != body:
                raise ValueError("Spool identity conflict")
            return body
        used = conn.execute(
            "SELECT COALESCE(SUM(length(payload)+256),0) FROM spool"
        ).fetchone()[0]
        if used + len(body) + 256 > self.quota_bytes:
            raise SpoolFull("Pause simulation: pending spool quota reached")
        conn.execute(
            "INSERT INTO spool(id,topic,payload,retain,created) VALUES(?,?,?,?,?)",
            (
                event.id,
                mqtt_topic_v2(event),
                body,
                event.tipo in ("device.state", "device.availability"),
                datetime.now(UTC).timestamp(),
            ),
        )
        return body

    @staticmethod
    def _actuators(state: PlantState) -> dict[str, bool]:
        return {
            "compressor_on": state.compressor_on,
            "condenser_fan_on": state.condenser_fan_on,
        }

    def availability(
        self, now: datetime, status: Literal["online", "offline"], *, will: bool = False
    ) -> bytes:
        with self._transaction() as conn:
            event = self._event(
                conn,
                "device.availability",
                {
                    "status": status,
                    "reason_code": "last_will"
                    if will
                    else "connected"
                    if status == "online"
                    else "shutdown",
                },
                now,
            )
            return serialize_event_v2(event) if will else self._queue(conn, event)

    def report_state(self, now: datetime) -> bytes:
        with self._transaction() as conn:
            return self._state_report(conn, now)

    def _state_report(self, conn: sqlite3.Connection, now: datetime) -> bytes:
        state = self._state(conn)
        return self._queue(
            conn,
            self._event(
                conn,
                "device.state",
                {
                    "actuators": self._actuators(state),
                    "mode": state.mode,
                    "manual_cooling_block": state.manual_cooling_block,
                    "reason_code": state.reason_code,
                    "last_revision": state.last_revision,
                },
                now,
            ),
        )

    def sample(self, now: datetime, elapsed: float = 2) -> bytes:
        with self._transaction() as conn:
            state = self._state(conn)
            readings = advance(state, self.config, now.timestamp(), elapsed)
            event = self._event(
                conn,
                "telemetry.sampled",
                {
                    "readings": readings,
                    "actuators": self._actuators(state),
                    "quality": {"missing_fields": []},
                },
                now,
            )
            raw = self._queue(conn, event)
            self._save(conn, state)
            return raw

    def command(self, raw: bytes, now: datetime) -> bytes:
        command = parse_event_v2(raw)
        if (
            not isinstance(command, CommandRequestedV2)
            or command.dispositivo != self.device_id
        ):
            raise ValueError("Command is not addressed to this simulator")
        digest = hashlib.sha256(raw).hexdigest()
        with self._transaction() as conn:
            previous = conn.execute(
                "SELECT sha256,ack FROM commands WHERE id=?", (command.id,)
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise ValueError("Command identity conflict")
                ack_bytes = bytes(previous[1])
                self._queue(conn, parse_event_v2(ack_bytes), ack_bytes)
                self._state_report(conn, now)
                return ack_bytes
            state = self._state(conn)
            kind, reason = "command.applied", "applied"
            content = command.conteudo
            if content.target_boot_id != self.boot_id:
                kind, reason = "command.rejected", "boot_mismatch"
            elif command_expired_v2(command, now):
                kind, reason = "command.expired", "expired"
            elif content.revision <= state.last_revision:
                kind, reason = "command.rejected", "stale_revision"
            elif content.desired.compressor_on and (
                state.thermal_lock or state.case_temp_c >= 85
            ):
                kind, reason = "command.rejected", "thermal_lockout"
            elif (
                content.desired.compressor_on
                and not state.compressor_on
                and now.timestamp() - state.last_off_epoch < 180
            ):
                kind, reason = "command.rejected", "restart_delay"
            elif (
                state.manual_cooling_block
                and command.metadata.producer == "control"
                and content.desired.condenser_fan_on
            ):
                kind, reason = "command.rejected", "manual_block"
            if content.target_boot_id == self.boot_id:
                state.last_revision = max(state.last_revision, content.revision)
            if kind == "command.applied":
                if state.compressor_on and not content.desired.compressor_on:
                    state.last_off_epoch = now.timestamp()
                state.compressor_on = content.desired.compressor_on
                state.condenser_fan_on = content.desired.condenser_fan_on
                state.mode = content.mode
                if command.metadata.producer == "api":
                    state.manual_cooling_block = (
                        content.mode == "manual"
                        and not content.desired.condenser_fan_on
                    )
                state.reason_code = content.reason_code
            ack = self._event(
                conn,
                kind,
                {
                    "command_id": command.id,
                    "revision": content.revision,
                    "observed": self._actuators(state),
                    "reason_code": reason,
                },
                now,
                command.correlation_id,
                command.id,
            )
            body = self._queue(conn, ack)
            self._save(conn, state)
            self._state_report(conn, now)
            conn.execute(
                "INSERT INTO commands VALUES(?,?,?,?)",
                (command.id, digest, body, now.timestamp()),
            )
            return body

    def receipt(self, event_id: str) -> None:
        with self._transaction() as conn:
            conn.execute("DELETE FROM spool WHERE id=?", (event_id,))

    def pending(
        self, now_epoch: float, limit: int = 32
    ) -> list[tuple[str, str, bytes, bool]]:
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT id,topic,payload,retain FROM spool WHERE last_sent<=? ORDER BY created,id LIMIT ?",
                (now_epoch - 5, max(1, min(limit, 64))),
            ).fetchall()
            return [
                (str(row[0]), str(row[1]), bytes(row[2]), bool(row[3])) for row in rows
            ]

    def sent(self, event_id: str, now_epoch: float) -> None:
        with self._transaction() as conn:
            conn.execute(
                "UPDATE spool SET last_sent=? WHERE id=?", (now_epoch, event_id)
            )

    def purge_ledger(self, now_epoch: float) -> None:
        with self._transaction() as conn:
            conn.execute(
                "DELETE FROM commands WHERE created<?", (now_epoch - 7 * 86400,)
            )

    def close(self) -> None:
        with self._lock:
            self.db.close()
