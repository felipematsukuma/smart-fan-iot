"""Alert history and rule metadata; live readings/predictions remain WebSocket data."""

from uuid import UUID

from smartfan_common.predictive import PredictiveRuleUpdate
from sqlalchemy import Engine, text

from .auth import Principal, audit
from .errors import Problem


class Insights:
    def __init__(self, engine: Engine):
        self.engine = engine

    def rule(self, identity: str) -> dict:
        with self.engine.connect() as conn:
            rule = (
                conn.execute(
                    text(
                        "SELECT rule_id,revision,configuration,updated_at FROM app.predictive_rules WHERE device_id=:id"
                    ),
                    {"id": identity},
                )
                .mappings()
                .first()
            )
            state = (
                conn.execute(
                    text(
                        "SELECT model_version,bad_count,good_count,active_alert_id,last_sample_at FROM app.predictive_states WHERE device_id=:id"
                    ),
                    {"id": identity},
                )
                .mappings()
                .first()
            )
        if rule is None:
            raise Problem(
                404, "predictive_rule_not_found", "Regra preditiva não encontrada."
            )
        return {
            "device_id": identity,
            **dict(rule),
            "state": dict(state) if state else None,
            "rul_unit": "calendar_hours",
        }

    def update(
        self,
        identity: str,
        body: PredictiveRuleUpdate,
        principal: Principal,
        correlation: str,
    ) -> dict:
        with self.engine.begin() as conn:
            revision = conn.execute(
                text(
                    "SELECT revision FROM app.predictive_rules WHERE device_id=:id FOR UPDATE"
                ),
                {"id": identity},
            ).scalar_one_or_none()
            if revision is None:
                raise Problem(
                    404, "predictive_rule_not_found", "Regra preditiva não encontrada."
                )
            if revision != body.expected_revision:
                raise Problem(
                    409,
                    "rule_revision_conflict",
                    "A regra mudou; atualize antes de salvar.",
                )
            conn.execute(
                text(
                    "UPDATE app.predictive_rules SET revision=revision+1,configuration=CAST(:config AS jsonb),updated_at=clock_timestamp() WHERE device_id=:id"
                ),
                {"id": identity, "config": body.configuration.model_dump_json()},
            )
            conn.execute(
                text(
                    "INSERT INTO app.predictive_rule_versions(device_id,revision,configuration) VALUES(:id,:revision,CAST(:config AS jsonb))"
                ),
                {
                    "id": identity,
                    "revision": revision + 1,
                    "config": body.configuration.model_dump_json(),
                },
            )
            audit(
                conn,
                principal.id,
                "predictive_rule.updated",
                "device",
                identity,
                correlation,
                {
                    "revision": revision + 1,
                    "configuration": body.configuration.model_dump(),
                },
            )
        return self.rule(identity)

    def alerts(
        self, identity: str | None, status: str | None, before: UUID | None, limit: int
    ) -> dict:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT id,device_id,rule_id,rule_revision,model_version,severity,status,reason_code,source_event_id,raised_at,cleared_at,last_sample_at,cleared_source_event_id,cleared_model_version FROM app.alerts WHERE (:device IS NULL OR device_id=:device) AND (:status IS NULL OR status=:status) AND (:before IS NULL OR (raised_at,id)<(SELECT raised_at,id FROM app.alerts WHERE id=CAST(:before AS uuid))) ORDER BY raised_at DESC,id DESC LIMIT :limit"
                    ),
                    {
                        "device": identity,
                        "status": status,
                        "before": str(before) if before else None,
                        "limit": limit + 1,
                    },
                )
                .mappings()
                .all()
            )
        return {
            "items": [dict(row) for row in rows[:limit]],
            "next_cursor": str(rows[limit - 1]["id"]) if len(rows) > limit else None,
            "note": "Ausência de dados não encerra alerta; horários preservam a fonte original.",
        }

    def status(self) -> dict:
        with self.engine.connect() as conn:
            selection = (
                conn.execute(
                    text(
                        "SELECT desired_version,active_version,activation_revision,active_revision,updated_at FROM app.model_selection WHERE singleton"
                    )
                )
                .mappings()
                .one()
            )
            drift = (
                conn.execute(
                    text(
                        "SELECT device_id,model_version,samples,bad_windows,good_windows,active,updated_at FROM app.drift_states ORDER BY device_id LIMIT 100"
                    )
                )
                .mappings()
                .all()
            )
        return {
            "selection": dict(selection),
            "drift": [dict(row) for row in drift],
            "rul_unit": "calendar_hours",
            "live_source": "websocket",
        }
