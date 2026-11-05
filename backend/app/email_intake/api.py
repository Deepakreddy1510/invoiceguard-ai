"""Authorized Gmail controls and read-only, workspace-scoped intake views."""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text

from app.audit import audit, financial_lock
from app.auth import Reviewer, User
from app.config import get_settings
from app.email_intake import google
from app.email_intake.policy import assess, context_for
from app.email_intake.service import connection_authorized, fetch_attachment, lock_key, record
from app.extraction.pdf import PDFError, pdf_process
from app.models import (
    Decision,
    EmailAttachment,
    EmailIntakeEvent,
    EmailMessage,
    GmailConnection,
    GmailOAuthAttempt,
    Membership,
    ProcessingRun,
    PurchaseOrder,
)
from app.workflow_api import DB

router = APIRouter(prefix="/api/v1/email")
COOKIE = "ig_gmail_oauth"


class RedactOAuthLog(logging.Filter):
    def filter(self, record):
        if (
            isinstance(record.args, tuple)
            and len(record.args) >= 3
            and str(record.args[2]).startswith("/api/v1/email/oauth/callback")
        ):
            args = list(record.args)
            args[2] = "/api/v1/email/oauth/callback?[REDACTED]"
            record.args = tuple(args)
        return True


def admin(user):
    if user.role != "ADMIN":
        raise HTTPException(403, "Workspace administrator access is required.")


def connection_for(session, user, identifier):
    c = session.scalar(
        select(GmailConnection).where(
            GmailConnection.id == identifier, GmailConnection.workspace_id == user.workspace_id
        )
    )
    if not c:
        raise HTTPException(404, "Gmail connection not found in this workspace.")
    return c


def attachment_for(session, user, identifier):
    a = session.scalar(
        select(EmailAttachment).where(
            EmailAttachment.id == identifier, EmailAttachment.workspace_id == user.workspace_id
        )
    )
    if not a:
        raise HTTPException(404, "Email attachment not found in this workspace.")
    return a


def transaction_lock(session, identifier):
    if not session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": lock_key(identifier)},
    ):
        raise HTTPException(409, "This mailbox or attachment is being processed. Retry shortly.")


def callback_authorized(session, attempt):
    s = get_settings()
    if s.auth_mode == "local" and s.app_environment == "local":
        return attempt.subject == "local-demo-reviewer"
    return bool(
        session.scalar(
            select(Membership.id).where(
                Membership.workspace_id == attempt.workspace_id,
                Membership.subject == attempt.subject,
                Membership.role == "ADMIN",
            )
        )
    )


