"""Worker-owned model metrics and explicit, revision-fenced administrative promotion."""

from alembic import op

revision = "0014_models"
down_revision = "0013_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE app.training_requests (
        job_id uuid PRIMARY KEY REFERENCES app.jobs(id),configuration jsonb NOT NULL,configuration_sha256 char(64) NOT NULL
      );
      CREATE TABLE app.models (
        version varchar(64) PRIMARY KEY CHECK(version ~ '^mdl_[a-f0-9]{32}$'),
        dataset_id uuid NOT NULL REFERENCES app.datasets(id),job_id uuid NOT NULL UNIQUE REFERENCES app.jobs(id),
        status varchar(16) NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed','cancelled')),
        artifact_sha256 char(64),manifest jsonb,report jsonb,approved boolean NOT NULL DEFAULT false,
        approved_against_version varchar(64),approved_by uuid,approved_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE INDEX models_recent ON app.models(created_at DESC,version DESC);
      CREATE TABLE app.model_selection (
        singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),desired_version varchar(64) REFERENCES app.models(version),
        active_version varchar(64) REFERENCES app.models(version),activation_revision bigint NOT NULL DEFAULT 0,
        active_revision bigint NOT NULL DEFAULT 0,updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      INSERT INTO app.model_selection(singleton) VALUES(true);
      CREATE TABLE app.activation_notifications (
        id uuid PRIMARY KEY,version varchar(64) NOT NULL REFERENCES app.models(version),revision bigint NOT NULL UNIQUE,
        request_hash char(64) NOT NULL,actor_user_id uuid NOT NULL,correlation_id uuid NOT NULL,
        state varchar(16) NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','enqueued','superseded')),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      GRANT SELECT,INSERT ON app.training_requests,app.models,app.activation_notifications TO smartfan_api;
      GRANT SELECT ON app.model_selection TO smartfan_api;
      GRANT UPDATE(approved,approved_against_version,approved_by,approved_at) ON app.models TO smartfan_api;
      GRANT UPDATE(desired_version,activation_revision,updated_at) ON app.model_selection TO smartfan_api;
      GRANT SELECT ON app.training_requests,app.models,app.model_selection,app.activation_notifications TO "smartfan_jobs-worker";
      GRANT UPDATE(status,artifact_sha256,manifest,report) ON app.models TO "smartfan_jobs-worker";
      GRANT UPDATE(state) ON app.activation_notifications TO "smartfan_jobs-worker";
      GRANT SELECT ON app.models,app.model_selection TO smartfan_inference;
      GRANT UPDATE(active_version,active_revision,updated_at) ON app.model_selection TO smartfan_inference;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
