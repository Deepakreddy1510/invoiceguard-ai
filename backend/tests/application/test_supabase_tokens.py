"""Real signatures and required Supabase claims; no live tenant access."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app.auth import verified_subject
from app.config import Settings, get_settings


@pytest.fixture
def signed(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.auth.jwks_client",
        lambda issuer: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
        ),
    )
    now = datetime.now(timezone.utc)
    claims = dict(
        sub=str(uuid4()),
        session_id=str(uuid4()),
        role="authenticated",
        aud="authenticated",
        iss="https://project.supabase.co/auth/v1",
        iat=now,
        exp=now + timedelta(minutes=5),
    )

    def sign(changes=None, remove=None, signing_key=None):
        payload = {**claims, **(changes or {})}
        if remove:
            payload.pop(remove)
        return "Bearer " + jwt.encode(payload, signing_key or key, algorithm="ES256")

    yield claims, sign
    get_settings.cache_clear()


def test_valid_asymmetric_supabase_identity(signed):
    claims, sign = signed
    assert verified_subject(sign()) == claims["sub"]


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "anon"},
        {"iss": "https://other.supabase.co/auth/v1"},
        {"role": "service_role"},
        {"role": "anon"},
        {"sub": "local-demo-reviewer"},
        {"session_id": "invalid"},
        {"session_id": None},
        {"session_id": 123},
        {"is_anonymous": True},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_invalid_claims_are_rejected(signed, changes):
    _, sign = signed
    with pytest.raises(HTTPException) as exc:
        verified_subject(sign(changes))
    assert exc.value.status_code == 401


@pytest.mark.parametrize("claim", ["sub", "exp", "iat", "iss", "aud", "role", "session_id"])
def test_missing_claims_are_rejected(signed, claim):
    _, sign = signed
    with pytest.raises(HTTPException):
        verified_subject(sign(remove=claim))


def test_forged_and_malformed_tokens_rejected(signed):
    _, sign = signed
    for token in [
        None,
        "",
        "Basic token",
        "Bearer broken",
        sign(signing_key=ec.generate_private_key(ec.SECP256R1())),
    ]:
        with pytest.raises(HTTPException) as exc:
            verified_subject(token)
        assert exc.value.status_code == 401


def test_hosted_local_mode_forbidden():
    with pytest.raises(RuntimeError, match="forbidden"):
        Settings(app_environment="production", auth_mode="local").validate_runtime()


def test_private_key_cannot_be_published():
    with pytest.raises(RuntimeError, match="publishable"):
        Settings(
            auth_mode="supabase",
            supabase_url="https://project.supabase.co",
            supabase_publishable_key="sb_secret_invalid",
        ).validate_runtime()


def test_shared_secret_rejection(signed):
    claims, _ = signed
    token = jwt.encode(claims, "test-shared-secret-unsupported-32bytes", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        verified_subject("Bearer " + token)
    assert exc.value.status_code == 401


def test_documented_jwks_endpoint_and_key_selection(monkeypatch):
    from app.auth import jwks_client

    key = ec.generate_private_key(ec.SECP256R1())
    public = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public.update(kid="current-signing-key", use="sig", alg="ES256")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("AUTH_MODE", "supabase")
    get_settings.cache_clear()
    jwks_client.cache_clear()
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [public]})
    now = datetime.now(timezone.utc)
    claims = dict(
        sub=str(uuid4()),
        session_id=str(uuid4()),
        role="authenticated",
        aud="authenticated",
        iss="https://project.supabase.co/auth/v1",
        iat=now,
        exp=now + timedelta(minutes=5),
    )
    try:
        assert jwks_client(get_settings().supabase_issuer).uri == (
            "https://project.supabase.co/auth/v1/.well-known/jwks.json"
        )
        token = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "current-signing-key"})
        assert verified_subject("Bearer " + token) == claims["sub"]
        unknown = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "unknown"})
        with pytest.raises(HTTPException):
            verified_subject("Bearer " + unknown)
    finally:
        jwks_client.cache_clear()
        get_settings.cache_clear()
