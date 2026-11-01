"""Protect committed audit, revision and decision history from mutation."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION invoiceguard_immutable_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'UPDATE' AND OLD.xmin::text::bigint = (txid_current() % 4294967296) THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'Committed InvoiceGuard history is immutable';
    END $$""")
    for table in ["audit_events", "invoice_revisions", "decisions", "review_corrections"]:
        op.execute(
            f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION invoiceguard_immutable_history()"
        )


def downgrade():
    for table in ["audit_events", "invoice_revisions", "decisions", "review_corrections"]:
        op.execute(f"DROP TRIGGER immutable_history ON {table}")
    op.execute("DROP FUNCTION invoiceguard_immutable_history()")
