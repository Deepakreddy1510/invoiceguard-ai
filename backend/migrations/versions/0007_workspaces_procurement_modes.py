"""Add workspace ownership, procurement revisions, import receipts and extraction modes.

Only additive schema changes; existing decisions/commitments/seed data are untouched.
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspaces", sa.Column("kind", sa.String(20), nullable=False, server_default="CUSTOM")
    )
    op.add_column("workspaces", sa.Column("owner_subject", sa.String(255)))
    op.add_column(
        "workspaces",
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_check_constraint("workspace_kind", "workspaces", "kind IN ('CUSTOM','DEMO','MY')")
    op.create_index(
        "uq_my_workspace_owner",
        "workspaces",
        ["owner_subject"],
        unique=True,
        postgresql_where=sa.text("kind = 'MY'"),
    )
    for table in ["vendors", "purchase_orders"]:
        op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "document_submissions",
        sa.Column("requested_mode", sa.String(12), nullable=False, server_default="AUTO"),
    )
    op.add_column(
        "processing_runs",
        sa.Column("extraction_mode", sa.String(12), nullable=False, server_default="AUTO"),
    )
    op.create_check_constraint(
        "run_extraction_mode", "processing_runs", "extraction_mode IN ('AUTO','GEMINI','FALLBACK')"
    )
    op.create_table(
        "procurement_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("workspace_id", "idempotency_key"),
    )


def downgrade():
    op.drop_table("procurement_imports")
    op.drop_column("document_submissions", "requested_mode")
    op.drop_constraint("run_extraction_mode", "processing_runs", type_="check")
    op.drop_column("processing_runs", "extraction_mode")
    for table in ["vendors", "purchase_orders"]:
        op.drop_column(table, "version")
    op.drop_index("uq_my_workspace_owner", table_name="workspaces")
    op.drop_constraint("workspace_kind", "workspaces", type_="check")
    for column in ["created_at", "owner_subject", "kind"]:
        op.drop_column("workspaces", column)
