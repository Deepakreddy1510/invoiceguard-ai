"""Durable polling and one-attachment-at-a-time intake using existing PostgreSQL/worker."""

import hashlib
import time
from contextlib import contextmanager
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from sqlalchemy import func, select, text

from app.audit import audit
from app.config import get_settings
from app.db import SessionLocal
from app.email_intake import google
from app.email_intake.policy import assess, context_for
from app.email_intake.screening import classify, normalize, parts
from app.extraction.pdf import pdf_process
from app.ingestion import ingest
from app.models import (
    EmailAttachment,
    EmailIntakeEvent,
    EmailMessage,
    GmailConnection,
    Membership,
    ProcessingRun,
    Workspace,
)


def lock_key(identifier):
    return "invoiceguard-gmail:" + str(identifier)


@contextmanager
def exclusive(factory, identifier):
    with factory() as locker:
        acquired = locker.scalar(
            text("SELECT pg_try_advisory_lock(hashtextextended(:key,0))"),
            {"key": lock_key(identifier)},
        )
        try:
            yield acquired
        finally:
            if acquired:
                locker.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key,0))"),
                    {"key": lock_key(identifier)},
                )


def record(session, connection, stage, outcome, detail, attachment=None, actor="gmail-worker"):
    session.add(
        EmailIntakeEvent(
            workspace_id=connection.workspace_id,
            connection_id=connection.id,
            attachment_id=attachment.id if attachment else None,
            stage=stage,
            outcome=outcome,
            detail=detail,
            evidence={"classification": attachment.classification}
            if stage == "classification" and attachment
            else {"review": attachment.review}
            if stage == "intake_review" and attachment
            else None,
        )
    )
    audit(
        session,
        connection.workspace_id,
        actor,
        "EMAIL_" + stage.upper(),
        {
            "connection_id": str(connection.id),
            "attachment_id": str(attachment.id) if attachment else None,
            "outcome": outcome,
        },
        attachment.document_id if attachment else None,
        attachment.run_id if attachment else None,
    )


def connection_authorized(session, connection):
    settings = get_settings()
    if settings.auth_mode == "local" and settings.app_environment == "local":
        return connection.subject == "local-demo-reviewer"
    return (
        session.scalar(
            select(Membership.id).where(
                Membership.workspace_id == connection.workspace_id,
                Membership.subject == connection.subject,
                Membership.role == "ADMIN",
            )
        )
        is not None
    )


def fail_connection(session, c, exc):
    c.failure_count += 1
    c.error = (
        str(exc)[:300]
        if isinstance(exc, google.GoogleFailure)
        else "Gmail synchronization failed. No mailbox content was logged; retry is scheduled."
    )
    if isinstance(exc, google.GoogleFailure) and exc.auth:
        c.status = "AUTH_REQUIRED"
    c.next_sync_at = google.now() + timedelta(
        seconds=max(min(3600, 15 * 2 ** min(c.failure_count, 8)), getattr(exc, "retry_after", 0))
    )
    record(session, c, "sync", "FAILED", c.error)
    session.commit()


def persist_message(session, c, raw):
    gmail_id = raw.get("id", "")
    google.GmailClient.identifier(gmail_id)
    previous = session.scalar(
        select(EmailMessage.id).where(
            EmailMessage.connection_id == c.id, EmailMessage.gmail_id == gmail_id
        )
    )
    if previous:
        return
    pending = session.scalar(
        select(func.count())
        .select_from(EmailAttachment)
        .join(EmailMessage, EmailMessage.id == EmailAttachment.message_id)
        .join(GmailConnection, GmailConnection.id == EmailMessage.connection_id)
        .where(
            EmailAttachment.workspace_id == c.workspace_id,
            EmailAttachment.status.in_(["QUEUED", "SCREENING"]),
            GmailConnection.status == "ACTIVE",
        )
    )
    if pending >= 500:
        raise google.GoogleFailure(
            "Email intake queue reached its 500-attachment workspace limit. Processing must catch up."
        )
    try:
        metadata, attachments = normalize(raw)
    except (google.GoogleFailure, TypeError, ValueError, AttributeError):
        # A malformed/oversize message is a durable failed intake item, not a poison cursor.
        m = EmailMessage(
            workspace_id=c.workspace_id,
            connection_id=c.id,
            gmail_id=gmail_id,
            sender="",
            subject="Message requires provider inspection",
            body="",
            status="FAILED",
        )
        session.add(m)
        session.flush()
        record(
            session,
            c,
            "discovery",
            "FAILED",
            "Message MIME/size limits exceeded; message content was not retained.",
        )
        return
    supported_count = sum(
        item["mime_type"] in ("application/pdf", "application/x-pdf", "application/octet-stream")
        and item["filename"].lower().endswith(".pdf")
        and 0 < item["byte_size"] <= 10 * 1024 * 1024
        for item in attachments
    )
    if pending + supported_count > 500:
        raise google.GoogleFailure(
            "Email intake queue reached its 500-attachment workspace limit. Processing must catch up."
        )
    m = EmailMessage(
        workspace_id=c.workspace_id,
        connection_id=c.id,
        gmail_id=gmail_id,
        **metadata,
        status="DISCOVERED"
        if supported_count
        else "INTAKE_REVIEW"
        if attachments
        else "NO_ATTACHMENTS",
    )
    session.add(m)
    session.flush()
    for item in attachments:
        supported = (
            item["mime_type"]
            in ("application/pdf", "application/x-pdf", "application/octet-stream")
            and item["filename"].lower().endswith(".pdf")
            and 0 < item["byte_size"] <= 10 * 1024 * 1024
        )
        a = EmailAttachment(
            workspace_id=c.workspace_id,
            message_id=m.id,
            **item,
            status="QUEUED" if supported else "UNSUPPORTED",
            error=None
            if supported
            else "Only PDF attachments up to 10 MiB are supported. No attachment was executed.",
        )
        session.add(a)
    record(
        session,
        c,
        "discovery",
        "SUCCEEDED",
        f"Message and {len(attachments)} attachment identities persisted. No financial decision implied.",
    )


