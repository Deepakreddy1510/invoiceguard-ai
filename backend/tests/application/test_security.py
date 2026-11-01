from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import DEMO_WORKSPACE_ID, get_settings
from app.db import get_session
from app.main import app
from app.models import (
    AuditEvent,
    InvoiceDocument,
    Membership,
    ProcessingRun,
    ReviewTask,
    Vendor,
    Workspace,
)


@pytest.fixture
def secure_client(workflow_db, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example/")
    monkeypatch.setenv("OIDC_AUDIENCE", "invoiceguard-api")
    monkeypatch.setenv("OIDC_CLIENT_ID", "public-client")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.auth.jwks_client",
        lambda issuer: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
        ),
    )

    def sessions():
        with workflow_db() as session:
            yield session

    app.dependency_overrides[get_session] = sessions

    def token(subject="invited-user", **changes):
        now = datetime.now(timezone.utc)
        claims = {
            "sub": subject,
            "iss": "https://issuer.example/",
            "aud": "invoiceguard-api",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            **changes,
        }
        return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256")}

    try:
        with TestClient(app) as client:
            yield client, workflow_db, token
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_authentication_and_membership_required(secure_client):
    client, factory, token = secure_client
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/config").status_code == 200
    assert client.get("/api/v1/vendors").status_code == 401
    assert client.get("/api/v1/vendors", headers=token()).status_code == 403
    with factory.begin() as session:
        session.add(
            Membership(workspace_id=DEMO_WORKSPACE_ID, subject="invited-user", role="VIEWER")
        )
    assert client.get("/api/v1/vendors", headers=token()).status_code == 200
    assert client.get("/api/v1/vendors", headers=token(aud="wrong-audience")).status_code == 401
    assert (
        client.get("/api/v1/vendors", headers=token(iss="https://other.example/")).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/vendors", headers=token(exp=datetime.now(timezone.utc) - timedelta(minutes=1))
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/documents", headers=token(), files={"file": ("a.pdf", b"%PDF")}
        ).status_code
        == 403
    )


def test_cross_workspace_documents_reviews_audit_and_headers_denied(secure_client):
    client, factory, token = secure_client
    other = uuid4()
    with factory.begin() as s:
        s.add(Membership(workspace_id=DEMO_WORKSPACE_ID, subject="invited-user", role="REVIEWER"))
        s.add(Workspace(id=other, name="Other evaluator workspace"))
        s.flush()
        vendor = Vendor(
            workspace_id=other,
            code="PRIVATE-VENDOR",
            legal_name="Private Synthetic",
            status="APPROVED",
        )
        s.add(vendor)
        doc = InvoiceDocument(
            workspace_id=other,
            sha256="a" * 64,
            storage_key=str(uuid4()) + ".pdf",
            byte_size=100,
            page_count=1,
        )
        s.add(doc)
        s.flush()
        run = ProcessingRun(document_id=doc.id)
        s.add(run)
        s.flush()
        task = ReviewTask(document_id=doc.id, latest_run_id=run.id)
        s.add(task)
        s.add(
            AuditEvent(
                workspace_id=other,
                actor="other-user",
                action="PRIVATE_EVENT",
                detail={},
                document_id=doc.id,
                run_id=run.id,
            )
        )
        s.flush()
        doc_id, run_id, task_id = doc.id, run.id, task.id
    headers = token()
    assert (
        client.get("/api/v1/documents/" + str(doc_id) + "/content", headers=headers).status_code
        == 404
    )
    assert client.get("/api/v1/runs/" + str(run_id), headers=headers).status_code == 404
    assert client.get("/api/v1/reviews/" + str(task_id), headers=headers).status_code == 404
    assert (
        client.get("/api/v1/vendors", headers={**headers, "X-Workspace-ID": str(other)}).status_code
        == 403
    )
    assert "PRIVATE_EVENT" not in client.get("/api/v1/audit-events", headers=headers).text
    assert "PRIVATE-VENDOR" not in client.get("/api/v1/vendors", headers=headers).text
    assert client.get("/api/v1/dashboard", headers=headers).json()["total_invoices"] == 0
