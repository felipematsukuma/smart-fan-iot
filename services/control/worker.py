"""Atomic control consumer with original-source freshness and physical ACKs."""

from datetime import UTC, datetime
from uuid import uuid4

from smartfan_common.contracts_v2 import (
    CommandAckV2,
    CommandRequestedV2,
    InsightPredictedV2,
    TelemetrySampleV2,
    parse_event_v2,
    payload_sha256,
)
from smartfan_common.control import RuleConfig, thermostat
from smartfan_common.reliability.amqp import authenticated_publisher
from smartfan_common.reliability.store import DurableStore
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text

from .domain import CommandService, ControlError, record_audit


class Controller:
    def __init__(self, store: DurableStore):
        if store.owner != "control":
            raise ValueError("Control account required")
        self.store = store
        self.commands = CommandService(store)

    def receive(
        self, raw: bytes, route: str, user_id: str | None, message_id: str | None
    ) -> None:
        try:
            event = parse_event_v2(raw)
            if (
                not isinstance(
                    event, (TelemetrySampleV2, CommandAckV2, InsightPredictedV2)
                )
                or routing_key_v2(event)[1] != route
                or message_id != event.id
                or not authenticated_publisher(event, user_id)
            ):
                raise ValueError("Invalid control event provenance")
            with self.store.transaction() as conn:
                if isinstance(event, (TelemetrySampleV2, CommandAckV2)):
                    receipt = conn.execute(
                        text(
                            "SELECT observed_at,sha256 FROM transport.receipts WHERE event_id=:id"
                        ),
                        {"id": event.id},
                    ).first()
                    if receipt is None or receipt[1] != payload_sha256(raw):
                        raise ValueError("Unjournaled device event")
                if (
                    self.store.receive(event.id, raw, route, connection=conn)
                    != "accepted"
                ):
                    return
                now = datetime.now(UTC)
                if isinstance(event, CommandAckV2):
                    self.ack(conn, event, now)
                elif isinstance(event, TelemetrySampleV2):
                    self.sample(conn, event, now)
                # Prediction alert hysteresis is M13. This consumer stores the event
                # without letting a model directly actuate a compressor.
                conn.execute(
                    text(
                        "UPDATE transport.inbox SET state='completed',finished_at=clock_timestamp() WHERE owner='control' AND event_id=:id"
                    ),
                    {"id": event.id},
                )
        except ValueError:
            self.store.quarantine(raw, route[:256], "invalid_control_event")

    def sample(self, conn, event: TelemetrySampleV2, now: datetime) -> None:
        stamp = datetime.fromisoformat(event.timestamp)
        if not 0 <= (now - stamp).total_seconds() <= 6:
            return
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "command-device:" + event.dispositivo},
        )
        status = (
            conn.execute(
                text("SELECT * FROM transport.device_status WHERE device_id=:id"),
                {"id": event.dispositivo},
            )
            .mappings()
            .first()
        )
        registration = conn.execute(
            text("SELECT enabled,zone FROM app.device_registry WHERE id=:id"),
            {"id": event.dispositivo},
        ).first()
        if (
            not registration
            or not registration[0]
            or registration[1] != event.metadata.zone
            or not status
            or str(status["boot_id"]) != event.metadata.boot_id
        ):
            return
        previous = (
            conn.execute(
                text("SELECT * FROM app.control_observations WHERE device_id=:id"),
                {"id": event.dispositivo},
            )
            .mappings()
            .first()
        )
        if (
            previous
            and previous["boot_id"] == status["boot_id"]
            and (
                stamp <= previous["sampled_at"]
                or event.metadata.sequence <= previous["sequence"]
            )
        ):
            return
        same = previous is not None and previous["boot_id"] == status["boot_id"]
        compressor = event.conteudo.actuators.compressor_on
        old_comp = (
            previous["telemetry"]["actuators"]["compressor_on"] if same else False
        )
        off_at = previous["last_off_at"] if same else status["boot_seen_at"]
        on_at = previous["last_on_at"] if same else stamp
        if old_comp and not compressor:
            off_at = stamp
        if compressor and not old_comp:
            on_at = stamp
        conn.execute(
            text(
                "INSERT INTO app.control_observations(device_id,boot_id,sequence,sampled_at,source_id,telemetry,last_off_at,last_on_at) VALUES(:id,:boot,:sequence,:stamp,:source,CAST(:telemetry AS jsonb),:off,:on) ON CONFLICT(device_id) DO UPDATE SET boot_id=excluded.boot_id,sequence=excluded.sequence,sampled_at=excluded.sampled_at,source_id=excluded.source_id,telemetry=excluded.telemetry,last_off_at=excluded.last_off_at,last_on_at=excluded.last_on_at"
            ),
            {
                "id": event.dispositivo,
                "boot": event.metadata.boot_id,
                "sequence": event.metadata.sequence,
                "stamp": stamp,
                "source": event.id,
                "telemetry": event.conteudo.model_dump_json(),
                "off": off_at,
                "on": on_at,
            },
        )
        rule_data = conn.execute(
            text("SELECT configuration FROM app.rules WHERE device_id=:id"),
            {"id": event.dispositivo},
        ).scalar_one_or_none()
        if rule_data is None:
            return
        latest = conn.execute(
            text(
                "SELECT payload FROM app.commands WHERE device_id=:id AND status='confirmed' ORDER BY revision DESC LIMIT 1"
            ),
            {"id": event.dispositivo},
        ).scalar_one_or_none()
        last_command = parse_event_v2(bytes(latest)) if latest is not None else None
        manual_hold = (
            isinstance(last_command, CommandRequestedV2)
            and last_command.metadata.producer == "api"
            and last_command.conteudo.mode == "manual"
        )
        decision = thermostat(
            RuleConfig.model_validate(rule_data),
            now,
            indoor=event.conteudo.readings.indoor_temp_c,
            case=event.conteudo.readings.compressor_case_temp_c,
            compressor=compressor,
            fan=event.conteudo.actuators.condenser_fan_on,
            manual=manual_hold
            or status["mode"] == "manual"
            or status["manual_cooling_block"],
            seconds_off=(now - off_at).total_seconds(),
            seconds_on=(now - on_at).total_seconds(),
        )
        if decision:
            try:
                self.commands.create(
                    conn,
                    event.dispositivo,
                    now,
                    reason=decision[2],
                    actor=None,
                    correlation=event.correlation_id or str(uuid4()),
                    desired=decision[:2],
                )
            except ControlError:
                pass  # Pending/offline/watermark is a domain state, not a failed delivery.

    @staticmethod
    def ack(conn, event: CommandAckV2, now: datetime) -> None:
        row = (
            conn.execute(
                text("SELECT * FROM app.commands WHERE id=:id FOR UPDATE"),
                {"id": event.conteudo.command_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            return
        command = parse_event_v2(bytes(row["payload"]))
        if (
            not isinstance(command, CommandRequestedV2)
            or command.dispositivo != event.dispositivo
            or command.conteudo.revision != event.conteudo.revision
            or (
                event.tipo == "command.applied"
                and (
                    command.conteudo.target_boot_id != event.metadata.boot_id
                    or command.conteudo.desired.model_dump()
                    != event.conteudo.observed.model_dump()
                )
            )
        ):
            raise ValueError("Conflicting physical ACK")
        if row["ack_event_id"] is not None:
            if str(row["ack_event_id"]) != event.id:
                raise ValueError("Conflicting physical ACK identity")
            return
        result = "confirmed" if event.tipo == "command.applied" else "failed"
        conn.execute(
            text(
                "UPDATE app.commands SET status=:status,result=:result,observed=CAST(:observed AS jsonb),ack_event_id=:ack,execution_unknown=false,updated_at=:now WHERE id=:id"
            ),
            {
                "status": result,
                "result": event.conteudo.reason_code,
                "observed": event.conteudo.observed.model_dump_json(),
                "ack": event.id,
                "now": now,
                "id": row["id"],
            },
        )
        record_audit(
            conn,
            str(row["actor_user_id"]) if row["actor_user_id"] else None,
            "command." + result,
            str(row["id"]),
            str(row["correlation_id"]),
            {
                "late_ack": row["execution_unknown"],
                "reason": event.conteudo.reason_code,
            },
        )
