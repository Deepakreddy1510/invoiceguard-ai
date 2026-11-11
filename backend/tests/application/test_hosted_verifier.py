"""Exercise the operator smoke command against real APIs/worker and signed test identities."""

import httpx

from app.worker.main import run_once
from app.workspace_service import seed_public
from scripts.verify_hosted_preview import main
from tests.application import test_security
from tests.application.test_customer_auth import CUSTOMER_A, bootstrap

secure_client = test_security.secure_client


def test_verifier_valid_review_ocr_overbilling_and_saved_receipt(
    secure_client, monkeypatch, tmp_path
):
    from uuid import UUID

    client, database_factory, token = secure_client
    workspace = bootstrap(client, token, CUSTOMER_A)["default_workspace_id"]
    with database_factory.begin() as session:
        seed_public(session, UUID(workspace))
    original_client = httpx.Client

    def adapter(**kwargs):
        def handle(request):
            if request.method == "GET" and request.url.path.startswith("/api/v1/runs/"):
                run_once(database_factory, run_id=UUID(request.url.path.split("/")[-1]))
            response = client.request(
                request.method,
                request.url.path + ("?" + request.url.query.decode() if request.url.query else ""),
                headers=request.headers,
                content=request.read(),
            )
            return httpx.Response(
                response.status_code, headers=response.headers, content=response.content
            )

        return original_client(**kwargs, transport=httpx.MockTransport(handle))

    monkeypatch.setattr("scripts.verify_hosted_preview.httpx.Client", adapter)
    monkeypatch.setenv("INVOICEGUARD_SMOKE_TOKEN", token(CUSTOMER_A)["Authorization"][7:])
    receipt = tmp_path / "smoke.json"
    args = [
        "verify_hosted_preview",
        "--origin",
        "https://synthetic.example",
        "--receipt",
        str(receipt),
    ]
    monkeypatch.setattr(
        "sys.argv",
        args + ["--workspace", workspace, "--workflow", "--include-ocr", "--include-overbilling"],
    )
    main()
    # A new client and receipt recover the correct workspace without a default header.
    monkeypatch.setattr("sys.argv", args + ["--verify-receipt"])
    main()
    assert "Bearer" not in receipt.read_text()
