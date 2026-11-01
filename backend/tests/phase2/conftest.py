import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import Base
from app.seed import seed


@pytest.fixture
def workflow_db(database, tmp_path, monkeypatch):
    # Dedicated *_test database, no production/demo data. Sequential pytest execution.
    factory = sessionmaker(database)
    tables = ",".join('"' + t.name + '"' for t in reversed(Base.metadata.sorted_tables))
    with database.begin() as conn:
        conn.execute(text("TRUNCATE " + tables + " CASCADE"))
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    with factory.begin() as session:
        seed(session)
    yield factory
    with database.begin() as conn:
        conn.execute(text("TRUNCATE " + tables + " CASCADE"))
    get_settings.cache_clear()
