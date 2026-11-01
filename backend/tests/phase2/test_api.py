from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.worker.main import run_once
from scripts.generate_samples import invoice_pdf


def test_real_upload_worker_and_persistent_history(workflow_db):
    factory = workflow_db

    def sessions():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/documents",
                files={"file": ("unseen.pdf", invoice_pdf(), "application/pdf")},
                headers={"Idempotency-Key": "test-one"},
            )
            assert response.status_code == 202, response.text
            record = response.json()
            run_id = record["run_id"]
            assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "QUEUED"
            assert run_once(factory)
            detail = client.get(f"/api/v1/runs/{run_id}").json()
            assert detail["status"] == "SUCCEEDED"
            assert detail["decision"]["outcome"] == "VALIDATED"
            assert detail["extraction"]["fields"]["total"]["document_id"] == record["document_id"]
            assert detail["events"][-1]["stage"] == "decision"
            assert detail["decision"]["summary"]["payment_executed"] is False
            assert client.get(
                f"/api/v1/documents/{record['document_id']}/content"
            ).content.startswith(b"%PDF")
            replay = client.post(
                "/api/v1/documents",
                files={
                    "file": (
                        "renamed.pdf",
                        client.get(f"/api/v1/documents/{record['document_id']}/content").content,
                        "application/pdf",
                    )
                },
            ).json()
            assert replay["replayed"] and replay["run_id"] == run_id
            assert len(client.get("/api/v1/runs").json()["runs"]) == 1
            assert client.get("/api/v1/runs").json()["unique_business_invoices"] == 1
            assert client.get(f"/api/v1/runs/{uuid4()}").status_code == 404
        # New app client and DB session reconstruct persisted result.
        with TestClient(app) as client:
            assert client.get(f"/api/v1/runs/{run_id}").json()["outcome"] == "VALIDATED"
    finally:
        app.dependency_overrides.clear()


def test_failed_worker_retry_and_corrupt_api(workflow_db):
    factory = workflow_db

    def sessions():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            assert (
                client.post(
                    "/api/v1/documents", files={"file": ("bad.pdf", b"%PDF-bad")}
                ).status_code
                == 422
            )
            record = client.post(
                "/api/v1/documents", files={"file": ("valid.pdf", invoice_pdf())}
            ).json()
            # Simulate document storage loss as an actual worker technical failure.
            from app.config import get_settings

            path = get_settings().storage_dir / f"{record['document_id']}.pdf"
            original = path.read_bytes()
            path.unlink()
            assert run_once(factory)
            detail = client.get(f"/api/v1/runs/{record['run_id']}").json()
            assert detail["status"] == "FAILED" and detail["decision"] is None
            path.write_bytes(original)
            retried = client.post(f"/api/v1/runs/{record['run_id']}/retry").json()
            assert run_once(factory)
            detail = client.get(f"/api/v1/runs/{retried['run_id']}").json()
            assert detail["outcome"] == "VALIDATED"
            assert detail["parent_run_id"] == record["run_id"]
            assert len(client.get("/api/v1/runs").json()["runs"]) == 2
            assert client.get("/api/v1/runs").json()["unique_business_invoices"] == 1
    finally:
        app.dependency_overrides.clear()
