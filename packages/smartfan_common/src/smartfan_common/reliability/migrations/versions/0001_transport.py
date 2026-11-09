"""Durable delivery journal and fenced resource ownership.

Revision definitions are deliberately frozen; future changes need new revisions.
"""

from alembic import op

revision = "0001_transport"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE transport.inbox (
          owner text NOT NULL, event_id uuid NOT NULL, sha256 char(64) NOT NULL,
          payload bytea, route varchar(256) NOT NULL,
          state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','working','completed','failed')),
          attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
          generation bigint NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          leased_until timestamptz, observed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          finished_at timestamptz, reason_code varchar(64), PRIMARY KEY(owner,event_id),
          CHECK (state IN ('completed','failed') OR payload IS NOT NULL)
        );
        CREATE INDEX inbox_due ON transport.inbox(owner,available_at) WHERE state IN ('pending','working');
        CREATE TABLE transport.outbox (
          owner text NOT NULL, event_id uuid NOT NULL, sha256 char(64) NOT NULL,
          payload bytea, exchange varchar(128) NOT NULL, routing_key varchar(256) NOT NULL,
          state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','working','completed','failed')),
          attempts integer NOT NULL DEFAULT 0, generation bigint NOT NULL DEFAULT 0,
          available_at timestamptz NOT NULL DEFAULT clock_timestamp(), leased_until timestamptz,
          observed_at timestamptz NOT NULL DEFAULT clock_timestamp(), finished_at timestamptz,
          reason_code varchar(64), PRIMARY KEY(owner,event_id),
          CHECK (state IN ('completed','failed') OR payload IS NOT NULL)
        );
        CREATE INDEX outbox_due ON transport.outbox(owner,available_at) WHERE state IN ('pending','working');
        CREATE TABLE transport.failures (
          owner text NOT NULL, failure_id uuid NOT NULL, event_id uuid,
          sha256 char(64) NOT NULL, payload bytea NOT NULL, route varchar(256) NOT NULL,
          reason_code varchar(64) NOT NULL, attempts integer NOT NULL,
          created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
          PRIMARY KEY(owner,failure_id)
        );
        CREATE TABLE transport.resource_leases (
          resource text PRIMARY KEY, holder_service text NOT NULL, owner_instance_id uuid NOT NULL,
          generation bigint NOT NULL, kind text NOT NULL,
          state text NOT NULL CHECK(state IN ('active','recovering','released')),
          expires_at timestamptz NOT NULL, updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE VIEW transport.receipts WITH (security_barrier=true) AS
          SELECT event_id, observed_at FROM transport.inbox WHERE owner='gateway';
        REVOKE ALL ON SCHEMA transport FROM PUBLIC;
        REVOKE ALL ON ALL TABLES IN SCHEMA transport FROM PUBLIC;
    """)
    for table in ("inbox", "outbox", "failures"):
        op.execute(f"ALTER TABLE transport.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY owner_only ON transport.{table} USING (owner=substring(current_user from 10)) WITH CHECK (owner=substring(current_user from 10))"
        )
    for role in ("gateway", "writer", "inference", "control", "api", "jobs-worker"):
        name = '"smartfan_' + role + '"'
        op.execute(f"GRANT USAGE ON SCHEMA transport TO {name}")
        op.execute(
            f"GRANT SELECT,INSERT,UPDATE ON transport.inbox,transport.outbox,transport.failures TO {name}"
        )
    for role in ("writer", "control"):
        op.execute(f'GRANT SELECT ON transport.receipts TO "smartfan_{role}"')
    for role in ("api", "jobs-worker"):
        op.execute(f'GRANT SELECT,INSERT,UPDATE ON transport.resource_leases TO "smartfan_{role}"')


def downgrade() -> None:
    raise RuntimeError(
        "Destructive transport downgrade is not supported; restore a validated backup"
    )
