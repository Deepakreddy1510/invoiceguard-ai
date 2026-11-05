"""Add encrypted workspace Gmail connections and durable email intake; preserve existing rows."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("processing_runs", sa.Column("intake_context", postgresql.JSONB(), nullable=True))
    op.create_table(
        "gmail_connections",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("history_id", sa.String(100), nullable=False),
        sa.Column("page_token", sa.String(2048), nullable=True),
        sa.Column("recovery_history_id", sa.String(100), nullable=True),
        sa.Column(
            "connected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "next_sync_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(300), nullable=True),
    )
    op.create_index("ix_gmail_due", "gmail_connections", ["status", "next_sync_at"], unique=False)
    op.create_index(
        "uq_gmail_active_workspace",
        "gmail_connections",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status != 'DISCONNECTED'"),
    )
    op.create_table(
        "gmail_oauth_attempts",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("gmail_connections.id"), nullable=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "connection_id", sa.Uuid(), sa.ForeignKey("gmail_connections.id"), nullable=False
        ),
        sa.Column("gmail_id", sa.String(200), nullable=False),
        sa.Column("sender", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("connection_id", "gmail_id"),
    )
    op.create_table(
        "email_attachments",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("email_messages.id"), nullable=False),
        sa.Column("part_id", sa.String(200), nullable=False),
        sa.Column("attachment_id", sa.String(1000), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(150), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("classification", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("review", postgresql.JSONB(), nullable=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("invoice_documents.id"), nullable=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("processing_runs.id"), nullable=True),
        sa.Column("replayed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("message_id", "part_id"),
    )
    op.create_index(
        "ix_email_attachment_due", "email_attachments", ["status", "next_attempt_at"], unique=False
    )
    op.create_table(
        "email_intake_events",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "connection_id", sa.Uuid(), sa.ForeignKey("gmail_connections.id"), nullable=False
        ),
        sa.Column("attachment_id", sa.Uuid(), sa.ForeignKey("email_attachments.id"), nullable=True),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("email_intake_events")
    op.drop_table("email_attachments")
    op.drop_table("email_messages")
    op.drop_table("gmail_oauth_attempts")
    op.drop_table("gmail_connections")
    op.drop_column("processing_runs", "intake_context")
