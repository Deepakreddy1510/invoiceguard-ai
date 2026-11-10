"""Durable, workspace-private sample initialization. No existing data is changed."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sample_installations",
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), primary_key=True),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False),
        sa.Column("current_run_id", sa.Uuid(), sa.ForeignKey("processing_runs.id")),
        sa.Column("run_ids", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint(
            "status IN ('QUEUED','PROCESSING','FAILED','COMPLETE')",
            name="sample_installation_status",
        ),
        sa.CheckConstraint(
            "completed >= 0 AND completed <= 21", name="sample_installation_progress"
        ),
    )


def downgrade():
    op.drop_table("sample_installations")
