"""Free-demo-only process supervisor. Production's separate web/worker commands are unchanged."""

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time

from app.runtime_diagnostics import memory_snapshot

logger = logging.getLogger(__name__)


def shutdown(processes, timeout=20):
    """Stop entire groups, including PDF/Tesseract descendants; never leave an orphan worker."""
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + timeout
    for process in processes:
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    # As PID 1, reap any exited descendants adopted after an interrupted PDF job.
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if not pid:
                break
        except ChildProcessError:
            break


def signal_label(code):
    if code >= 0:
        return "none"
    try:
        return signal.Signals(-code).name
    except ValueError:
        return "signal_" + str(-code)


def supervise(migration, services, stop, *, shutdown_timeout=20):
    """Fail the whole container on child exit so a healthy API cannot conceal a dead worker."""
    child = subprocess.Popen(migration, start_new_session=True)
    try:
        while child.poll() is None and not stop.wait(0.1):
            pass
        migrated = child.poll() == 0 and not stop.is_set()
    finally:
        shutdown([child], shutdown_timeout)
    if stop.is_set():
        return 0
    if not migrated:
        logger.error("Free demo migration failed; web and worker were not started.")
        return 1
    children = []
    try:
        for name, command in services:
            children.append((name, subprocess.Popen(command, start_new_session=True)))
        logger.info(
            "Free demo event=services_started resources=%s",
            memory_snapshot([(name, process.pid) for name, process in children]),
        )
        next_sample = time.monotonic() + 15
        while not stop.wait(0.2):
            if time.monotonic() >= next_sample:
                logger.info(
                    "Free demo event=resource_sample resources=%s",
                    memory_snapshot([(name, process.pid) for name, process in children]),
                )
                next_sample = time.monotonic() + 15
            for name, process in children:
                if process.poll() is not None:
                    logger.error(
                        "Free demo event=child_exit role=%s exit_code=%s signal=%s resources=%s; stopping sibling for restart.",
                        name,
                        process.returncode,
                        signal_label(process.returncode),
                        memory_snapshot([(role, child.pid) for role, child in children]),
                    )
                    return 1
        return 0
    finally:
        shutdown([process for _, process in children], shutdown_timeout)


def migrate():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from app.db import engine

    # Rolling deploys/restarts serialize migration startup across containers.
    with engine.begin() as connection:
        connection.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended('invoiceguard-free-demo-migrations',0))"
            )
        )
        command.upgrade(Config("alembic.ini"), "head")


def main():
    from app.config import get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    settings.validate_runtime()
    if (
        settings.app_environment != "production"
        or settings.auth_mode != "supabase"
        or settings.storage_backend != "s3"
    ):
        raise RuntimeError("Free demo requires production, Supabase authentication and private S3.")
    if args.migrate:
        migrate()
        return 0
    port = int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):

        def request_stop(received, _frame):
            logger.info(
                "Free demo event=shutdown_requested signal=%s resources=%s",
                signal.Signals(received).name,
                memory_snapshot(),
            )
            stop.set()

        signal.signal(signum, request_stop)
    return supervise(
        [sys.executable, "-m", "scripts.run_free_demo", "--migrate"],
        [
            (
                "web",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(port),
                    "--workers",
                    "1",
                    "--timeout-graceful-shutdown",
                    "15",
                ],
            ),
            ("worker", [sys.executable, "-m", "app.worker.main"]),
        ],
        stop,
    )


if __name__ == "__main__":
    raise SystemExit(main())
