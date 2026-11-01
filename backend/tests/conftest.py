import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app


@pytest.fixture(scope="session")
def database():
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://invoiceguard:local_demo_only@127.0.0.1:5432/invoiceguard_test",
    )
    if not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError("Tests require a dedicated database ending in _test")
    original = os.environ.get("DATABASE_URL")
    from app.config import get_settings

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original
        get_settings.cache_clear()
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(database):
    with database.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def isolated_runtime_settings(monkeypatch):
    """Never inherit hosted auth, object storage or a real provider key in regressions."""
    from app.config import get_settings

    monkeypatch.setenv("APP_ENVIRONMENT", "local")
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_WORKSPACE_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
