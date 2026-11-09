"""Authorized realtime snapshots and ticket scopes; no broker payload rewrites."""

from alembic import op

revision = "0007_realtime"
down_revision = "0006_auth_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      ALTER TABLE app.ws_tickets ADD COLUMN scope jsonb NOT NULL DEFAULT '[]'::jsonb;
      CREATE TABLE app.event_snapshots (
        kind varchar(64) NOT NULL,device_id varchar(64) NOT NULL,
        event_id uuid NOT NULL,source_event_id uuid,boot_id uuid,
        sequence bigint NOT NULL DEFAULT -1,sampled_at timestamptz NOT NULL,
        observed_at timestamptz NOT NULL,payload bytea NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(kind,device_id)
      );
      GRANT SELECT,INSERT,UPDATE ON app.event_snapshots TO smartfan_api;
      GRANT SELECT ON transport.receipts TO smartfan_api,smartfan_inference;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
