"""Reserve exact Influx point identities before any external upsert."""

from alembic import op

revision = "0004_influx_points"
down_revision = "0003_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE transport.influx_points (
            owner text NOT NULL DEFAULT 'writer' CHECK(owner='writer'),
            point_key char(64) PRIMARY KEY,event_id uuid NOT NULL UNIQUE,
            source_sha256 char(64) NOT NULL,line_sha256 char(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        ALTER TABLE transport.influx_points ENABLE ROW LEVEL SECURITY;
        CREATE POLICY writer_only ON transport.influx_points USING(owner=substring(current_user from 10)) WITH CHECK(owner=substring(current_user from 10));
        GRANT SELECT,INSERT ON transport.influx_points TO smartfan_writer;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
