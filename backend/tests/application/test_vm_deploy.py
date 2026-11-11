"""VM runtime boundaries and the rendered Compose network/service contract."""

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models import WorkerHeartbeat
from scripts.run_vm import main, worker_healthy


def test_vm_fails_closed_with_local_runtime(monkeypatch):
    monkeypatch.setattr("sys.argv", ["run_vm", "api"])
    with pytest.raises(RuntimeError, match="production"):
        main()


def test_worker_health_requires_recent_database_heartbeat(workflow_db):
    now = datetime.now(timezone.utc)
    with workflow_db.begin() as session:
        assert not worker_healthy(session, now=now)
        heartbeat = WorkerHeartbeat(last_seen=now - timedelta(seconds=241), status="AVAILABLE")
        session.add(heartbeat)
        session.flush()
        assert not worker_healthy(session, now=now)
        heartbeat.last_seen = now
        session.flush()
        assert worker_healthy(session, now=now)


def test_compose_has_private_db_single_worker_and_hosted_auth(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose CLI is required for rendering the deployment contract")
    root = Path(__file__).resolve().parents[3]
    env_file = tmp_path / "runtime.env"
    env_file.write_text("GEMINI_API_KEY=synthetic$literal\n")
    env = {
        **os.environ,
        "APP_IMAGE": "invoiceguard-ai:synthetic",
        "APP_DOMAIN": "invoiceguard.example.invalid",
        "ACME_EMAIL": "test@example.invalid",
        "POSTGRES_PASSWORD": "a" * 64,
        "VM_ENV_FILE": str(env_file),
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            "maintenance",
            "-f",
            str(root / "deploy/vm/compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    config = json.loads(result.stdout)
    services = config["services"]
    assert set(services) == {"db", "migrate", "api", "worker", "proxy"}
    for name in ["db", "migrate", "api", "worker"]:
        assert not services[name].get("ports")
    assert {p["published"] for p in services["proxy"]["ports"]} == {"80", "443"}
    assert config["networks"]["private"]["internal"]
    for name in ["api", "worker", "migrate"]:
        service = services[name]
        assert service["environment"]["AUTH_MODE"] == "supabase"
        assert service["environment"]["APP_ENVIRONMENT"] == "production"
        assert service["environment"]["STORAGE_BACKEND"] == "s3"
        # Compose config escapes literal dollars for safe round-trip serialization.
        assert service["environment"]["GEMINI_API_KEY"] == "synthetic$$literal"
        assert service["command"] == [
            "python",
            "-m",
            "scripts.run_vm",
            name if name != "api" else "api",
        ]
    assert int(services["worker"]["mem_limit"]) == 2 * 1024**3
    assert int(services["api"]["mem_limit"]) == 1024**3
    assert services["db"]["volumes"][0]["type"] == "volume"
