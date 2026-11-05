from sqlalchemy import text

from app.models import AuditEvent


def financial_lock(session, workspace_id, *, allow_archived=False):
    # Short financial transactions serialize per workspace; OCR/model work is outside.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": "invoiceguard-financial:" + str(workspace_id)},
    )
    if not allow_archived:
        from fastapi import HTTPException

        archived = session.scalar(
            text("SELECT archived_at FROM workspaces WHERE id = :id"), {"id": workspace_id}
        )
        if archived is not None:
            raise HTTPException(
                409, "This workspace is archived. Restore it before making changes."
            )


def audit(session, workspace_id, actor, action, detail, document_id=None, run_id=None):
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor=actor,
            action=action,
            detail=detail,
            document_id=document_id,
            run_id=run_id,
        )
    )