@router.post("/oauth/start")
def start(session: DB, user: User):
    admin(user)
    if not google.configured():
        raise HTTPException(
            503,
            "Gmail connection unavailable. Configure Google OAuth and the server encryption key first.",
        )
    financial_lock(session, user.workspace_id)
    active = session.scalar(
        select(GmailConnection).where(
            GmailConnection.workspace_id == user.workspace_id,
            GmailConnection.status != "DISCONNECTED",
        )
    )
    if active and active.status != "AUTH_REQUIRED":
        raise HTTPException(
            409, "Disconnect the current mailbox before connecting another account."
        )
    count = session.scalar(
        select(func.count())
        .select_from(GmailOAuthAttempt)
        .where(
            GmailOAuthAttempt.workspace_id == user.workspace_id,
            GmailOAuthAttempt.consumed_at.is_(None),
            GmailOAuthAttempt.expires_at > google.now(),
        )
    )
    if count >= 5:
        raise HTTPException(
            429, "Too many pending Gmail authorizations. Wait ten minutes before retrying."
        )
    state = secrets.token_urlsafe(32)
    browser = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    session.add(
        GmailOAuthAttempt(
            workspace_id=user.workspace_id,
            connection_id=active.id if active else None,
            subject=user.subject,
            state_hash=google.digest(state),
            browser_hash=google.digest(browser),
            verifier=google.seal(user.workspace_id, {"verifier": verifier}),
            expires_at=google.now() + timedelta(minutes=10),
        )
    )
    audit(session, user.workspace_id, user.subject, "GMAIL_OAUTH_STARTED", {})
    session.commit()
    response = JSONResponse({"authorization_url": google.authorization_url(state, verifier)})
    response.set_cookie(
        COOKIE,
        browser,
        max_age=600,
        httponly=True,
        secure=urlsplit(get_settings().gmail_redirect_uri).scheme == "https",
        samesite="lax",
        path="/api/v1/email/oauth/callback",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/oauth/callback")
def callback(request: Request, session: DB):
    state = request.query_params.get("state", "")
    browser = request.cookies.get(COOKIE, "")
    if not google.configured() or not state or len(state) > 200 or len(browser) > 200:
        raise HTTPException(400, "Invalid or expired Gmail authorization.")
    attempt = session.scalar(
        select(GmailOAuthAttempt)
        .where(GmailOAuthAttempt.state_hash == google.digest(state))
        .with_for_update()
    )
    if (
        not attempt
        or attempt.consumed_at
        or attempt.expires_at <= google.now()
        or not hmac.compare_digest(attempt.browser_hash, google.digest(browser))
        or not callback_authorized(session, attempt)
    ):
        raise HTTPException(400, "Invalid or expired Gmail authorization.")
    try:
        verifier = google.unseal(attempt.workspace_id, attempt.verifier)["verifier"]
    except google.GoogleFailure:
        raise HTTPException(400, "Invalid or expired Gmail authorization.") from None
    attempt.consumed_at = google.now()
    session.commit()
    client = google.GmailClient()
    success = False
    try:
        code = request.query_params.get("code", "")
        if not code or len(code) > 4096 or request.query_params.get("error"):
            raise google.GoogleFailure("Google consent was not completed.", auth=True)
        tokens = client.exchange(code, verifier)
        if (
            not tokens.get("refresh_token")
            or not tokens.get("access_token")
            or google.SCOPE not in tokens.get("scope", "").split()
        ):
            raise google.GoogleFailure(
                "Required offline Gmail read permission was not granted.", auth=True
            )
        client.token = tokens["access_token"]
        profile = client.profile()
        email = str(profile["emailAddress"])
        history = str(profile["historyId"])
        if "@" not in email or len(email) > 320 or not history.isdigit() or len(history) > 100:
            raise google.GoogleFailure("Google returned an invalid mailbox profile.", auth=True)
        financial_lock(session, attempt.workspace_id)
        if not callback_authorized(session, attempt):
            raise google.GoogleFailure(
                "Workspace permission changed during authorization.", auth=True
            )
        active = session.scalar(
            select(GmailConnection).where(
                GmailConnection.workspace_id == attempt.workspace_id,
                GmailConnection.status != "DISCONNECTED",
            )
        )
        if active:
            if (
                active.id != attempt.connection_id
                or active.email.casefold() != email.casefold()
                or active.status != "AUTH_REQUIRED"
            ):
                raise google.GoogleFailure(
                    "Mailbox connection changed. Disconnect before switching accounts.", auth=True
                )
            transaction_lock(session, active.id)
            c = active
        else:
            c = GmailConnection(
                workspace_id=attempt.workspace_id,
                subject=attempt.subject,
                email=email,
                history_id=history,
                connected_at=google.now(),
            )
            session.add(c)
        c.credentials = google.seal(
            attempt.workspace_id,
            {
                "refresh_token": tokens["refresh_token"],
                "access_token": tokens["access_token"],
                "expires_at": google.now().timestamp()
                + min(int(tokens.get("expires_in", 3600)), 3600),
            },
        )
        c.subject = attempt.subject
        c.status = "ACTIVE"
        c.error = None
        c.failure_count = 0
        c.next_sync_at = google.now()
        session.flush()
        record(
            session,
            c,
            "connection",
            "SUCCEEDED",
            "Google consent verified; mailbox checkpoint initialized without historical backfill.",
            actor=attempt.subject,
        )
        session.commit()
        success = True
    except (google.GoogleFailure, ValueError, KeyError, TypeError):
        session.rollback()
        audit(
            session,
            attempt.workspace_id,
            attempt.subject,
            "GMAIL_OAUTH_FAILED",
            {
                "safe_error": "Google authorization could not be completed; start Connect Gmail again."
            },
        )
        session.commit()
    finally:
        client.close()
    response = RedirectResponse(
        get_settings().gmail_trusted_origin.rstrip("/")
        + "/email-intake?gmail="
        + ("connected" if success else "failed"),
        status_code=303,
    )
    response.delete_cookie(COOKIE, path="/api/v1/email/oauth/callback")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/connections/{identifier}/sync", status_code=202)
def synchronize(identifier: UUID, session: DB, user: User):
    admin(user)
    c = connection_for(session, user, identifier)
    if not google.configured():
        raise HTTPException(
            503, "Gmail connection unavailable. Restore the server OAuth configuration first."
        )
    if c.status != "ACTIVE":
        raise HTTPException(409, "Reconnect the mailbox before requesting synchronization.")
    c.next_sync_at = google.now()
    record(
        session,
        c,
        "sync_requested",
        "QUEUED",
        "Administrator requested a bounded background synchronization.",
        actor=user.subject,
    )
    session.commit()
    return {"queued": True}


@router.post("/connections/{identifier}/disconnect", status_code=202)
def disconnect(identifier: UUID, session: DB, user: User):
    admin(user)
    c = connection_for(session, user, identifier)
    transaction_lock(session, c.id)
    if c.status == "DISCONNECTED":
        return {"status": c.status}
    c.status = "REVOKE_PENDING"
    c.next_sync_at = google.now()
    pending = session.scalars(
        select(EmailAttachment)
        .join(EmailMessage)
        .where(
            EmailMessage.connection_id == c.id,
            EmailAttachment.run_id.is_(None),
            EmailAttachment.status.in_(["QUEUED", "SCREENING"]),
        )
    ).all()
    for attachment in pending:
        attachment.status = "REVIEW"
        attachment.error = "Mailbox disconnected before handoff. Retain or ignore this source record; resend the PDF to a newly connected mailbox or use manual upload."
        record(
            session,
            c,
            "intake_paused",
            "SUCCEEDED",
            attachment.error,
            attachment,
            actor=user.subject,
        )
    record(
        session,
        c,
        "disconnect",
        "QUEUED",
        "Mailbox reads disabled; provider revocation queued. Historical intake and financial records are retained.",
        actor=user.subject,
    )
    session.commit()
    return {"status": c.status}


class IntakeReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["FORWARD", "IGNORE", "RETRY"]
    reason: str = Field(min_length=10, max_length=2000)
    selected_po_id: UUID | None = None


@router.post("/attachments/{identifier}/review")
def review(identifier: UUID, payload: IntakeReview, session: DB, user: Reviewer):
    a = attachment_for(session, user, identifier)
    m = session.get(EmailMessage, a.message_id)
    c = session.get(GmailConnection, m.connection_id)
    transaction_lock(session, c.id)
    transaction_lock(session, a.id)
    if a.status in ("SCREENING", "QUEUED"):
        raise HTTPException(409, "Wait for the current intake attempt before reviewing it.")
    if a.run_id and not (a.replayed and a.status == "REVIEW"):
        raise HTTPException(
            409,
            "This attachment is already linked to an immutable invoice run. Use financial exception review.",
        )
    if payload.action == "IGNORE":
        a.status = "IGNORED"
    else:
        if not google.configured():
            raise HTTPException(
                503,
                "Gmail connection unavailable. Restore the server OAuth configuration before forwarding.",
            )
        if c.status != "ACTIVE":
            raise HTTPException(409, "Reconnect Gmail before forwarding or retrying an attachment.")
        if a.status == "UNSUPPORTED":
            raise HTTPException(422, "Unsupported attachments cannot enter the PDF pipeline.")
        if a.run_id:
            raise HTTPException(
                409,
                "This exact PDF has an existing decision. Inspect that run and record any financial review there.",
            )
        selected = None
        if payload.selected_po_id:
            po = session.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.id == payload.selected_po_id,
                    PurchaseOrder.workspace_id == user.workspace_id,
                )
            )
            values = {
                f["value"]
                for f in (a.classification or {}).get("evidence", [])
                if f.get("kind") == "po_number" and f.get("verified")
            }
            if not po or po.number not in values:
                raise HTTPException(
                    422, "Select a PO in this workspace supported by the recorded email evidence."
                )
            selected = po.number
        a.review = {
            "actor": user.subject,
            "reason": payload.reason,
            "action": payload.action,
            "selected_po_number": selected,
            "created_at": google.now().isoformat(),
        }
        if payload.action == "FORWARD":
            if not a.classification:
                raise HTTPException(
                    409, "The attachment has no classification evidence yet. Retry intake first."
                )
            a.classification = {**a.classification, "intake_confirmation": "HUMAN_REVIEW"}
        elif payload.action == "RETRY":
            a.classification = None
        a.status = "QUEUED"
        a.attempts = 0
        a.next_attempt_at = google.now()
        a.error = None
    a.review = {
        **(a.review or {}),
        "actor": user.subject,
        "reason": payload.reason,
        "action": payload.action,
    }
    record(
        session,
        c,
        "intake_review",
        "SUCCEEDED",
        "Attributed reviewer disposition recorded; financial validation cannot be bypassed.",
        a,
        actor=user.subject,
    )
    statuses = session.scalars(
        select(EmailAttachment.status).where(EmailAttachment.message_id == m.id)
    ).all()
    m.status = (
        "DISCOVERED"
        if any(x in ("QUEUED", "SCREENING") for x in statuses)
        else "INTAKE_REVIEW"
        if any(x in ("REVIEW", "UNSUPPORTED", "FAILED") for x in statuses)
        else "INTAKE_RECORDED"
    )
    session.commit()
    return {"status": a.status}


