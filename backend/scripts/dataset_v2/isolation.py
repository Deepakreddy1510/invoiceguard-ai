"""Ownership-checked, create-only disposable PostgreSQL evaluation databases."""

import os
import re
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

PATTERN = re.compile(r"^ig_eval_v2_[0-9a-f]{24}$")


def validate_name(name):
    if not PATTERN.fullmatch(name):
        raise ValueError("Not an evaluator-owned database name.")
    return name


class DatabasePool:
    def __init__(self, admin_url):
        self.base = make_url(admin_url)
        self.owned = set()
        self.admin = create_engine(self.base.set(database="postgres"), isolation_level="AUTOCOMMIT")

    def create(self, template=None):
        name = "ig_eval_v2_" + uuid4().hex[:24]
        validate_name(name)
        if template is not None and template not in self.owned:
            raise ValueError("Template is not owned by this invocation.")
        suffix = f' TEMPLATE "{validate_name(template)}"' if template else ""
        with self.admin.connect() as c:
            c.exec_driver_sql(f'CREATE DATABASE "{name}"' + suffix)
        self.owned.add(name)
        return name, self.base.set(database=name).render_as_string(hide_password=False)

    def drop(self, name):
        if name not in self.owned:
            raise ValueError("Refusing to drop a database not created by this invocation.")
        validate_name(name)
        with self.admin.connect() as c:
            c.exec_driver_sql(f'DROP DATABASE "{name}"')
        self.owned.remove(name)

    def close(self):
        try:
            for name in list(self.owned):
                self.drop(name)
        finally:
            self.admin.dispose()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def child_environment(url, storage, provider):
    name = make_url(url).database
    validate_name(name)
    env = os.environ.copy()
    env.update(
        DATABASE_URL=url,
        STORAGE_DIR=str(storage),
        STORAGE_BACKEND="local",
        AUTH_MODE="local",
        LOCAL_WORKSPACE_ID="00000000-0000-0000-0000-000000000001",
        APP_ENVIRONMENT="local",
        OMP_THREAD_LIMIT="1",
    )
    if provider == "fallback":
        env["GEMINI_API_KEY"] = ""
    return env
