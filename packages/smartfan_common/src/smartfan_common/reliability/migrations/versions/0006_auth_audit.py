"""Application identity, revocable sessions, bounded login attempts and audit."""

from alembic import op

revision = "0006_auth_audit"
down_revision = "0005_dependency_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE SCHEMA app;
        REVOKE ALL ON SCHEMA app FROM PUBLIC;
        GRANT USAGE ON SCHEMA app TO smartfan_api;
        CREATE TABLE app.users (
            id uuid PRIMARY KEY,username varchar(64) NOT NULL UNIQUE,
            password_hash bytea NOT NULL,role text NOT NULL CHECK(role IN ('visualizador','operador','administrador')),
            enabled boolean NOT NULL DEFAULT true,auth_version integer NOT NULL DEFAULT 1 CHECK(auth_version>0),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE TABLE app.sessions (
            id uuid PRIMARY KEY,user_id uuid NOT NULL REFERENCES app.users(id),auth_version integer NOT NULL,
            expires_at timestamptz NOT NULL,revoked_at timestamptz,created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX sessions_user_active ON app.sessions(user_id,expires_at) WHERE revoked_at IS NULL;
        CREATE TABLE app.login_attempts (
            id uuid PRIMARY KEY,identity_hash char(64) NOT NULL,ip_hash char(64) NOT NULL,
            failed boolean NOT NULL DEFAULT true,created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX login_identity ON app.login_attempts(identity_hash,created_at) WHERE failed;
        CREATE INDEX login_ip ON app.login_attempts(ip_hash,created_at) WHERE failed;
        CREATE TABLE app.ws_tickets (
            token_hash char(64) PRIMARY KEY,session_id uuid NOT NULL REFERENCES app.sessions(id),
            origin text NOT NULL,expires_at timestamptz NOT NULL,consumed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX ticket_expiry ON app.ws_tickets(expires_at);
        CREATE TABLE app.audit (
            id uuid PRIMARY KEY,actor_user_id uuid REFERENCES app.users(id),action varchar(64) NOT NULL,
            entity_type varchar(64) NOT NULL,entity_id varchar(128),outcome varchar(32) NOT NULL,
            correlation_id uuid NOT NULL,details jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX audit_created ON app.audit(created_at DESC,id DESC);
        CREATE INDEX audit_actor ON app.audit(actor_user_id,created_at DESC);
        CREATE INDEX audit_correlation ON app.audit(correlation_id);
        CREATE INDEX audit_entity_action ON app.audit(action,entity_id,created_at DESC);
        GRANT SELECT,INSERT,UPDATE ON app.users,app.sessions,app.login_attempts,app.ws_tickets TO smartfan_api;
        GRANT SELECT,INSERT ON app.audit TO smartfan_api;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