def attachment_view(session, a):
    run = (
        session.scalar(
            select(ProcessingRun)
            .where(ProcessingRun.document_id == a.document_id)
            .order_by(ProcessingRun.created_at.desc(), ProcessingRun.id.desc())
            .limit(1)
        )
        if a.document_id
        else None
    )
    decision = session.scalar(select(Decision).where(Decision.run_id == run.id)) if run else None
    return {
        key: getattr(a, key)
        for key in [
            "id",
            "filename",
            "mime_type",
            "byte_size",
            "sha256",
            "classification",
            "status",
            "attempts",
            "next_attempt_at",
            "error",
            "review",
            "document_id",
            "run_id",
            "replayed",
        ]
    } | {
        "handoff_run_id": a.run_id,
        "run_id": run.id if run else a.run_id,
        "processing_status": run.status if run else None,
        "decision": decision.outcome if decision else None,
    }


@router.get("")
def overview(
    session: DB,
    user: User,
    search: Annotated[str, Query(max_length=160)] = "",
    status: Annotated[str, Query(max_length=30)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
):
    connections = session.scalars(
        select(GmailConnection)
        .where(GmailConnection.workspace_id == user.workspace_id)
        .order_by(GmailConnection.connected_at.desc())
    ).all()
    query = select(EmailMessage).where(EmailMessage.workspace_id == user.workspace_id)
    if search:
        term = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(
                EmailMessage.subject.ilike(term, escape="\\"),
                EmailMessage.sender.ilike(term, escape="\\"),
                EmailMessage.id.in_(
                    select(EmailAttachment.message_id).where(
                        EmailAttachment.workspace_id == user.workspace_id,
                        EmailAttachment.filename.ilike(term, escape="\\"),
                    )
                ),
            )
        )
    if status:
        query = query.where(
            EmailMessage.id.in_(
                select(EmailAttachment.message_id).where(
                    EmailAttachment.workspace_id == user.workspace_id,
                    EmailAttachment.status == status,
                )
            )
        )
    messages = session.scalars(
        query.order_by(EmailMessage.created_at.desc()).offset(offset).limit(30)
    ).all()
    attachments = session.scalars(
        select(EmailAttachment).where(
            EmailAttachment.workspace_id == user.workspace_id,
            EmailAttachment.message_id.in_([m.id for m in messages]),
        )
    ).all()
    a = EmailAttachment
    counts = (
        session.execute(
            select(
                func.count()
                .filter(a.classification["category"].astext == "INVOICE")
                .label("invoice_candidates"),
                func.count().filter(a.run_id.is_not(None)).label("attachments_ingested"),
                func.count()
                .filter(a.status.in_(["REVIEW", "UNSUPPORTED"]))
                .label("awaiting_review"),
                func.count().filter(a.status == "IGNORED").label("ignored"),
                func.count().filter(a.status == "FAILED").label("failed"),
                func.count(func.distinct(a.document_id)).label("unique_documents"),
            ).where(a.workspace_id == user.workspace_id)
        )
        .one()
        ._mapping
    )
    metrics = dict(counts)
    metrics["emails_checked"] = session.scalar(
        select(func.count())
        .select_from(EmailMessage)
        .where(EmailMessage.workspace_id == user.workspace_id)
    )
    metrics["failed_attempts"] = session.scalar(
        select(func.count())
        .select_from(EmailIntakeEvent)
        .where(
            EmailIntakeEvent.workspace_id == user.workspace_id,
            EmailIntakeEvent.stage == "attachment_intake",
            EmailIntakeEvent.outcome == "FAILED",
        )
    )
    metrics["linked_invoices"] = session.scalar(
        select(func.count(func.distinct(Decision.invoice_id)))
        .join(ProcessingRun, ProcessingRun.id == Decision.run_id)
        .join(a, a.document_id == ProcessingRun.document_id)
        .where(a.workspace_id == user.workspace_id)
    )

    return {
        "available": google.configured(),
        "email_classifier": "GEMINI"
        if get_settings().gmail_use_gemini and get_settings().gemini_api_key
        else "FALLBACK",
        "configuration_message": None
        if google.configured()
        else "Gmail connection unavailable. Google OAuth credentials and a server encryption key are required.",
        "can_manage": user.role == "ADMIN",
        "can_review": user.role in ("ADMIN", "REVIEWER"),
        "workspace_id": user.workspace_id,
        "connections": [
            {
                key: getattr(c, key)
                for key in [
                    "id",
                    "email",
                    "status",
                    "connected_at",
                    "last_sync_at",
                    "next_sync_at",
                    "failure_count",
                    "error",
                ]
            }
            for c in connections
        ],
        "metrics": metrics,
        "messages": [
            {
                **{
                    key: getattr(m, key)
                    for key in ["id", "sender", "subject", "received_at", "status"]
                },
                "invoice_attachment_count": sum(
                    (a.classification or {}).get("category") == "INVOICE"
                    for a in attachments
                    if a.message_id == m.id
                ),
                "attachments": [
                    attachment_view(session, a) for a in attachments if a.message_id == m.id
                ],
            }
            for m in messages
        ],
        "offset": offset,
        "limit": 30,
    }


