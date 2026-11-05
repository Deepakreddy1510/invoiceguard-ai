"""Run browser tests with an owned disposable DB, worker, API and UI; keep demo untouched."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.seed import seed
from scripts.dataset_v2.common import ROOT
from scripts.dataset_v2.isolation import DatabasePool, child_environment
from scripts.dataset_v2.runner import invoke

admin = os.environ.get(
    "EVAL_ADMIN_DATABASE_URL",
    "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/postgres",
)
processes = []
with DatabasePool(admin) as pool, tempfile.TemporaryDirectory() as temp:
    name, url = pool.create()
    env = child_environment(url, temp, "fallback")
    env.update(
        VITE_PORT="5174",
        API_PROXY_TARGET="http://127.0.0.1:8001",
        PLAYWRIGHT_BASE_URL="http://127.0.0.1:5174",
    )
    invoke("migrate", url, Path(temp), "fallback")
    engine = create_engine(url)
    with Session(engine) as session, session.begin():
        seed(session)
    engine.dispose()
    try:
        for label, command, cwd in [
            (
                "api",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8001",
                ],
                ROOT / "backend",
            ),
            ("worker", [sys.executable, "-m", "app.worker.main"], ROOT / "backend"),
            ("vite", ["node", "node_modules/vite/bin/vite.js"], ROOT / "frontend"),
        ]:
            log = open(Path(temp) / ("browser-" + label + ".log"), "w")
            processes.append(
                (subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=log), log)
            )
        with httpx.Client() as client:
            for _ in range(60):
                if any(p.poll() is not None for p, _ in processes):
                    raise RuntimeError("A test service failed; inspect browser service logs.")
                try:
                    if (
                        client.get("http://127.0.0.1:8001/api/v1/health/ready").status_code == 200
                        and client.get("http://127.0.0.1:5174").status_code == 200
                    ):
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("Isolated test services not ready")
        result = subprocess.run(
            ["node", "node_modules/playwright/cli.js", "test"],
            cwd=ROOT / "frontend",
            env=env,
            timeout=300,
        )
        if result.returncode:
            for _, log in processes:
                log.flush()
                print(Path(log.name).read_text()[-2000:])
            raise RuntimeError("Browser regression failed")
    finally:
        for p, _ in processes:
            p.terminate()
        for p, log in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            log.close()
    print("Isolated original browser regression completed; demo untouched.")
