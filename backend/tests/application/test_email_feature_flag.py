"""Disabling optional intake never disables manual invoice processing."""

from uuid import uuid4

import pytest

from app.config import Settings, get_settings
from app.email_intake.service import intake_attachment, mail_once, sync_connection
from tests.application import test_security
from tests.application.test_customer_auth import CUSTOMER_A, bootstrap

secure_client = test_security.secure_client


@pytest.mark.parametrize(
    "environment,expected", [("local", True), ("production", False), ("staging", False)]
)
def test_email_feature_default_is_hosted_off(environment, expected):
    assert Settings(app_environment=environment, _env_file=None).email_intake_enabled is expected
    assert (
        Settings(
            app_environment=environment, enable_email_intake=False, _env_file=None
        ).email_intake_enabled
        is False
    )
    assert (
        Settings(
            app_environment=environment, enable_email_intake=True, _env_file=None
        ).email_intake_enabled
        is True
    )


def test_disabled_intake_never_queries_jobs_or_provider(monkeypatch):
    monkeypatch.setenv("ENABLE_EMAIL_INTAKE", "false")
    get_settings.cache_clear()

    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled intake must not touch a DB, lock, or Gmail provider")

    monkeypatch.setattr("app.email_intake.service.google.configured", forbidden)
    monkeypatch.setattr("app.email_intake.service.exclusive", forbidden)
    assert mail_once(forbidden) is False
    assert sync_connection(forbidden, uuid4()) is False
    assert intake_attachment(forbidden, uuid4()) is False


def test_disabled_api_and_callback_are_guarded_but_manual_apis_remain(secure_client, monkeypatch):
    client, _, token = secure_client
    bootstrap(client, token, CUSTOMER_A)
    monkeypatch.setenv("ENABLE_EMAIL_INTAKE", "false")
    get_settings.cache_clear()
    assert client.get("/api/v1/config").json()["enable_email_intake"] is False
    headers = token(CUSTOMER_A)
    for method, path in [
        ("GET", "/api/v1/email"),
        ("POST", "/api/v1/email/oauth/start"),
        ("GET", "/api/v1/email/oauth/callback?code=synthetic&state=synthetic"),
    ]:
        response = client.request(method, path, headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Email Intake is disabled in this deployment."
    for path in ["vendors", "purchase-orders", "runs", "dashboard"]:
        assert client.get("/api/v1/" + path, headers=headers).status_code == 200
        assert client.get("/api/v1/" + path).status_code == 401
    # Existing PDF admission remains reachable and rejects a corrupt document normally.
    assert (
        client.post(
            "/api/v1/documents", headers=headers, files={"file": ("bad.pdf", b"bad")}
        ).status_code
        == 422
    )
    monkeypatch.setenv("ENABLE_EMAIL_INTAKE", "true")
    get_settings.cache_clear()
    assert client.get("/api/v1/config").json()["enable_email_intake"] is True
    assert client.get("/api/v1/email", headers=headers).status_code == 200


def test_disabled_email_preserves_real_pdf_processing(workflow_db, monkeypatch):
    from app.worker.main import run_once
    from scripts.generate_samples import invoice_pdf
    from tests.application.test_review import client_for

    monkeypatch.setenv("ENABLE_EMAIL_INTAKE", "false")
    get_settings.cache_clear()
    with client_for(workflow_db) as client:
        submission = client.post(
            "/api/v1/documents",
            files={"file": ("manual.pdf", invoice_pdf(), "application/pdf")},
        )
        assert submission.status_code == 202
        assert run_once(workflow_db)
        detail = client.get("/api/v1/runs/" + submission.json()["run_id"]).json()
        assert detail["status"] == "SUCCEEDED"
        assert detail["outcome"] == "VALIDATED"
        assert detail["decision"]["summary"]["commitment_id"]
