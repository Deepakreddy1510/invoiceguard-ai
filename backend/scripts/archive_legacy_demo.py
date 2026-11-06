"""Explicit local cleanup through the supported archive lifecycle; history is retained.

Preview: uv run python -m scripts.archive_legacy_demo
Apply:   uv run python -m scripts.archive_legacy_demo --version <preview-version> --confirm
Only the original local synthetic workspace can be targeted. Never runs during migration.
"""

import argparse
import json
from uuid import NAMESPACE_URL, uuid5

from app.auth import Access
from app.config import DEMO_WORKSPACE_ID, get_settings
from app.db import SessionLocal
from app.models import Workspace
from app.workspaces_api import WorkspaceChange, archive_workspace


def cleanup(session, *, confirm=False, version=None):
    settings = get_settings()
    if settings.auth_mode != "local" or settings.app_environment != "local":
        raise ValueError("Legacy cleanup is restricted to local developer mode.")
    subject = "local-demo-reviewer"
    sample = session.get(Workspace, uuid5(NAMESPACE_URL, "invoiceguard:asterfield-v1:" + subject))
    legacy = session.get(Workspace, DEMO_WORKSPACE_ID)
    if not sample or sample.archived_at or sample.owner_subject != subject:
        raise ValueError("An existing active local Asterfield sample is required. No data changed.")
    if (
        not legacy
        or legacy.name != "Synthetic AP Demo"
        or legacy.owner_subject not in (None, subject)
    ):
        raise ValueError(
            "The original local synthetic workspace was not recognized. No data changed."
        )
    if not confirm or legacy.archived_at:
        return {
            "id": str(legacy.id),
            "version": legacy.version,
            "archived": bool(legacy.archived_at),
            "history": "retained",
            "preview": True,
        }
    if version is None:
        raise ValueError("Supply the preview version with --version before confirming.")
    return archive_workspace(
        legacy.id,
        WorkspaceChange(version=version, confirm=True),
        session,
        Access(subject, legacy.id, "ADMIN"),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--version", type=int)
    args = parser.parse_args()
    with SessionLocal() as session:
        print(json.dumps(cleanup(session, confirm=args.confirm, version=args.version), default=str))
