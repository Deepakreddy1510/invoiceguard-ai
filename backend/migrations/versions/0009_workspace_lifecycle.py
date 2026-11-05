"""Add reversible workspace archival without changing financial history."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    # Repair only the optional field missing from some earlier 0008 prototypes.
    # Existing evidence and financial records are never rewritten.
    from sqlalchemy.dialects import postgresql

    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("email_intake_events")
    }
    if "evidence" not in columns:
        op.add_column(
            "email_intake_events", sa.Column("evidence", postgresql.JSONB(), nullable=True)
        )

    op.add_column("workspaces", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "workspaces", sa.Column("version", sa.Integer(), nullable=False, server_default="1")
    )


def downgrade():
    op.drop_column("workspaces", "version")
    op.drop_column("workspaces", "archived_at")
