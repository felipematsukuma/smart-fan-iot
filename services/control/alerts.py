"""Persisted predictive hysteresis; no stale/unavailable prediction clears an alert."""

from datetime import datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from smartfan_common.contracts_v2 import (
    AlertV2,
    InsightPredictedV2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.predictive import PredictiveRule, advance
from smartfan_common.reliability.store import DurableStore, Outbound
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text


class PredictiveAlerts:
    def __init__(self, store: DurableStore):
        self.store = store

    def handle(
        self, conn, event: InsightPredictedV2, raw: bytes, now: datetime
    ) -> None:
        source = event.conteudo.source_event_id
        receipt = (
            conn.execute(
                text("SELECT * FROM app.prediction_receipts WHERE source_event_id=:id"),
                {"id": source},
            )
            .mappings()
            .first()
        )
        if (
            receipt is None
            or receipt["insight_sha256"] != payload_sha256(raw)
            or receipt["device_id"] != event.dispositivo
            or str(receipt["boot_id"]) != event.metadata.boot_id
            or receipt["sequence"] != event.metadata.sequence
            or receipt["sampled_at"] != datetime.fromisoformat(event.timestamp)
            or receipt["observed_at"]
            != datetime.fromisoformat(event.metadata.observed_at)
        ):
            raise ValueError("Insight differs from committed inference result")
        stamp = datetime.fromisoformat(event.timestamp)
        observed = datetime.fromisoformat(event.metadata.observed_at)
        if (
            not 0 <= (now - stamp).total_seconds() <= 6
            or not stamp <= observed <= now
            or (now - observed).total_seconds() > 6
        ):
            return
        device = conn.execute(
            text(
                "SELECT d.enabled,d.zone,p.boot_id,p.mqtt_status FROM app.device_registry d JOIN transport.device_status p ON p.device_id=d.id WHERE d.id=:id"
            ),
            {"id": event.dispositivo},
        ).first()
        if (
            not device
            or not device[0]
            or device[1] != event.metadata.zone
            or str(device[2]) != event.metadata.boot_id
            or device[3] == "offline"
        ):
            return
        rule_id = str(uuid5(NAMESPACE_URL, "smartfan:predictive:" + event.dispositivo))
        conn.execute(
            text(
                "INSERT INTO app.predictive_rules(device_id,rule_id,configuration) VALUES(:device,:rule,CAST(:config AS jsonb)) ON CONFLICT(device_id) DO NOTHING"
            ),
            {
                "device": event.dispositivo,
                "rule": rule_id,
                "config": PredictiveRule().model_dump_json(),
            },
        )
        row = (
            conn.execute(
                text(
                    "SELECT * FROM app.predictive_rules WHERE device_id=:id FOR SHARE"
                ),
                {"id": event.dispositivo},
            )
            .mappings()
            .one()
        )
        rule = PredictiveRule.model_validate(row["configuration"])
        conn.execute(
            text(
                "INSERT INTO app.predictive_rule_versions(device_id,revision,configuration) VALUES(:id,:revision,CAST(:config AS jsonb)) ON CONFLICT DO NOTHING"
            ),
            {
                "id": event.dispositivo,
                "revision": row["revision"],
                "config": rule.model_dump_json(),
            },
        )
        conn.execute(
            text(
                "INSERT INTO app.predictive_states(device_id,rule_id,rule_revision) VALUES(:device,:rule,:revision) ON CONFLICT(device_id) DO NOTHING"
            ),
            {
                "device": event.dispositivo,
                "rule": row["rule_id"],
                "revision": row["revision"],
            },
        )
        state = (
            conn.execute(
                text(
                    "SELECT * FROM app.predictive_states WHERE device_id=:id FOR UPDATE"
                ),
                {"id": event.dispositivo},
            )
            .mappings()
            .one()
        )
        if state["last_sample_at"] and (
            stamp <= state["last_sample_at"]
            or (
                state["boot_id"] is not None
                and str(state["boot_id"]) == event.metadata.boot_id
                and event.metadata.sequence <= state["last_sequence"]
            )
        ):
            return
        same = (
            state["model_version"] == event.conteudo.model_version
            and str(state["boot_id"]) == event.metadata.boot_id
            and state["rule_revision"] == row["revision"]
            and state["last_sample_at"] is not None
            and (stamp - state["last_sample_at"]).total_seconds() <= 6
        )
        bad = state["bad_count"] if same else 0
        good = state["good_count"] if same else 0
        active_id = state["active_alert_id"]
        transition = None
        current = conn.execute(text("SELECT * FROM app.active_model")).mappings().one()
        if (
            event.conteudo.status == "valid"
            and rule.enabled
            and current["approved"]
            and current["active_version"] == event.conteudo.model_version
            and current["active_revision"] == receipt["activation_revision"]
        ):
            bad, good, transition = advance(
                rule,
                event.conteudo.health_score,
                event.conteudo.rul_calendar_hours,
                bad,
                good,
                active_id is not None,
            )
        else:
            bad = good = 0
        if transition == "raised":
            assert (
                event.conteudo.health_score is not None
                and event.conteudo.rul_calendar_hours is not None
            )
            active_id = str(uuid4())
            severity = (
                "critical"
                if event.conteudo.health_score < 20
                or event.conteudo.rul_calendar_hours < 12
                else "warning"
            )
            conn.execute(
                text(
                    "INSERT INTO app.alerts(id,device_id,rule_id,rule_revision,model_version,severity,status,reason_code,source_event_id,raised_at,last_sample_at) VALUES(:id,:device,:rule,:rule_revision,:version,:severity,'active','predictive_health_or_rul',:source,:at,:at)"
                ),
                {
                    "id": active_id,
                    "device": event.dispositivo,
                    "rule": row["rule_id"],
                    "rule_revision": row["revision"],
                    "version": event.conteudo.model_version,
                    "severity": severity,
                    "source": source,
                    "at": stamp,
                },
            )
            self.emit(
                conn,
                event,
                str(active_id),
                str(row["rule_id"]),
                "raised",
                severity,
                "predictive_health_or_rul",
            )
        elif transition == "cleared":
            severity = conn.execute(
                text("SELECT severity FROM app.alerts WHERE id=:id"), {"id": active_id}
            ).scalar_one()
            conn.execute(
                text(
                    "UPDATE app.alerts SET status='cleared',cleared_at=:at,last_sample_at=:at,cleared_source_event_id=:source,cleared_model_version=:version WHERE id=:id"
                ),
                {
                    "id": active_id,
                    "at": stamp,
                    "source": source,
                    "version": event.conteudo.model_version,
                },
            )
            self.emit(
                conn,
                event,
                str(active_id),
                str(row["rule_id"]),
                "cleared",
                severity,
                "predictive_recovered",
            )
            active_id = None
        elif active_id:
            conn.execute(
                text("UPDATE app.alerts SET last_sample_at=:at WHERE id=:id"),
                {"id": active_id, "at": stamp},
            )
        conn.execute(
            text(
                "UPDATE app.predictive_states SET rule_revision=:revision,model_version=:version,boot_id=:boot,last_sequence=:sequence,last_sample_at=:at,last_source_event_id=:source,bad_count=:bad,good_count=:good,active_alert_id=:alert,updated_at=clock_timestamp() WHERE device_id=:device"
            ),
            {
                "device": event.dispositivo,
                "revision": row["revision"],
                "version": event.conteudo.model_version,
                "boot": event.metadata.boot_id,
                "sequence": event.metadata.sequence,
                "at": stamp,
                "source": source,
                "bad": bad,
                "good": good,
                "alert": active_id,
            },
        )

    def emit(
        self,
        conn,
        source: InsightPredictedV2,
        identity: str,
        rule_id: str,
        transition: str,
        severity: str,
        reason: str,
    ) -> None:
        metadata = source.metadata.model_dump()
        metadata.update(producer="control", causation_id=source.id)
        event = AlertV2.model_validate(
            {
                "id": str(
                    uuid5(
                        NAMESPACE_URL, "smartfan:alert-" + transition + ":" + identity
                    )
                ),
                "schema_version": "2.1",
                "timestamp": source.timestamp,
                "tipo": "alert." + transition,
                "dispositivo": source.dispositivo,
                "correlation_id": source.correlation_id,
                "metadata": metadata,
                "conteudo": {
                    "alert_id": identity,
                    "rule_id": rule_id,
                    "severity": severity,
                    "source_event_id": source.conteudo.source_event_id,
                    "reason_code": reason,
                },
            }
        )
        exchange, route = routing_key_v2(event)
        self.store.enqueue(
            Outbound(event.id, serialize_event_v2(event), exchange, route),
            connection=conn,
        )

        # The shared audit writer is command-specific; alerts use their own entity.
        conn.execute(
            text(
                "INSERT INTO app.audit(id,actor_user_id,action,entity_type,entity_id,correlation_id,details,outcome) VALUES(:id,NULL,:action,'alert',:entity,:correlation,CAST(:details AS jsonb),'success')"
            ),
            {
                "id": str(uuid4()),
                "action": "alert." + transition,
                "entity": identity,
                "correlation": source.correlation_id or str(uuid4()),
                "details": "{}",
            },
        )
