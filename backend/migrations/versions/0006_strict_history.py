"""Disallow every history update, including within its creation transaction."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE OR REPLACE FUNCTION invoiceguard_immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'Committed InvoiceGuard history is immutable';
    END $$""")


def downgrade():
    op.execute("""CREATE OR REPLACE FUNCTION invoiceguard_immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'UPDATE' AND OLD.xmin::text::bigint = (txid_current() % 4294967296) THEN RETURN NEW; END IF;
      RAISE EXCEPTION 'Committed InvoiceGuard history is immutable';
    END $$""")
