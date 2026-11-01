"""Explicit isolated-test reset; refuses ordinary application databases."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Base
from app.seed import seed

if __name__ == "__main__":
    url = get_settings().database_url
    if not (make_url(url).database or "").endswith(("_test", "_e2e")):
        raise RuntimeError("Reset refused: requires a dedicated *_test or *_e2e database.")
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url)
    with engine.begin() as connection:
        tables = ",".join('"' + t.name + '"' for t in reversed(Base.metadata.sorted_tables))
        connection.execute(text("TRUNCATE " + tables + " CASCADE"))
        with Session(bind=connection) as session:
            seed(session)
            session.flush()
    engine.dispose()
    print("Isolated test database reset and seeded. Demo database unchanged.")
