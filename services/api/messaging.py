"""Bounded read-only management API and allowlisted failure previews; no queue gets."""

import base64
import json
import math
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from smartfan_common.contracts_v2 import TelemetrySampleV2, parse_event_v2
from smartfan_common.routing_v2 import QUEUES_V2
from sqlalchemy import Engine, text

from .errors import Problem


def bounded_number(value, integer: bool = False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        return 0
    return min(int(value) if integer else float(value), 10**12)


class Management:
    def __init__(self, password_file: Path):
        self._header = (
            "Basic "
            + base64.b64encode(
                ("api-monitor:" + password_file.read_text().strip()).encode()
            ).decode()
        )
        self._lock = threading.Lock()
        self._cached: dict | None = None
        self._until = 0.0

    def snapshot(self) -> dict:
        with self._lock:
            if self._cached is not None and time.monotonic() < self._until:
                return self._cached
            request = urllib.request.Request(
                "http://rabbitmq:15672/api/queues/%2Fsmartfan",
                headers={"Authorization": self._header},
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError("Management response exceeds budget")
                rows = json.loads(raw)
                if not isinstance(rows, list):
                    raise TypeError("Invalid queue list")
                known = {item.name: item for item in QUEUES_V2}
                queues = []
                for row in rows:
                    name = row.get("name") if isinstance(row, dict) else None
                    if name not in known:
                        continue
                    spec = known[name]
                    stats = row.get("message_stats") or {}

                    def rate(key, stats=stats):
                        return bounded_number(
                            (stats.get(key + "_details") or {}).get("rate", 0)
                        )

                    queues.append(
                        {
                            "name": spec.name,
                            "consumer_service": spec.consumer,
                            "messages_ready": bounded_number(
                                row.get("messages_ready", 0), True
                            ),
                            "messages_unacknowledged": bounded_number(
                                row.get("messages_unacknowledged", 0), True
                            ),
                            "consumers": bounded_number(row.get("consumers", 0), True),
                            "publish_rate": rate("publish"),
                            "delivery_rate": rate("deliver_get"),
                            "durable": row.get("durable") is True,
                            "type": "quorum"
                            if row.get("type") == "quorum"
                            else "unexpected",
                            "state": "running"
                            if row.get("state") == "running"
                            else "unavailable",
                        }
                    )
                if len(queues) != len(known):
                    raise ValueError("Required queues missing")
            except (OSError, ValueError, TypeError, AttributeError):
                raise Problem(
                    503,
                    "messaging_unavailable",
                    "Mensageria temporariamente indisponível.",
                ) from None
            self._cached = {
                "sampled_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "queues": sorted(queues, key=lambda item: item["name"]),
                "source": "rabbitmq_management",
                "cache_seconds": 2,
            }
            self._until = time.monotonic() + 2
            return self._cached


class FailureJournal:
    def __init__(self, engine: Engine):
        self.engine = engine

    def page(self, limit: int = 50, before: UUID | None = None) -> dict:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT f.*,coalesce((SELECT count(*) FROM app.failure_replays r WHERE r.failure_id=f.failure_id),0) AS replay_count FROM app.failure_journal f WHERE (:before IS NULL OR (f.created_at,f.failure_id)<(SELECT created_at,failure_id FROM app.failure_journal WHERE failure_id=CAST(:before AS uuid))) ORDER BY f.created_at DESC,f.failure_id DESC LIMIT :limit"
                    ),
                    {"before": str(before) if before else None, "limit": limit + 1},
                )
                .mappings()
                .all()
            )
            devices = set(conn.execute(text("SELECT id FROM app.devices")).scalars())
        owners = {
            item.consumer for item in QUEUES_V2 if item.consumer != "administrator"
        }
        items = []
        reasons = {
            "attempts_exhausted",
            "invalid_device_event",
            "invalid_device_ack",
            "invalid_command_origin",
            "invalid_control_event",
            "invalid_api_event",
            "invalid_point_identity",
            "influx_rejected_point",
            "influx_unavailable",
            "invalid_event",
            "invalid_source",
            "identity_conflict",
        }
        for row in rows[:limit]:
            preview = {}
            valid_telemetry = False
            try:
                event = parse_event_v2(bytes(row["payload"]))
                preview = {
                    "type": event.tipo,
                    "producer": event.metadata.producer,
                    "device_id": event.dispositivo
                    if event.dispositivo in devices
                    else None,
                    "timestamp": event.timestamp,
                }
                valid_telemetry = isinstance(event, TelemetrySampleV2)
            except (ValueError, TypeError):
                pass
            items.append(
                {
                    "id": str(row["failure_id"]),
                    "source_event_id": str(row["event_id"]),
                    "owner": row["owner"] if row["owner"] in owners else "unknown",
                    "reason_code": row["reason_code"]
                    if row["reason_code"] in reasons
                    else "quarantined",
                    "attempts": row["attempts"],
                    "created_at": row["created_at"],
                    "delivery_state": row["delivery_state"],
                    "preview": preview,
                    "replay_count": row["replay_count"],
                    "can_replay": row["owner"] == "writer"
                    and row["delivery_state"] == "failed"
                    and valid_telemetry
                    and row["replay_count"] < 3,
                }
            )
        return {
            "items": items,
            "next_cursor": str(rows[limit - 1]["failure_id"])
            if len(rows) > limit
            else None,
            "note": "Prévia do journal durável; consultar não lê nem confirma mensagens da DLQ.",
        }

    def replay(
        self, identity: UUID, request_id: UUID, actor: str, correlation: str
    ) -> dict:
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT app.replay_writer_failure(:id,:request,:actor,:correlation)"
                ),
                {
                    "id": str(identity),
                    "request": str(request_id),
                    "actor": actor,
                    "correlation": correlation,
                },
            ).scalar_one()
        if result not in ("requested", "already_requested"):
            raise Problem(
                409,
                result,
                "Falha não elegível para reprocessamento. Comandos exigem nova intenção explícita.",
            )
        return {
            "failure_id": str(identity),
            "request_id": str(request_id),
            "status": result,
            "note": "Entrada original recolocada na inbox do writer; bytes, ID e horário preservados.",
        }
