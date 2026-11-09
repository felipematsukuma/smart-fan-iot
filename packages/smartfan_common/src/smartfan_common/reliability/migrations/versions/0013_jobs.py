"""Immutable synthetic configurations and fenced job execution state."""

from alembic import op

revision = "0013_jobs"
down_revision = "0012_messaging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      GRANT USAGE ON SCHEMA app TO "smartfan_jobs-worker";
      CREATE TABLE app.datasets (
        id uuid PRIMARY KEY,configuration jsonb NOT NULL,configuration_sha256 char(64) NOT NULL,
        config_version integer NOT NULL DEFAULT 1 CHECK(config_version=1),rows bigint NOT NULL CHECK(rows BETWEEN 1 AND 5000000),
        status varchar(16) NOT NULL CHECK(status IN ('queued','running','completed','failed','cancelled')),
        sha256 char(64),manifest jsonb,actor_user_id uuid NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),completed_at timestamptz
      );
      CREATE TABLE app.jobs (
        id uuid PRIMARY KEY,dataset_id uuid NOT NULL REFERENCES app.datasets(id),
        kind varchar(16) NOT NULL CHECK(kind IN ('generate','train')),
        actor_user_id uuid NOT NULL,idempotency_key varchar(128) NOT NULL,request_hash char(64) NOT NULL,
        event_sha256 char(64) NOT NULL,correlation_id uuid NOT NULL,
        status varchar(16) NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed','cancelled')),
        processed bigint NOT NULL DEFAULT 0,total bigint NOT NULL CHECK(total>0),
        cancel_requested boolean NOT NULL DEFAULT false,reason_code varchar(64),
        worker_instance uuid,resource_generation bigint,attempts integer NOT NULL DEFAULT 0,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE(actor_user_id,idempotency_key),CHECK(processed>=0 AND processed<=total)
      );
      CREATE INDEX jobs_recent ON app.jobs(created_at DESC,id DESC);
      CREATE INDEX datasets_recent ON app.datasets(created_at DESC,id DESC);
      GRANT SELECT,INSERT ON app.datasets,app.jobs TO smartfan_api;
      GRANT UPDATE(cancel_requested) ON app.jobs TO smartfan_api;
      GRANT SELECT,UPDATE ON app.datasets,app.jobs TO "smartfan_jobs-worker";
      GRANT INSERT ON app.audit TO "smartfan_jobs-worker";
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
