"""One serialized intention per device; broker confirmation never means actuation."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from smartfan_common.contracts_v2 import CommandRequestedV2, serialize_event_v2
from smartfan_common.control import CommandIntent
from smartfan_common.reliability.store import DurableStore, Outbound
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import Connection, text


class ControlError(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(code)


def record_audit(
    conn: Connection,
    actor: str | None,
    action: str,
    identity: str,
    correlation: str,
    details: dict,
) -> None:
    conn.execute(
        text(
            "INSERT INTO app.audit(id,actor_user_id,action,entity_type,entity_id,correlation_id,details,outcome) VALUES(:id,:actor,:action,'command',:entity,:correlation,CAST(:details AS jsonb),'success')"
        ),
        {
            "id": str(uuid4()),
            "actor": actor,
            "action": action,
            "entity": identity,
            "correlation": correlation,
            "details": json.dumps(details),
        },
    )


PUBLIC_COLUMNS = "id,device_id,revision,boot_id,producer,reason_code,status,result,ack_event_id,observed,execution_unknown,expires_at,created_at,updated_at"


def public_command(row) -> dict:
    return {
        key: str(value)
        if key in ("id", "boot_id", "ack_event_id") and value is not None
        else value
        for key, value in dict(row).items()
        if key in PUBLIC_COLUMNS.split(",")
    }


class CommandService:
    def __init__(self, store: DurableStore):
        if store.owner not in ("api", "control"):
            raise ValueError("Commands require api/control account")
        self.store = store

    @staticmethod
    def expire(conn: Connection, now: datetime) -> None:
        rows = conn.execute(
            text(
                "UPDATE app.commands SET status='failed',result='ack_timeout',execution_unknown=true,updated_at=:now WHERE status='pending' AND expires_at+:grace<:now RETURNING id,actor_user_id,correlation_id"
            ),
            {"now": now, "grace": timedelta(seconds=5)},
        ).all()
        for row in rows:
            record_audit(
                conn,
                str(row[1]) if row[1] else None,
                "command.unconfirmed",
                str(row[0]),
                str(row[2]),
                {"execution_unknown": True},
            )

    def manual(
        self, identity: str, body: CommandIntent, actor: str, key: str, correlation: str
    ) -> dict:
        digest = hashlib.sha256(
            json.dumps(
                {"device": identity, **body.model_dump()}, sort_keys=True
            ).encode()
        ).hexdigest()
        with self.store.transaction() as conn:
            # Key lock precedes device lock: the same key cannot create two devices' intents.
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": "command-key:" + actor + ":" + key},
            )
            previous = (
                conn.execute(
                    text(
                        "SELECT * FROM app.commands WHERE actor_user_id=:actor AND idempotency_key=:key"
                    ),
                    {"actor": actor, "key": key},
                )
                .mappings()
                .first()
            )
            if previous:
                if previous["request_hash"] != digest:
                    raise ControlError(
                        "idempotency_conflict",
                        "Chave de idempotência já usada com outro pedido.",
                    )
                return public_command(previous)
            now = datetime.now(UTC)
            command = self.create(
                conn,
                identity,
                now,
                reason="manual_" + body.action,
                actor=actor,
                correlation=correlation,
                manual=body.action,
            )
            conn.execute(
                text(
                    "UPDATE app.commands SET idempotency_key=:key,request_hash=:hash WHERE id=:id"
                ),
                {"key": key, "hash": digest, "id": command.id},
            )
            row = (
                conn.execute(
                    text("SELECT * FROM app.commands WHERE id=:id"), {"id": command.id}
                )
                .mappings()
                .one()
            )
            return public_command(row)

    def create(
        self,
        conn: Connection,
        identity: str,
        now: datetime,
        *,
        reason: str,
        actor: str | None,
        correlation: str,
        manual: str | None = None,
        desired: tuple[bool, bool] | None = None,
    ) -> CommandRequestedV2:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "command-device:" + identity},
        )
        device = conn.execute(
            text("SELECT zone,enabled FROM app.device_registry WHERE id=:id"),
            {"id": identity},
        ).first()
        if device is None or not device[1]:
            raise ControlError("device_disabled", "Dispositivo ausente ou desativado.")
        if conn.execute(
            text("SELECT 1 FROM app.commands WHERE device_id=:id AND status='pending'"),
            {"id": identity},
        ).first():
            raise ControlError(
                "command_pending", "Aguarde a confirmação da intenção anterior."
            )
        status = (
            conn.execute(
                text("SELECT * FROM transport.device_status WHERE device_id=:id"),
                {"id": identity},
            )
            .mappings()
            .first()
        )
        observed = (
            conn.execute(
                text("SELECT * FROM app.control_observations WHERE device_id=:id"),
                {"id": identity},
            )
            .mappings()
            .first()
        )
        if (
            status is None
            or observed is None
            or status["last_revision"] is None
            or status["boot_id"] != observed["boot_id"]
            or not 0 <= (now - observed["sampled_at"]).total_seconds() <= 6
            or not status["last_sample_at"]
            or not 0 <= (now - status["last_sample_at"]).total_seconds() <= 6
        ):
            raise ControlError(
                "device_not_fresh",
                "Sem leitura recente e boot/revisão confirmados do aparelho.",
            )
        actuators = observed["telemetry"]["actuators"]
        if manual is not None:
            desired = (
                bool(actuators["compressor_on"]) if manual != "fan_off" else False,
                manual != "fan_off",
            )
        assert desired is not None
        if desired[0] and not desired[1]:
            raise ControlError(
                "unsafe_actuators", "Compressor exige ventilador do condensador."
            )
        conn.execute(
            text(
                "INSERT INTO app.command_sequences(device_id,last_revision) VALUES(:id,:revision) ON CONFLICT(device_id) DO UPDATE SET last_revision=GREATEST(command_sequences.last_revision,excluded.last_revision-1)+1"
            ),
            {"id": identity, "revision": status["last_revision"] + 1},
        )
        revision = conn.execute(
            text("SELECT last_revision FROM app.command_sequences WHERE device_id=:id"),
            {"id": identity},
        ).scalar_one()
        command_id = str(uuid4())
        command = CommandRequestedV2.model_validate(
            {
                "id": command_id,
                "schema_version": "2.1",
                "timestamp": now.isoformat().replace("+00:00", "Z"),
                "tipo": "command.requested",
                "dispositivo": identity,
                "correlation_id": correlation,
                "metadata": {
                    "producer": self.store.owner,
                    "causation_id": None,
                    "zone": device[0],
                    "equipment_type": "ac_split_onoff",
                },
                "conteudo": {
                    "command_id": command_id,
                    "target_boot_id": str(observed["boot_id"]),
                    "revision": revision,
                    "desired": {
                        "compressor_on": desired[0],
                        "condenser_fan_on": desired[1],
                    },
                    "mode": "auto"
                    if manual is None or manual == "release_auto"
                    else "manual",
                    "expires_at": (now + timedelta(seconds=15))
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "reason_code": reason,
                },
            }
        )
        raw = serialize_event_v2(command)
        conn.execute(
            text(
                "INSERT INTO app.commands(id,device_id,revision,boot_id,producer,actor_user_id,correlation_id,reason_code,payload,expires_at) VALUES(:id,:device,:revision,:boot,:producer,:actor,:correlation,:reason,:payload,:expires)"
            ),
            {
                "id": command.id,
                "device": identity,
                "revision": revision,
                "boot": observed["boot_id"],
                "producer": self.store.owner,
                "actor": actor,
                "correlation": correlation,
                "reason": reason,
                "payload": raw,
                "expires": datetime.fromisoformat(command.conteudo.expires_at),
            },
        )
        exchange, route = routing_key_v2(command)
        self.store.enqueue(Outbound(command.id, raw, exchange, route), connection=conn)
        record_audit(
            conn,
            actor,
            "command.requested",
            command.id,
            correlation,
            {"device_id": identity, "revision": revision, "reason": reason},
        )
        return command
