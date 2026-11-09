"""Supabase JWT verification and server-controlled workspace authorization."""

from dataclasses import dataclass
from functools import lru_cache
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import Membership


@dataclass(frozen=True)
class Access:
    subject: str
    workspace_id: UUID
    role: str


@lru_cache(maxsize=4)
def jwks_client(issuer: str):
    return jwt.PyJWKClient(
        issuer.rstrip("/") + "/.well-known/jwks.json", cache_jwk_set=True, lifespan=300, timeout=5
    )


def verified_subject(authorization: str | None) -> str:
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            401, "Sign in to access this application.", headers={"WWW-Authenticate": "Bearer"}
        )
    token = authorization[7:]
    try:
        key = jwks_client(settings.supabase_issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=settings.supabase_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud", "role", "session_id"]},
            leeway=15,
        )
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("Missing subject")
        UUID(claims["sub"])
        if not isinstance(claims["session_id"], str):
            raise ValueError("Missing session identity")
        UUID(claims["session_id"])
        if claims["role"] != "authenticated" or claims.get("is_anonymous", False):
            raise ValueError("An authenticated account is required")
        return claims["sub"]
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            401, "Invalid or expired sign-in token.", headers={"WWW-Authenticate": "Bearer"}
        ) from exc


def access(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
    x_workspace_id: Annotated[UUID | None, Header()] = None,
) -> Access:
    settings = get_settings()
    if settings.auth_mode == "local":
        if settings.app_environment != "local":
            raise HTTPException(503, "Hosted authentication is not configured.")
        from app.workspace_service import local_ids

        subject = "local-demo-reviewer"
        workspace = x_workspace_id or settings.local_workspace_id
        if x_workspace_id and workspace not in local_ids(session, subject):
            raise HTTPException(403, "No access to this workspace.")
        result = Access(subject, workspace, "ADMIN")
        guard_mutation(session, result, request)
        return result
    subject = verified_subject(authorization)
    # Bootstrap is the only route that accepts a verified identity without membership.
    # Ignore workspace headers here; provisioning always derives ownership from the token.
    if request.method == "POST" and request.url.path == "/api/v1/workspaces/bootstrap":
        from app.workspace_service import provision_my

        workspace = provision_my(session, SimpleNamespace(subject=subject))
        return Access(subject, workspace.id, "ADMIN")
    query = select(Membership).where(Membership.subject == subject)
    if x_workspace_id:
        query = query.where(Membership.workspace_id == x_workspace_id)
    memberships = session.scalars(query.order_by(Membership.created_at, Membership.id)).all()
    if not memberships:
        raise HTTPException(
            403,
            "No access to this workspace. Select an authorized workspace or create your private workspace.",
        )
    membership = memberships[0]
    result = Access(subject, membership.workspace_id, membership.role)
    guard_mutation(session, result, request)
    return result


def guard_mutation(session, user, request):
    if request.method not in ("GET", "HEAD", "OPTIONS") and not request.url.path.startswith(
        "/api/v1/workspaces"
    ):
        if user.role not in ["REVIEWER", "ADMIN"]:
            raise HTTPException(403, "Write access is required.")
        from app.audit import financial_lock

        financial_lock(session, user.workspace_id)


def reviewer(user: Annotated[Access, Depends(access)]) -> Access:
    if user.role not in ["REVIEWER", "ADMIN"]:
        raise HTTPException(403, "Reviewer access is required.")
    return user


User = Annotated[Access, Depends(access)]
Reviewer = Annotated[Access, Depends(reviewer)]


def manual_modes_allowed(user):
    settings = get_settings()
    return user.role == "ADMIN" and (
        (settings.auth_mode == "local" and settings.app_environment == "local")
        or settings.allow_manual_extraction_modes
    )
