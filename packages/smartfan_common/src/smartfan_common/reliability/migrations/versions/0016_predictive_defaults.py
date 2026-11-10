"""Seed versioned predictive settings without overwriting existing rules."""

from uuid import NAMESPACE_URL, uuid5

from alembic import op
from sqlalchemy import text

revision = "0016_predictive_defaults"
down_revision = "0015_inference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE app.predictive_rule_versions (
        device_id varchar(32) NOT NULL REFERENCES app.devices(id),revision integer NOT NULL,
        configuration jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(device_id,revision));
        ALTER TABLE app.alerts ADD COLUMN rule_revision integer NOT NULL DEFAULT 1;
        GRANT SELECT,INSERT ON app.predictive_rule_versions TO smartfan_api,smartfan_control;""")
    config = '{"enabled":true,"health_raise":40.0,"health_clear":45.0,"rul_raise_hours":24.0,"rul_clear_hours":30.0,"bad_samples":3,"good_samples":10}'
    conn = op.get_bind()
    for identity in conn.execute(text("SELECT id FROM app.devices")).scalars():
        conn.execute(
            text(
                "INSERT INTO app.predictive_rules(device_id,rule_id,configuration) VALUES(:id,:rule,CAST(:config AS jsonb)) ON CONFLICT(device_id) DO NOTHING"
            ),
            {
                "id": identity,
                "rule": str(uuid5(NAMESPACE_URL, "smartfan:predictive:" + identity)),
                "config": config,
            },
        )
    conn.execute(
        text(
            "INSERT INTO app.predictive_rule_versions(device_id,revision,configuration) SELECT device_id,revision,configuration FROM app.predictive_rules ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
