"""Source-idempotent predictions, activation history, and persistent alert hysteresis."""

from alembic import op

revision = "0015_inference"
down_revision = "0014_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE app.model_activations (
        revision bigint PRIMARY KEY,version varchar(64) NOT NULL REFERENCES app.models(version),
        artifact_sha256 char(64) NOT NULL,activated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE TABLE app.inference_results (
        source_event_id uuid PRIMARY KEY,persisted_event_id uuid NOT NULL UNIQUE,
        device_id varchar(32) NOT NULL,boot_id uuid NOT NULL,sequence bigint NOT NULL,
        sampled_at timestamptz NOT NULL,observed_at timestamptz NOT NULL,
        model_version varchar(64),activation_revision bigint,insight_sha256 char(64) NOT NULL,
        frame_payload bytea,insight_payload bytea,created_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE INDEX inference_device_time ON app.inference_results(device_id,sampled_at DESC);
      CREATE VIEW app.prediction_receipts WITH (security_barrier=true) AS
        SELECT source_event_id,device_id,boot_id,sequence,sampled_at,observed_at,model_version,activation_revision,insight_sha256
        FROM app.inference_results;
      CREATE TABLE app.drift_states (
        device_id varchar(32) PRIMARY KEY,model_version varchar(64) NOT NULL,
        samples integer NOT NULL DEFAULT 0,outside_sum double precision NOT NULL DEFAULT 0,
        bad_windows integer NOT NULL DEFAULT 0,good_windows integer NOT NULL DEFAULT 0,
        active boolean NOT NULL DEFAULT false,updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE TABLE app.predictive_rules (
        device_id varchar(32) PRIMARY KEY REFERENCES app.devices(id),rule_id uuid NOT NULL UNIQUE,
        revision integer NOT NULL DEFAULT 1,configuration jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE TABLE app.predictive_states (
        device_id varchar(32) PRIMARY KEY,rule_id uuid NOT NULL,rule_revision integer NOT NULL,
        model_version varchar(64),boot_id uuid,last_sequence bigint NOT NULL DEFAULT -1,
        last_sample_at timestamptz,last_source_event_id uuid,bad_count integer NOT NULL DEFAULT 0,
        good_count integer NOT NULL DEFAULT 0,active_alert_id uuid,updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE TABLE app.alerts (
        id uuid PRIMARY KEY,device_id varchar(32) NOT NULL,rule_id uuid NOT NULL,model_version varchar(64),
        severity varchar(16) NOT NULL,status varchar(16) NOT NULL CHECK(status IN ('active','cleared')),
        reason_code varchar(64) NOT NULL,source_event_id uuid NOT NULL,
        raised_at timestamptz NOT NULL,cleared_at timestamptz,last_sample_at timestamptz NOT NULL,
        cleared_source_event_id uuid,cleared_model_version varchar(64)
      );
      CREATE INDEX alerts_device_status ON app.alerts(device_id,status,raised_at DESC,id DESC);
      GRANT SELECT,INSERT ON app.model_activations,app.inference_results TO smartfan_inference;
      GRANT INSERT ON app.audit TO smartfan_inference;
      GRANT SELECT,INSERT,UPDATE ON app.drift_states TO smartfan_inference;
      GRANT SELECT ON app.prediction_receipts TO smartfan_control,smartfan_api;
      CREATE VIEW app.active_model WITH (security_barrier=true) AS
        SELECT s.active_version,s.active_revision,m.approved FROM app.model_selection s LEFT JOIN app.models m ON m.version=s.active_version WHERE s.singleton;
      GRANT SELECT ON app.active_model TO smartfan_control;
      GRANT SELECT ON app.model_activations,app.drift_states TO smartfan_api;
      GRANT SELECT,INSERT,UPDATE ON app.predictive_rules,app.predictive_states,app.alerts TO smartfan_control;
      GRANT SELECT,INSERT,UPDATE ON app.predictive_rules TO smartfan_api;
      GRANT SELECT ON app.predictive_states,app.alerts TO smartfan_api;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
