"""Production VM entrypoints. No provisioning, seeding or authorization bypass."""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import get_settings
from app.runtime_diagnostics import memory_snapshot

logger = logging.getLogger(__name__)


def worker_healthy(session, *, now=None):
    from app.models import WorkerHeartbeat

    latest = session.scalar(select(func.max(WorkerHeartbeat.last_seen)))
    return latest is not None and latest >= (now or datetime.now(timezone.utc)) - timedelta(
        seconds=240
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["migrate", "api", "worker", "worker-health"])
    role = parser.parse_args().role
    settings = get_settings()
    if settings.app_environment != "production":
        raise RuntimeError("VM deployment requires APP_ENVIRONMENT=production.")
    settings.validate_runtime()
    if role == "migrate":
        from scripts.run_free_demo import migrate_locked

        migrate_locked()
        return 0
    if role == "worker-health":
        from app.db import SessionLocal

        try:
            with SessionLocal() as session:
                return 0 if worker_healthy(session) else 1
        except Exception:
            # Health output must never contain connection strings or provider responses.
            logger.error("VM event=worker_health_failed category=database_unavailable")
            return 1
    logger.info("VM event=service_start role=%s resources=%s", role, memory_snapshot())
    command = (
        [sys.executable, "-m", "app.worker.main"]
        if role == "worker"
        else [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--workers",
            "1",
            "--proxy-headers",
            "--forwarded-allow-ips",
            "*",
            "--no-access-log",
        ]
    )
    # Only the private Docker network reaches port 8000; Caddy is the public proxy.
    os.execv(sys.executable, command)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
