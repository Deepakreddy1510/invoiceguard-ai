import unicodedata
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text

from app.audit import audit, financial_lock
from app.auth import Reviewer, User
from app.email_intake.service import lock_key
from app.models import EmailAttachment, GmailConnection, InvoiceDocument, ProcessingRun, Workspace
from app.workflow_api import DB
from app.workspace_service import (
    EXPANDED_DEMO,
    accessible,
    fresh_demo,
    provision_my,
    provision_sample,
    workspace_kind,
)

router = APIRouter(prefix="/api/v1/workspaces")


def listing(session, user, include_archived=False):
    workspaces = [
        {
            "id": str(w.id),
            "name": w.name,
            "kind": workspace_kind(w),
            "role": role,
            "created_at": w.created_at,
            "archived_at": w.archived_at,
            "version": w.version,
        }
        for w, role in accessible(session, user)
        if include_archived or w.archived_at is None
    ]
    preferred = next(
        (
            str(w.id)
            for w, _ in accessible(session, user)
            if w.kind == "DEMO" and w.owner_subject == user.subject and w.archived_at is None
        ),
        None,
    )
    default = preferred or next(
        (w["id"] for w in workspaces if w["id"] == str(EXPANDED_DEMO)),
        next(
            (w["id"] for w in workspaces if w["kind"] == "DEMO"),
            next((w["id"] for w in workspaces if w["kind"] == "MY"), str(user.workspace_id)),
        ),
    )
    return {"workspaces": workspaces, "default_workspace_id": default, "subject": user.subject}


@router.get("")
def list_workspaces(session: DB, user: User, include_archived: bool = False):
    return listing(session, user, include_archived)


@router.post("/bootstrap")
def bootstrap(session: DB, user: User):
    provision_my(session, user)
    session.commit()
    return listing(session, user)


@router.post("/sample", status_code=201)
def sample_workspace(session: DB, user: User):
    workspace = provision_sample(session, user)
    from app.sample_service import start

    start(session, workspace, user)
    session.commit()
    return {"workspace_id": str(workspace.id), **listing(session, user)}


class CreateWorkspaceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    name: str = Field(min_length=1, max_length=160)
    workspace_type: Literal["EMPTY", "SAMPLE"]

    @field_validator("name")
    @classmethod
    def visible_name(cls, value):
        value = value.strip()
        if not value or any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("Enter a workspace name using visible characters.")
        return value


@router.post("", status_code=201)
def create_workspace(payload: CreateWorkspaceInput, session: DB, user: User):
    if user.role != "ADMIN":
        raise HTTPException(403, "Workspace administrator access is required.")
    from app.workspace_service import create_workspace as create

    identifier, replayed = create(
        session, user, payload.request_id, payload.name, payload.workspace_type
    )
    return {"workspace_id": str(identifier), "replayed": replayed, **listing(session, user)}


class FreshDemoInput(BaseModel):
    request_id: UUID
    confirm_create: bool


@router.post("/fresh-demo", status_code=201)
def restore_demo(payload: FreshDemoInput, session: DB, user: Reviewer):
    if user.role != "ADMIN":
        raise HTTPException(403, "Administrator access is required to create a fresh demo.")
    if not payload.confirm_create:
        raise HTTPException(
            422, "Confirm creation of a new isolated demo. Existing history will be preserved."
        )
    result = fresh_demo(session, user, payload.request_id)
    return {**result, **listing(session, user)}


