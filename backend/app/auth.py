"""OIDC verification and server-controlled workspace authorization."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException
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
        key = jwks_client(settings.oidc_issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            leeway=15,
        )
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("Missing subject")
        return claims["sub"]
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(
            401, "Invalid or expired sign-in token.", headers={"WWW-Authenticate": "Bearer"}
        ) from exc


def access(
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
        return Access(subject, workspace, "ADMIN")
    subject = verified_subject(authorization)
    query = select(Membership).where(Membership.subject == subject)
    if x_workspace_id:
        query = query.where(Membership.workspace_id == x_workspace_id)
    memberships = session.scalars(query.order_by(Membership.created_at, Membership.id)).all()
    if not memberships:
        raise HTTPException(
            403, "No access to this workspace. Ask the demo administrator for an invitation."
        )
    membership = memberships[0]
    return Access(subject, membership.workspace_id, membership.role)


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
