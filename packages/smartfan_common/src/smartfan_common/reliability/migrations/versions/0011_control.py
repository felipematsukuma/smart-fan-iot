"""Serialized command intentions, observed state, and versioned thermostat rules."""

import json

from alembic import op
from sqlalchemy import text

from smartfan_common.control import RuleConfig

revision = "0011_control"
down_revision = "0010_registry_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE app.rules (
        device_id varchar(32) PRIMARY KEY REFERENCES app.devices(id),revision integer NOT NULL CHECK(revision>0),
        configuration jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE TABLE app.rule_versions (
        device_id varchar(32) NOT NULL REFERENCES app.devices(id),revision integer NOT NULL,
        configuration jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(device_id,revision)
      );
      CREATE TABLE app.control_observations (
        device_id varchar(32) PRIMARY KEY REFERENCES app.devices(id),boot_id uuid NOT NULL,
        sequence bigint NOT NULL,sampled_at timestamptz NOT NULL,source_id uuid NOT NULL,
        telemetry jsonb NOT NULL,last_off_at timestamptz NOT NULL,last_on_at timestamptz NOT NULL
      );
      CREATE TABLE app.command_sequences (
        device_id varchar(32) PRIMARY KEY REFERENCES app.devices(id),last_revision bigint NOT NULL
      );
      CREATE TABLE app.commands (
        id uuid PRIMARY KEY,device_id varchar(32) NOT NULL REFERENCES app.devices(id),
        revision bigint NOT NULL,boot_id uuid NOT NULL,producer varchar(16) NOT NULL CHECK(producer IN ('api','control')),
        actor_user_id uuid, idempotency_key varchar(128),request_hash char(64),
        correlation_id uuid NOT NULL,reason_code varchar(64) NOT NULL,payload bytea NOT NULL,
        status varchar(16) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','failed')),
        result varchar(64),ack_event_id uuid,observed jsonb,execution_unknown boolean NOT NULL DEFAULT false,
        expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),UNIQUE(device_id,revision),
        UNIQUE(actor_user_id,idempotency_key)
      );
      CREATE UNIQUE INDEX one_pending_device ON app.commands(device_id) WHERE status='pending';
      CREATE INDEX commands_history ON app.commands(device_id,created_at DESC,id DESC);
      CREATE INDEX commands_expiry ON app.commands(expires_at) WHERE status='pending';
      GRANT SELECT,INSERT,UPDATE ON app.rules TO smartfan_api;
      GRANT SELECT,INSERT ON app.rule_versions TO smartfan_api;
      GRANT SELECT ON app.rules TO smartfan_control;
      GRANT SELECT,INSERT,UPDATE ON app.control_observations TO smartfan_control;
      GRANT SELECT ON app.control_observations TO smartfan_api;
      GRANT SELECT,INSERT,UPDATE ON app.commands,app.command_sequences TO smartfan_api,smartfan_control;
      GRANT INSERT ON app.audit TO smartfan_control;
      GRANT SELECT ON transport.receipts TO smartfan_control;
    """)
    conn = op.get_bind()
    config = json.dumps(RuleConfig().model_dump())
    conn.execute(
        text(
            "INSERT INTO app.rules(device_id,revision,configuration) SELECT id,1,CAST(:config AS jsonb) FROM app.devices"
        ),
        {"config": config},
    )
    conn.execute(
        text(
            "INSERT INTO app.rule_versions(device_id,revision,configuration) SELECT device_id,revision,configuration FROM app.rules"
        )
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