@router.get("/messages/{identifier}")
def message_detail(identifier: UUID, session: DB, user: User):
    m = session.scalar(
        select(EmailMessage).where(
            EmailMessage.id == identifier, EmailMessage.workspace_id == user.workspace_id
        )
    )
    if not m:
        raise HTTPException(404, "Email not found in this workspace.")
    attachments = session.scalars(
        select(EmailAttachment).where(EmailAttachment.message_id == m.id)
    ).all()
    events = session.scalars(
        select(EmailIntakeEvent)
        .where(
            EmailIntakeEvent.workspace_id == user.workspace_id,
            or_(
                EmailIntakeEvent.attachment_id.in_([a.id for a in attachments]),
                (EmailIntakeEvent.connection_id == m.connection_id)
                & EmailIntakeEvent.attachment_id.is_(None),
            ),
        )
        .order_by(EmailIntakeEvent.created_at.desc())
        .limit(200)
    ).all()
    data = {
        **{
            key: getattr(m, key)
            for key in ["id", "sender", "subject", "body", "received_at", "status", "gmail_id"]
        },
        "workspace_id": m.workspace_id,
        "invoice_attachment_count": sum(
            (a.classification or {}).get("category") == "INVOICE" for a in attachments
        ),
        "attachments": [],
        "events": [
            {
                key: getattr(e, key)
                for key in [
                    "id",
                    "stage",
                    "outcome",
                    "detail",
                    "created_at",
                    "attachment_id",
                    "evidence",
                ]
            }
            for e in events
        ],
    }
    for a in attachments:
        evidence = (a.classification or {}).get("evidence", [])
        refs = {f["value"] for f in evidence if f.get("kind") == "po_number" and f.get("verified")}
        pos = (
            session.scalars(
                select(PurchaseOrder).where(
                    PurchaseOrder.workspace_id == user.workspace_id, PurchaseOrder.number.in_(refs)
                )
            ).all()
            if refs
            else []
        )
        view = attachment_view(session, a)
        run = session.get(ProcessingRun, view["run_id"]) if view["run_id"] else None
        data["attachments"].append(
            {
                **view,
                "po_candidates": [
                    {
                        "id": p.id,
                        "number": p.number,
                        "vendor": p.vendor.legal_name,
                        "status": p.status,
                        "source": "STORED_PROCUREMENT",
                    }
                    for p in pos
                ],
                "email_rules": assess(context_for(m, a), run.extraction) if run else [],
            }
        )
    return data


