"""Durable assistant admission limits and redacted request metadata."""

from alembic import op

revision = "0018_assistant"
down_revision = "0017_insight_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE app.assistant_requests (
        id uuid PRIMARY KEY,actor_user_id uuid NOT NULL,instance_id uuid NOT NULL,
        device_id varchar(32) NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        outcome varchar(32) NOT NULL DEFAULT 'queued',finished_at timestamptz,
        question_sha256 char(64) NOT NULL,summary_sha256 char(64) NOT NULL,
        sources jsonb NOT NULL,model varchar(64) NOT NULL,
        duration_ms integer,first_token_ms integer,tokens integer,response_sha256 char(64),reason_code varchar(64)
      );
      CREATE INDEX assistant_actor_time ON app.assistant_requests(actor_user_id,created_at DESC);
      CREATE INDEX assistant_time ON app.assistant_requests(created_at DESC);
      GRANT SELECT,INSERT,UPDATE ON app.assistant_requests TO smartfan_api;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
