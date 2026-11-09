"""HTTP adapters for command intents and versioned automatic rules."""

import json

from smartfan_common.control import RuleConfig, RuleUpdate
from sqlalchemy import Engine, text

from .auth import Principal, audit
from .errors import Problem


def get_rule(engine: Engine, identity: str) -> dict:
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT revision,configuration,updated_at FROM app.rules WHERE device_id=:id"
                ),
                {"id": identity},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise Problem(404, "rule_not_found", "Regra não encontrada.")
    return {"device_id": identity, "timezone": "America/Sao_Paulo", **dict(row)}


def update_rule(
    engine: Engine,
    identity: str,
    body: RuleUpdate,
    principal: Principal,
    correlation: str,
) -> dict:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT revision FROM app.rules WHERE device_id=:id FOR UPDATE"),
            {"id": identity},
        ).first()
        if row is None:
            raise Problem(404, "rule_not_found", "Regra não encontrada.")
        if row[0] != body.expected_revision:
            raise Problem(
                409,
                "rule_revision_conflict",
                "A regra mudou. Atualize antes de salvar.",
            )
        config = RuleConfig.model_validate(body.configuration).model_dump_json()
        conn.execute(
            text(
                "UPDATE app.rules SET revision=revision+1,configuration=CAST(:config AS jsonb),updated_at=clock_timestamp() WHERE device_id=:id"
            ),
            {"id": identity, "config": config},
        )
        conn.execute(
            text(
                "INSERT INTO app.rule_versions(device_id,revision,configuration) VALUES(:id,:revision,CAST(:config AS jsonb))"
            ),
            {"id": identity, "revision": row[0] + 1, "config": config},
        )
        audit(
            conn,
            principal.id,
            "rule.updated",
            "device",
            identity,
            correlation,
            {"revision": row[0] + 1, "configuration": json.loads(config)},
        )
    return get_rule(engine, identity)
