import pytest

from app.config import settings
from app.seed import seed


@pytest.fixture
def token(client):
    seed()
    r = client.post("/auth/login", json={"email": settings.seed_email, "password": settings.seed_password})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_login(client, auth):
    assert client.get("/auth/me", headers=auth).json()["email"] == settings.seed_email
    assert client.get("/auth/me").status_code == 401
    bad = client.post("/auth/login", json={"email": settings.seed_email, "password": "nope"})
    assert bad.status_code == 401
