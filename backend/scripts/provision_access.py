"""Administrator-run invitation binding. No public registration endpoint."""

import argparse
from uuid import UUID

from sqlalchemy import select

from app.audit import audit
from app.db import SessionLocal
from app.models import Membership, Workspace

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True)
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--role", choices=["VIEWER", "REVIEWER", "ADMIN"], default="REVIEWER")
    args = parser.parse_args()
    with SessionLocal.begin() as session:
        if not session.get(Workspace, args.workspace):
            raise ValueError("Seed the intended workspace first.")
        membership = session.scalar(
            select(Membership).where(
                Membership.workspace_id == args.workspace, Membership.subject == args.subject
            )
        )
        if membership:
            membership.role = args.role
        else:
            session.add(
                Membership(workspace_id=args.workspace, subject=args.subject, role=args.role)
            )
        audit(
            session,
            args.workspace,
            "administrator-cli",
            "ACCESS_PROVISIONED",
            {"subject": args.subject, "role": args.role},
        )
    print("Workspace membership saved. No credentials or tokens were printed.")
