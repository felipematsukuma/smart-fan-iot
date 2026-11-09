"""Dependency outages do not exhaust accepted inbox messages."""

from alembic import op

revision = "0005_dependency_retries"
down_revision = "0004_influx_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE transport.inbox ADD COLUMN dependency_failure boolean NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