@router.get("/attachments/{identifier}/content")
def original_attachment(identifier: UUID, session: DB, user: User):
    a = attachment_for(session, user, identifier)
    if a.status == "UNSUPPORTED":
        raise HTTPException(422, "Unsupported attachments cannot be previewed as PDFs.")
    m = session.get(EmailMessage, a.message_id)
    c = session.get(GmailConnection, m.connection_id)
    transaction_lock(session, c.id)
    if c.status != "ACTIVE" or not google.configured() or not connection_authorized(session, c):
        raise HTTPException(
            409, "Reconnect the authorized mailbox to preview this original attachment."
        )
    client = None
    try:
        client = google.access(c)
        payload = fetch_attachment(client, m, a)
        if len(payload) != a.byte_size or not payload.startswith(b"%PDF-"):
            raise google.GoogleFailure("Attachment size or PDF signature is invalid.", status=422)
        if a.sha256 and hashlib.sha256(payload).hexdigest() != a.sha256:
            raise google.GoogleFailure(
                "Attachment bytes differ from the recorded intake evidence.", status=422
            )
        with TemporaryDirectory() as temp:
            path = Path(temp) / "source.pdf"
            path.write_bytes(payload)
            pdf_process(path, False)
        record(
            session,
            c,
            "source_preview",
            "SUCCEEDED",
            "Authorized reviewer opened the original bounded PDF attachment.",
            a,
            actor=user.subject,
        )
        session.commit()
        return Response(
            payload,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'inline; filename="source-attachment.pdf"',
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
        )
    except (google.GoogleFailure, PDFError) as exc:
        session.rollback()
        raise HTTPException(
            422 if isinstance(exc, PDFError) or getattr(exc, "status", 0) == 422 else 503,
            "Original attachment could not be safely loaded. Check Gmail authorization and document readability.",
        ) from None
    finally:
        if client:
            client.close()
