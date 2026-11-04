from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth import Reviewer, User
from app.workflow_api import DB
from app.workspace_service import (
    EXPANDED_DEMO,
    accessible,
    fresh_demo,
    provision_my,
    workspace_kind,
)

router = APIRouter(prefix="/api/v1/workspaces")


def listing(session, user):
    workspaces = [
        {
            "id": str(w.id),
            "name": w.name,
            "kind": workspace_kind(w),
            "role": role,
            "created_at": w.created_at,
        }
        for w, role in accessible(session, user)
    ]
    preferred = next(
        (
            str(w.id)
            for w, _ in accessible(session, user)
            if w.kind == "DEMO" and w.owner_subject == user.subject
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
def list_workspaces(session: DB, user: User):
    return listing(session, user)


@router.post("/bootstrap")
def bootstrap(session: DB, user: User):
    provision_my(session, user)
    session.commit()
    return listing(session, user)


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
