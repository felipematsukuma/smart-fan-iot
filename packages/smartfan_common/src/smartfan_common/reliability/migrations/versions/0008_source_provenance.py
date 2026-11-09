"""Preserve source time/content after raw payload retention; reject freshened replays."""

from alembic import op
from sqlalchemy import text

from smartfan_common.contracts_v2 import TelemetrySampleV2, parse_event_v2
from smartfan_common.reliability.origins import record_origin

revision = "0008_source_provenance"
down_revision = "0007_realtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE transport.telemetry_origins (
        event_id uuid PRIMARY KEY,sampled_at timestamptz NOT NULL,device_id varchar(64) NOT NULL,
        boot_id uuid NOT NULL,sequence bigint NOT NULL,data_sha256 char(64) NOT NULL,zone varchar(64) NOT NULL
    ); GRANT SELECT,INSERT ON transport.telemetry_origins TO smartfan_gateway;""")
    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT payload FROM transport.inbox WHERE owner='gateway' AND payload IS NOT NULL")
    )
    for row in rows:
        try:
            event = parse_event_v2(bytes(row[0]))
        except ValueError:
            continue
        if isinstance(event, TelemetrySampleV2):
            record_origin(conn, event)
    op.execute("""CREATE OR REPLACE VIEW transport.receipts WITH (security_barrier=true) AS
      SELECT i.event_id,i.observed_at,i.sha256,o.sampled_at,o.device_id,o.boot_id,o.sequence,o.data_sha256,o.zone
      FROM transport.inbox i LEFT JOIN transport.telemetry_origins o ON o.event_id=i.event_id WHERE i.owner='gateway';""")


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
