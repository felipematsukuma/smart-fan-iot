"""Scoped terminal-payload retention, preserving pending work and failures."""

from alembic import op

revision = "0002_retention"
down_revision = "0001_transport"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION transport.prune_terminals() RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE svc text := substring(session_user from 10);
        BEGIN
          IF svc NOT IN ('gateway','writer','inference','control','api','jobs-worker') THEN
            RAISE EXCEPTION 'Invalid retention owner' USING ERRCODE='42501';
          END IF;
          UPDATE transport.inbox SET payload=NULL WHERE owner=svc
            AND state IN ('completed','failed') AND finished_at<clock_timestamp()-interval '24 hours';
          UPDATE transport.outbox SET payload=NULL WHERE owner=svc
            AND state IN ('completed','failed') AND finished_at<clock_timestamp()-interval '24 hours';
          DELETE FROM transport.inbox WHERE owner=svc AND state='completed'
            AND finished_at<clock_timestamp()-interval '31 days';
          DELETE FROM transport.outbox WHERE owner=svc AND state='completed'
            AND finished_at<clock_timestamp()-interval '31 days';
        END $$;
        REVOKE ALL ON FUNCTION transport.prune_terminals() FROM PUBLIC;
    """)
    for role in ("gateway", "writer", "inference", "control", "api", "jobs-worker"):
        op.execute(f'GRANT EXECUTE ON FUNCTION transport.prune_terminals() TO "smartfan_{role}"')


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is not supported; restore a validated backup")
