"""Allow registry readers to resolve the app schema, without private auth access."""

from alembic import op

revision = "0010_registry_usage"
down_revision = "0009_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT USAGE ON SCHEMA app TO smartfan_gateway,smartfan_control,smartfan_inference")


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
