"""Gateway presence, authenticated command results and receipt provenance."""

from alembic import op

revision = "0003_gateway"
down_revision = "0002_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE OR REPLACE VIEW transport.receipts WITH (security_barrier=true) AS
        SELECT event_id,observed_at,sha256 FROM transport.inbox WHERE owner='gateway';
      CREATE TABLE transport.device_presence (
        owner text NOT NULL DEFAULT 'gateway' CHECK(owner='gateway'), device_id text PRIMARY KEY,
        zone text NOT NULL, boot_id uuid NOT NULL, boot_seen_at timestamptz NOT NULL,
        last_sample_at timestamptz, last_sequence bigint NOT NULL DEFAULT -1,
        state_at timestamptz, last_revision bigint, mode text NOT NULL DEFAULT 'auto',
        manual_cooling_block boolean NOT NULL DEFAULT false, mqtt_status text,
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE TABLE transport.command_results (
        owner text NOT NULL DEFAULT 'gateway' CHECK(owner='gateway'), command_id uuid PRIMARY KEY,
        ack_event_id uuid NOT NULL, ack_sha256 char(64) NOT NULL, result text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      ALTER TABLE transport.device_presence ENABLE ROW LEVEL SECURITY;
      ALTER TABLE transport.command_results ENABLE ROW LEVEL SECURITY;
      CREATE POLICY gateway_only ON transport.device_presence USING(owner=substring(current_user from 10)) WITH CHECK(owner=substring(current_user from 10));
      CREATE POLICY gateway_only ON transport.command_results USING(owner=substring(current_user from 10)) WITH CHECK(owner=substring(current_user from 10));
      GRANT SELECT,INSERT,UPDATE ON transport.device_presence,transport.command_results TO smartfan_gateway;
      CREATE VIEW transport.device_status WITH (security_barrier=true) AS
        SELECT device_id,zone,boot_id,boot_seen_at,last_sample_at,last_sequence,state_at,last_revision,mode,manual_cooling_block,mqtt_status,updated_at
        FROM transport.device_presence WHERE owner='gateway';
      GRANT SELECT ON transport.device_status TO smartfan_api,smartfan_control,smartfan_writer,smartfan_inference;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