class WorkspaceChange(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    confirm: bool = False


def managed(session, user, identifier, version):
    role = next((r for w, r in accessible(session, user) if w.id == identifier), None)
    if role != "ADMIN":
        raise HTTPException(403, "Workspace administrator access is required.")
    financial_lock(session, identifier, allow_archived=True)
    workspace = session.scalar(
        select(Workspace)
        .where(Workspace.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if workspace.version != version:
        raise HTTPException(409, "Workspace settings changed. Refresh and try again.")
    return workspace


def changed(session, user, workspace, action, detail):
    workspace.version += 1
    audit(session, workspace.id, user.subject, action, detail)
    session.commit()
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "version": workspace.version,
        "archived_at": workspace.archived_at,
    }


@router.patch("/{identifier}")
def rename_workspace(identifier: UUID, payload: WorkspaceChange, session: DB, user: User):
    workspace = managed(session, user, identifier, payload.version)
    name = (payload.name or "").strip()
    if not name or any(ord(c) < 32 for c in name):
        raise HTTPException(422, "Enter a workspace name using visible characters.")
    previous = workspace.name
    effective_kind = workspace_kind(workspace)
    workspace.name = name
    workspace.kind = effective_kind  # Preserve legacy inferred demo disclosure after a rename.
    return changed(
        session, user, workspace, "WORKSPACE_RENAMED", {"before": previous, "after": name}
    )


@router.post("/{identifier}/archive")
def archive_workspace(identifier: UUID, payload: WorkspaceChange, session: DB, user: User):
    workspace = managed(session, user, identifier, payload.version)
    if not payload.confirm:
        raise HTTPException(422, "Confirm that this workspace should be archived.")
    if workspace.archived_at:
        raise HTTPException(409, "This workspace is already archived.")
    if sum(w.archived_at is None for w, _ in accessible(session, user)) <= 1:
        raise HTTPException(
            409, "Keep one active workspace available. Create or restore another workspace first."
        )
    now = datetime.now(timezone.utc)
    running = session.scalar(
        select(ProcessingRun.id)
        .join(InvoiceDocument)
        .where(
            InvoiceDocument.workspace_id == identifier,
            ProcessingRun.status == "RUNNING",
            ProcessingRun.lease_until > now,
        )
        .limit(1)
    )
    screening = session.scalar(
        select(EmailAttachment.id)
        .where(
            EmailAttachment.workspace_id == identifier,
            EmailAttachment.status == "SCREENING",
            EmailAttachment.next_attempt_at > now,
        )
        .limit(1)
    )
    if running or screening:
        raise HTTPException(
            409, "An invoice is currently processing. Wait for it to finish, then archive."
        )
    for connection in session.scalars(
        select(GmailConnection.id).where(GmailConnection.workspace_id == identifier)
    ).all():
        if not session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": lock_key(connection)},
        ):
            raise HTTPException(
                409, "An email check is in progress. Try archiving again after it finishes."
            )
    workspace.archived_at = now
    return changed(
        session,
        user,
        workspace,
        "WORKSPACE_ARCHIVED",
        {"name": workspace.name, "queued_invoices": "paused", "history": "retained"},
    )


@router.post("/{identifier}/restore")
def restore_workspace(identifier: UUID, payload: WorkspaceChange, session: DB, user: User):
    workspace = managed(session, user, identifier, payload.version)
    if not payload.confirm:
        raise HTTPException(422, "Confirm restoration of this workspace.")
    if not workspace.archived_at:
        raise HTTPException(409, "This workspace is already active.")
    workspace.archived_at = None
    return changed(
        session,
        user,
        workspace,
        "WORKSPACE_RESTORED",
        {"name": workspace.name, "queued_invoices": "resumed"},
    )


@router.get("/sample-initialization")
def sample_initialization(session: DB, user: User):
    from app.sample_service import is_owned_sample, progress

    own = is_owned_sample(session, session.get(Workspace, user.workspace_id), user.subject)
    return {
        "eligible": own,
        "initialization": progress(session, user.workspace_id) if own else None,
    }


@router.post("/sample-initialization/resume")
def resume_sample_initialization(session: DB, user: User):
    from app.sample_service import resume

    if user.role != "ADMIN":
        raise HTTPException(403, "Workspace administrator access is required.")
    resume(session, session.get(Workspace, user.workspace_id), user)
    session.commit()
    return sample_initialization(session, user)
