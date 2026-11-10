"""Add queue organization without rewriting invoices or the financial ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoice_documents", sa.Column("archived_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("invoice_documents", "archived_at")
