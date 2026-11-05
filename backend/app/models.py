from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(20), default="CUSTOM", server_default="CUSTOM")
    owner_subject: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        CheckConstraint("kind IN ('CUSTOM','DEMO','MY')", name="workspace_kind"),
        Index(
            "uq_my_workspace_owner",
            "owner_subject",
            unique=True,
            postgresql_where=text("kind = 'MY'"),
        ),
    )


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("workspace_id", "code"),
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("status IN ('APPROVED','SUSPENDED','INACTIVE')", name="vendor_status"),
        Index("ix_vendors_workspace_status", "workspace_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    code: Mapped[str] = mapped_column(String(40))
    legal_name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("workspace_id", "number"),
        ForeignKeyConstraint(["workspace_id", "vendor_id"], ["vendors.workspace_id", "vendors.id"]),
        CheckConstraint("authorized_gross > 0", name="po_positive_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="po_currency"),
        CheckConstraint(
            "status IN ('OPEN','PARTIALLY_BILLED','CLOSED','CANCELLED')", name="po_status"
        ),
        CheckConstraint("valid_until >= issued_on", name="po_dates"),
        CheckConstraint("billing_mode IN ('ITEMIZED','AMOUNT_BASED')", name="po_billing_mode"),
        Index("ix_po_workspace_vendor_status", "workspace_id", "vendor_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    vendor_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    number: Mapped[str] = mapped_column(String(60))
    currency: Mapped[str] = mapped_column(String(3))
    authorized_gross: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    status: Mapped[str] = mapped_column(String(20))
    billing_mode: Mapped[str] = mapped_column(String(20))
    issued_on: Mapped[date]
    valid_until: Mapped[date]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    vendor: Mapped[Vendor] = relationship()
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        order_by="PurchaseOrderItem.line_number"
    )


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    __table_args__ = (
        UniqueConstraint("po_id", "line_number"),
        CheckConstraint("line_number > 0 AND quantity > 0 AND unit_price >= 0", name="item_values"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 1", name="item_tax_rate"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    po_id: Mapped[UUID] = mapped_column(ForeignKey("purchase_orders.id"))
    line_number: Mapped[int]
    sku: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(12, 8))


# Workflow identities are separate from procurement and from each other.


class InvoiceDocument(Base):
    __tablename__ = "invoice_documents"
    __table_args__ = (UniqueConstraint("workspace_id", "sha256"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(80), unique=True)
    byte_size: Mapped[int]
    page_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessingRun(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','FAILED')", name="run_status"
        ),
        Index("ix_runs_claim", "status", "lease_until"),
        CheckConstraint(
            "extraction_mode IN ('AUTO','GEMINI','FALLBACK')", name="run_extraction_mode"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("invoice_documents.id"))
    parent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("processing_runs.id"))
    status: Mapped[str] = mapped_column(String(20), default="QUEUED")
    extraction_mode: Mapped[str] = mapped_column(String(12), default="AUTO", server_default="AUTO")
    attempt: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pages: Mapped[list | None] = mapped_column(JSONB)
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    intake_context: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentSubmission(Base):
    __tablename__ = "document_submissions"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    document_id: Mapped[UUID] = mapped_column(ForeignKey("invoice_documents.id"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("processing_runs.id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    requested_mode: Mapped[str] = mapped_column(String(12), default="AUTO", server_default="AUTO")
    original_filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (Index("ix_events_run_id", "run_id", "id"),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("processing_runs.id"))
    attempt: Mapped[int]
    stage: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BusinessInvoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("workspace_id", "identity_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    vendor_id: Mapped[UUID] = mapped_column(ForeignKey("vendors.id"))
    identity_key: Mapped[str] = mapped_column(String(240))
    source_document_id: Mapped[UUID] = mapped_column(ForeignKey("invoice_documents.id"))
    invoice_number: Mapped[str] = mapped_column(String(160))
    invoice_date: Mapped[date | None]
    currency: Mapped[str | None] = mapped_column(String(3))
    total: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InvoiceRevision(Base):
    __tablename__ = "invoice_revisions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("processing_runs.id"), unique=True)
    extraction: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('VALIDATED','NEEDS_REVIEW','BLOCKED')", name="decision_outcome"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("processing_runs.id"), unique=True)
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("invoice_revisions.id"))
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id"))
    po_id: Mapped[UUID | None] = mapped_column(ForeignKey("purchase_orders.id"))
    outcome: Mapped[str] = mapped_column(String(20))
    rules: Mapped[list] = mapped_column(JSONB)
    summary: Mapped[dict] = mapped_column(JSONB)
    policy_version: Mapped[str] = mapped_column(String(60), default="gross-zero-overrun-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialCommitment(Base):
    __tablename__ = "financial_commitments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RESERVED','HELD','RELEASED','SETTLED')", name="commitment_status"
        ),
        CheckConstraint("amount > 0 AND amount < 'Infinity'::numeric", name="commitment_amount"),
        Index(
            "uq_consuming_commitment",
            "invoice_id",
            unique=True,
            postgresql_where=text("status IN ('RESERVED','HELD','SETTLED')"),
        ),
        Index("ix_commitments_po_status", "po_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"))
    decision_id: Mapped[UUID] = mapped_column(ForeignKey("decisions.id"), unique=True)
    po_id: Mapped[UUID] = mapped_column(ForeignKey("purchase_orders.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20), default="RESERVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommitmentAllocation(Base):
    __tablename__ = "commitment_allocations"
    __table_args__ = (
        UniqueConstraint("commitment_id", "po_item_id"),
        CheckConstraint(
            "quantity > 0 AND quantity < 'Infinity'::numeric", name="allocation_quantity"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    commitment_id: Mapped[UUID] = mapped_column(ForeignKey("financial_commitments.id"))
    po_item_id: Mapped[UUID] = mapped_column(ForeignKey("purchase_order_items.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "subject"),
        CheckConstraint("role IN ('VIEWER','REVIEWER','ADMIN')", name="membership_role"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    subject: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','REVALIDATING','RESOLVED')", name="review_status"),
        Index(
            "uq_open_review_document",
            "document_id",
            unique=True,
            postgresql_where=text("status IN ('OPEN','REVALIDATING')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("invoice_documents.id"))
    latest_run_id: Mapped[UUID] = mapped_column(ForeignKey("processing_runs.id"))
    invoice_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoices.id"))
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    version: Mapped[int] = mapped_column(default=1)
    assignee: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReviewCorrection(Base):
    __tablename__ = "review_corrections"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("review_tasks.id"))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("processing_runs.id"), unique=True)
    base_run_id: Mapped[UUID] = mapped_column(ForeignKey("processing_runs.id"))
    actor: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str] = mapped_column(String(2000))
    extraction: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_workspace_time", "workspace_id", "created_at"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80))
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoice_documents.id"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("processing_runs.id"))
    detail: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))


class ProcurementImport(Base):
    __tablename__ = "procurement_imports"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    actor: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(30))
    sha256: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    record_count: Mapped[int]
    row_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GmailConnection(Base):
    __tablename__ = "gmail_connections"
    __table_args__ = (
        Index(
            "uq_gmail_active_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text("status != 'DISCONNECTED'"),
        ),
        Index("ix_gmail_due", "status", "next_sync_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    subject: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    credentials: Mapped[str | None] = mapped_column(Text)
    history_id: Mapped[str] = mapped_column(String(100))
    page_token: Mapped[str | None] = mapped_column(String(2048))
    recovery_history_id: Mapped[str | None] = mapped_column(String(100))
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_sync_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    failure_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(300))


class GmailOAuthAttempt(Base):
    __tablename__ = "gmail_oauth_attempts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    connection_id: Mapped[UUID | None] = mapped_column(ForeignKey("gmail_connections.id"))
    subject: Mapped[str] = mapped_column(String(255))
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (UniqueConstraint("connection_id", "gmail_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("gmail_connections.id"))
    gmail_id: Mapped[str] = mapped_column(String(200))
    sender: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="DISCOVERED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailAttachment(Base):
    __tablename__ = "email_attachments"
    __table_args__ = (
        UniqueConstraint("message_id", "part_id"),
        Index("ix_email_attachment_due", "status", "next_attempt_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    message_id: Mapped[UUID] = mapped_column(ForeignKey("email_messages.id"))
    part_id: Mapped[str] = mapped_column(String(200))
    attachment_id: Mapped[str | None] = mapped_column(String(1000))
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(150))
    byte_size: Mapped[int]
    sha256: Mapped[str | None] = mapped_column(String(64))
    classification: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error: Mapped[str | None] = mapped_column(String(300))
    review: Mapped[dict | None] = mapped_column(JSONB)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("invoice_documents.id"))
    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("processing_runs.id"))
    replayed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailIntakeEvent(Base):
    __tablename__ = "email_intake_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"))
    connection_id: Mapped[UUID] = mapped_column(ForeignKey("gmail_connections.id"))
    attachment_id: Mapped[UUID | None] = mapped_column(ForeignKey("email_attachments.id"))
    stage: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(String(500))
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