def sync_connection(factory, identifier):
    with exclusive(factory, identifier) as acquired:
        if not acquired:
            return False
        with factory() as session:
            c = session.get(GmailConnection, identifier)
            if (
                not c
                or (
                    session.get(Workspace, c.workspace_id).archived_at is not None
                    and c.status != "REVOKE_PENDING"
                )
                or c.status not in ("ACTIVE", "REVOKE_PENDING")
                or c.next_sync_at > google.now()
            ):
                return False
            client = None
            try:
                if c.status == "REVOKE_PENDING":
                    tokens = google.unseal(c.workspace_id, c.credentials)
                    client = google.GmailClient()
                    client.revoke(tokens["refresh_token"])
                    c.credentials = None
                    c.status = "DISCONNECTED"
                    c.error = None
                    record(
                        session,
                        c,
                        "disconnect",
                        "SUCCEEDED",
                        "Provider revocation completed; encrypted credentials erased.",
                    )
                    session.commit()
                    return True
                if not connection_authorized(session, c):
                    raise google.GoogleFailure(
                        "The connection owner no longer has workspace administrator access.",
                        auth=True,
                    )
                client = google.access(c)
                if not c.recovery_history_id:
                    try:
                        page = client.history(c.history_id, c.page_token)
                    except google.GoogleFailure as exc:
                        if exc.status != 404:
                            raise
                        c.recovery_history_id = str(client.profile()["historyId"])
                        c.page_token = None
                        record(
                            session,
                            c,
                            "checkpoint_recovery",
                            "STARTED",
                            "History expired; bounded recent-inbox recovery begins without importing the historical mailbox.",
                        )
                if c.recovery_history_id:
                    since = max(
                        c.connected_at, (c.last_sync_at or c.connected_at) - timedelta(minutes=5)
                    )
                    page = client.recent(since, c.page_token)
                    ids = [row["id"] for row in page.get("messages", [])][:10]
                else:
                    ids = list(
                        dict.fromkeys(
                            item["message"]["id"]
                            for history in page.get("history", [])
                            for item in history.get("messagesAdded", [])
                        )
                    )
                    # Recover an oversized history batch through bounded messages.list pages.
                    if len(ids) > 50:
                        c.recovery_history_id = str(client.profile()["historyId"])
                        c.page_token = None
                        c.next_sync_at = google.now()
                        record(
                            session,
                            c,
                            "checkpoint_recovery",
                            "STARTED",
                            "Large history batch will be recovered through bounded recent-inbox pages.",
                        )
                        session.commit()
                        return True
                deadline = time.monotonic() + 40
                for message_id in ids:
                    if session.scalar(
                        select(EmailMessage.id).where(
                            EmailMessage.connection_id == c.id, EmailMessage.gmail_id == message_id
                        )
                    ):
                        continue
                    if time.monotonic() > deadline:
                        raise google.GoogleFailure(
                            "Mailbox page budget reached. Persisted message identities will be skipped on the next attempt."
                        )
                    try:
                        raw = client.message(message_id)
                    except google.GoogleFailure as exc:
                        if exc.status == 404:
                            record(
                                session,
                                c,
                                "message_missing",
                                "SKIPPED",
                                "Message was removed before retrieval; no attachment intake was created.",
                            )
                            session.commit()
                            continue
                        if exc.status == 413:
                            session.add(
                                EmailMessage(
                                    workspace_id=c.workspace_id,
                                    connection_id=c.id,
                                    gmail_id=message_id,
                                    sender="",
                                    subject="Message exceeds intake size limits",
                                    body="",
                                    status="FAILED",
                                )
                            )
                            record(
                                session,
                                c,
                                "discovery",
                                "FAILED",
                                "Oversized message was retained as a failed intake identity without storing its body.",
                            )
                            session.commit()
                            continue
                        raise
                    persist_message(session, c, raw)
                    # A bounded page can resume after failure without re-fetching its committed prefix.
                    session.commit()
                c.page_token = page.get("nextPageToken")
                if not c.page_token:
                    c.history_id = str(
                        c.recovery_history_id or page.get("historyId") or c.history_id
                    )
                    c.recovery_history_id = None
                    c.last_sync_at = google.now()
                c.next_sync_at = google.now() + timedelta(
                    seconds=1 if c.page_token else get_settings().gmail_poll_seconds
                )
                c.error = None
                c.failure_count = 0
                record(
                    session,
                    c,
                    "sync",
                    "SUCCEEDED",
                    "Bounded mailbox page and attachment identities committed before checkpoint advancement.",
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                c = session.get(GmailConnection, identifier)
                if isinstance(exc, google.GoogleFailure) and exc.status == 400:
                    c.page_token = None
                fail_connection(session, c, exc)
            finally:
                if client:
                    client.close()
        return True


def fetch_attachment(client, message, attachment):
    if attachment.attachment_id:
        return client.attachment(message.gmail_id, attachment.attachment_id)
    raw = client.message(message.gmail_id)
    for index, part in enumerate(parts(raw.get("payload", {}))):
        if str(part.get("partId") or index) == attachment.part_id:
            return google.decode(part.get("body", {}).get("data", ""), 10 * 1024 * 1024)
    raise google.GoogleFailure("Attachment is no longer available.", status=404)


def intake_attachment(factory, identifier):
    with exclusive(factory, identifier) as acquired:
        if not acquired:
            return False
        with factory() as session:
            a = session.get(EmailAttachment, identifier)
            if not a or a.status not in ("QUEUED", "SCREENING") or a.next_attempt_at > google.now():
                return False
            m = session.get(EmailMessage, a.message_id)
            c = session.get(GmailConnection, m.connection_id)
            # Serialize disconnect, discovery and attachment reads for this mailbox.
            with exclusive(factory, c.id) as mailbox_locked:
                if not mailbox_locked:
                    return False
                if (
                    c.status != "ACTIVE"
                    or session.get(Workspace, c.workspace_id).archived_at is not None
                ):
                    return False
                if not connection_authorized(session, c):
                    fail_connection(
                        session,
                        c,
                        google.GoogleFailure(
                            "Connection administrator access was removed.", auth=True
                        ),
                    )
                    return False
                a.status = "SCREENING"
                a.attempts += 1
                a.next_attempt_at = google.now() + timedelta(seconds=180)
                record(
                    session,
                    c,
                    "attachment_fetch",
                    "RUNNING",
                    "Fetching bounded PDF attachment from Gmail.",
                    a,
                )
                session.commit()
                client = None
                try:
                    client = google.access(c)
                    payload = fetch_attachment(client, m, a)
                    if len(payload) != a.byte_size:
                        raise google.GoogleFailure(
                            "Gmail attachment size did not match its persisted metadata.",
                            status=422,
                        )
                    if not payload.startswith(b"%PDF-"):
                        raise google.GoogleFailure(
                            "Attachment has no valid PDF signature.", status=422
                        )
                    payload_hash = hashlib.sha256(payload).hexdigest()
                    if a.sha256 and a.sha256 != payload_hash:
                        raise google.GoogleFailure(
                            "Attachment bytes differ from the recorded intake evidence.", status=422
                        )
                    a.sha256 = payload_hash
                    if not a.classification:
                        with TemporaryDirectory() as temp:
                            path = Path(temp) / "intake.pdf"
                            path.write_bytes(payload)
                            pages = pdf_process(path, True)["pages"]
                        a.classification = classify(m, a, pages)
                        record(
                            session,
                            c,
                            "classification",
                            "SUCCEEDED",
                            a.classification["explanation"],
                            a,
                        )
                        category = a.classification["category"]
                        a.status = (
                            "REVIEW"
                            if category == "UNCERTAIN"
                            or a.classification.get("matching_review_required")
                            or a.classification.get("multiple_invoices")
                            else "IGNORED"
                            if category == "NOT_INVOICE"
                            else "SCREENING"
                        )
                        session.commit()
                    if a.status in ("REVIEW", "IGNORED"):
                        return True
                    context = context_for(m, a)
                    record(
                        session,
                        c,
                        "handoff",
                        "RUNNING",
                        "Submitting actual PDF to the existing durable invoice pipeline.",
                        a,
                    )
                    session.commit()
                    receipt = ingest(
                        BytesIO(payload),
                        a.filename,
                        "gmail:" + str(a.id),
                        session,
                        a.workspace_id,
                        "gmail-worker",
                        extraction_mode="AUTO" if get_settings().gmail_use_gemini else "FALLBACK",
                        email_attachment_id=a.id,
                        intake_context=context,
                    )
                    session.refresh(a)
                    a.run_id = UUID(receipt["run_id"])
                    a.document_id = UUID(receipt["document_id"])
                    a.status = "INGESTED"
                    a.replayed = receipt["replayed"]
                    a.error = None
                    # Exact replays retain immutable earlier decisions. Context review is an intake disposition.
                    previous = session.get(ProcessingRun, a.run_id)
                    if a.replayed and (
                        any(r["outcome"] == "REVIEW" for r in assess(context, previous.extraction))
                        if previous.extraction
                        else a.classification.get("matching_review_required")
                    ):
                        a.status = "REVIEW"
                        a.error = "Exact-document replay retained the earlier run; this email context needs separate review."
                    record(
                        session,
                        c,
                        "handoff",
                        "SUCCEEDED",
                        "Persisted document/run linked; financial decision is recorded separately by the invoice worker.",
                        a,
                    )
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    a = session.get(EmailAttachment, identifier)
                    c = session.get(GmailConnection, c.id)
                    if a.run_id:
                        return (
                            True  # Commit acknowledgement ambiguity: never undo a durable handoff.
                        )
                    retryable = isinstance(exc, google.GoogleFailure) and (
                        exc.status in (0, 429) or exc.status >= 500 or exc.auth
                    )
                    a.status = "QUEUED" if retryable and a.attempts < 5 else "FAILED"
                    a.error = (
                        str(exc)[:300]
                        if isinstance(exc, google.GoogleFailure)
                        else "PDF intake failed. Check attachment readability and retry; no financial decision was fabricated."
                    )
                    a.next_attempt_at = google.now() + timedelta(
                        seconds=max(min(3600, 15 * 2**a.attempts), getattr(exc, "retry_after", 0))
                    )
                    if isinstance(exc, google.GoogleFailure) and exc.auth:
                        c.status = "AUTH_REQUIRED"
                        c.error = a.error
                    record(session, c, "attachment_intake", "FAILED", a.error, a)
                    session.commit()
                finally:
                    if client:
                        client.close()
                    statuses = session.scalars(
                        select(EmailAttachment.status).where(EmailAttachment.message_id == m.id)
                    ).all()
                    message = session.get(EmailMessage, m.id)
                    message.status = (
                        "DISCOVERED"
                        if any(x in ("QUEUED", "SCREENING") for x in statuses)
                        else "INTAKE_REVIEW"
                        if any(x in ("REVIEW", "FAILED", "UNSUPPORTED") for x in statuses)
                        else "INTAKE_RECORDED"
                    )
                    session.commit()
        return True


def mail_once(factory=SessionLocal):
    if not google.configured():
        return False
    with factory() as session:
        # Alternate discovery with intake by prioritizing due attachments, then a due connection.
        attachment = session.scalar(
            select(EmailAttachment.id)
            .join(EmailMessage)
            .join(GmailConnection)
            .where(
                EmailAttachment.status.in_(["QUEUED", "SCREENING"]),
                EmailAttachment.next_attempt_at <= google.now(),
                GmailConnection.status == "ACTIVE",
                GmailConnection.workspace_id.in_(
                    select(Workspace.id).where(Workspace.archived_at.is_(None))
                ),
            )
            .order_by(EmailAttachment.next_attempt_at)
            .limit(1)
        )
        connection = session.scalar(
            select(GmailConnection.id)
            .where(
                GmailConnection.status.in_(["ACTIVE", "REVOKE_PENDING"]),
                (GmailConnection.status == "REVOKE_PENDING")
                | GmailConnection.workspace_id.in_(
                    select(Workspace.id).where(Workspace.archived_at.is_(None))
                ),
                GmailConnection.next_sync_at <= google.now(),
            )
            .order_by(GmailConnection.next_sync_at)
            .limit(1)
        )
    # One bounded discovery page, then one bounded attachment, without a new queue service.
    worked = sync_connection(factory, connection) if connection else False
    if attachment:
        worked = intake_attachment(factory, attachment) or worked
    return worked
