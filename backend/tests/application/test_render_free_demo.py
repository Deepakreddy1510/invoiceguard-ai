"""Free-only topology and real subprocess lifecycle, with no Render/AWS calls."""

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from scripts.run_free_demo import supervise

ROOT = Path(__file__).parents[3]


def command(code):
    return [sys.executable, "-c", code]


def test_blueprint_is_only_one_free_web_and_one_free_database():
    source = (ROOT / "deploy/render-free-demo.yaml").read_text()
    assert source.count("  plan: free") == 2
    assert source.count("- type: web") == 1 and "type: worker" not in source
    assert "plan: starter" not in source and "basic-" not in source
    assert "preDeployCommand" not in source and "disk:" not in source
    assert "dockerCommand: python -m scripts.run_free_demo" in source
    assert "fromGroup: invoiceguard-runtime" in source
    assert "value: s3" in source and "value: supabase" in source
    assert "autoDeploy: false" in source
    assert "fromDatabase:" in source and "property: connectionString" in source
    assert "ipAllowList: []" in source
    assert "AWS_ACCESS_KEY_ID" not in source and "GEMINI_API_KEY" not in source


def test_failed_migration_never_starts_services(tmp_path):
    marker = tmp_path / "unexpected"
    code = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    result = supervise(
        command("raise SystemExit(2)"),
        [("web", command(code)), ("worker", command(code))],
        threading.Event(),
        shutdown_timeout=0.5,
    )
    assert result == 1 and not marker.exists()


@pytest.mark.parametrize("name,exit_code", [("worker", 0), ("worker", 1), ("web", 1)])
def test_child_exit_stops_sibling_and_requests_container_restart(tmp_path, name, exit_code):
    marker = tmp_path / "sibling.json"
    sibling = command(
        f"import json,os,time;from pathlib import Path;Path({str(marker)!r}).write_text(json.dumps([os.getpid(),os.getpgrp()]));time.sleep(30)"
    )
    crashing = command(f"import time;time.sleep(.3);raise SystemExit({exit_code})")
    services = [
        ("web", sibling if name == "worker" else crashing),
        ("worker", crashing if name == "worker" else sibling),
    ]
    assert supervise(command("pass"), services, threading.Event(), shutdown_timeout=0.5) == 1
    pid, group = json.loads(marker.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    with pytest.raises(ProcessLookupError):
        os.killpg(group, 0)


def test_sigterm_reaches_both_process_groups_and_supervisor_exits_cleanly(tmp_path):
    markers = [tmp_path / "web", tmp_path / "worker"]
    service_code = "import os,time;from pathlib import Path;Path({path!r}).write_text(str(os.getpid()));time.sleep(30)"
    services = [
        (name, command(service_code.format(path=str(marker))))
        for name, marker in zip(["web", "worker"], markers, strict=True)
    ]
    # Exercise an actual PID-1-style signal handler in a separate supervisor process.
    code = f"import signal,threading;from scripts.run_free_demo import supervise;stop=threading.Event();signal.signal(signal.SIGTERM,lambda *_:stop.set());raise SystemExit(supervise({command('pass')!r},{services!r},stop,shutdown_timeout=.5))"
    process = subprocess.Popen(command(code))
    try:
        import time

        deadline = time.monotonic() + 5
        while not all(marker.exists() for marker in markers) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert all(marker.exists() for marker in markers)
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        for marker in markers:
            with pytest.raises(ProcessLookupError):
                os.kill(int(marker.read_text()), 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_stop_during_migration_does_not_start_worker(tmp_path):
    marker = tmp_path / "worker"
    stop = threading.Event()
    timer = threading.Timer(0.2, stop.set)
    timer.start()
    try:
        assert (
            supervise(
                command("import time;time.sleep(30)"),
                [("worker", command(f"from pathlib import Path;Path({str(marker)!r}).touch()"))],
                stop,
                shutdown_timeout=0.5,
            )
            == 0
        )
        assert not marker.exists()
    finally:
        timer.cancel()


def test_runtime_rejects_local_auth_before_migrations_or_services(monkeypatch):
    from scripts.run_free_demo import main

    monkeypatch.setattr(sys, "argv", ["run_free_demo"])
    with pytest.raises(RuntimeError, match="Free demo requires"):
        main()


def test_real_api_worker_boot_and_anonymous_auth_boundary(workflow_db, tmp_path):
    import socket
    import time

    import httpx
    from sqlalchemy import select

    from app.models import WorkerHeartbeat

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with workflow_db() as session:
        url = session.bind.url.render_as_string(hide_password=False)
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "APP_ENVIRONMENT": "production",
        "AUTH_MODE": "supabase",
        "SUPABASE_URL": "https://issuer.example",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_synthetic",
        "STORAGE_BACKEND": "s3",
        "S3_BUCKET": "synthetic-no-network",
        "STORAGE_DIR": str(tmp_path / "staging"),
        "PORT": str(port),
    }
    # No token/PDF requests: this smoke check makes no Supabase, S3 or Gemini calls.
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_free_demo"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        with httpx.Client(trust_env=False) as client:
            while time.monotonic() < deadline:
                assert process.poll() is None, "Supervisor exited before readiness"
                try:
                    response = client.get(f"http://127.0.0.1:{port}/api/v1/health/ready", timeout=1)
                    if response.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Supervised API did not become ready")
            assert client.get(f"http://127.0.0.1:{port}/api/v1/dashboard").status_code == 401
            assert (
                client.get(f"http://127.0.0.1:{port}/api/v1/config").json()["auth_mode"]
                == "supabase"
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with workflow_db() as session:
                    if session.scalar(select(WorkerHeartbeat.id).limit(1)):
                        break
                time.sleep(0.1)
            else:
                pytest.fail("Supervised worker did not heartbeat")
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=25) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
