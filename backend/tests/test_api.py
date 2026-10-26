import httpx
import pytest
import respx

from app.config import settings
from app.seed import seed
from app.services.pubmed import EUTILS


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


@respx.mock
def test_preview_creates_versions(client, auth):
    route = respx.post(f"{EUTILS}/esearch.fcgi").mock(
        return_value=httpx.Response(200, json={"esearchresult": {"count": "1234"}})
    )
    body = {"query_string": '"type 2 diabetes" AND metformin', "date_from": "2020-01-01"}
    v1 = client.post("/queries/preview", json=body, headers=auth).json()
    v2 = client.post("/queries/preview", json={"query_string": "metformin NOT mice"}, headers=auth).json()

    assert v1["hit_count"] == 1234 and v1["version_number"] == 1 and v1["status"] == "previewed"
    assert v2["version_number"] == 2 and v2["parent_version_id"] == v1["id"]
    sent = dict(httpx.QueryParams(route.calls[0].request.content.decode()))
    assert sent["rettype"] == "count" and sent["mindate"] == "2020/01/01" and sent["tool"]
    listed = client.get("/queries", headers=auth).json()
    assert [v["version_number"] for v in listed] == [2, 1]


def test_preview_rejects_bad_dates(client, auth):
    body = {"query_string": "x", "date_from": "2021-01-01", "date_to": "2020-01-01"}
    assert client.post("/queries/preview", json=body, headers=auth).status_code == 422
