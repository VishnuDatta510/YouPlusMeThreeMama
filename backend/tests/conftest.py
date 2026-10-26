import os

# Point the app at a dedicated test database before anything imports app.db.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/minirayyan_test"
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import models  # noqa: E402, F401
from app.db import Base, SessionLocal, engine  # noqa: E402


def _ensure_database():
    url = engine.url
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("select 1 from pg_database where datname = :n"), {"n": url.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'create database "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def schema():
    _ensure_database()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"truncate {tables} restart identity cascade"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)
