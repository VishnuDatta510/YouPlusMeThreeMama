import csv
import io
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import settings
from app.models import Record, RecordQueryLink
from app.seed import seed
from app.services.pubmed import EUTILS, parse_efetch


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


FIXTURE = Path(__file__).parent / "fixtures" / "efetch_sample.xml"


def mock_pubmed(pmids):
    def esearch(request):
        params = dict(httpx.QueryParams(request.content.decode()))
        if params.get("rettype") == "count":
            return httpx.Response(200, json={"esearchresult": {"count": str(len(pmids))}})
        return httpx.Response(200, json={"esearchresult": {"idlist": pmids}})

    respx.post(f"{EUTILS}/esearch.fcgi").mock(side_effect=esearch)
    return respx.post(f"{EUTILS}/efetch.fcgi").mock(
        return_value=httpx.Response(200, content=FIXTURE.read_bytes())
    )


@respx.mock
def test_fetch_is_incremental(client, auth, db):
    pmids = [r["pmid"] for r in parse_efetch(FIXTURE.read_bytes())]
    efetch = mock_pubmed(pmids)
    v1 = client.post("/queries/preview", json={"query_string": "metformin"}, headers=auth).json()
    logs = client.post(f"/queries/{v1['id']}/fetch", headers=auth).json()
    assert [(s["step"], s["status"]) for s in logs] == [
        ("fetch", "ok"),
        ("dedupe", "ok"),
        ("screen", "ok"),
        ("pico", "ok"),
    ]
    assert logs[3]["details"]["tagged"] > 0
    assert logs[0]["details"]["new"] == 16
    assert db.scalar(select(func.count()).select_from(Record)) == 16
    screened = logs[2]["details"]
    assert screened["screened"] == 16 and screened["exclude"] >= 6  # 4 case reports + 4 French at least

    v2 = client.post("/queries/preview", json={"query_string": "metformin again"}, headers=auth).json()
    logs = client.post(f"/queries/{v2['id']}/fetch", headers=auth).json()
    assert logs[0]["details"] == {"found": 16, "new": 0, "already_known": 16}
    assert logs[2]["details"]["screened"] == 0  # same method version, nothing re-screened
    assert efetch.call_count == 1
    assert db.scalar(select(func.count()).select_from(RecordQueryLink)) == 32
    runs = client.get(f"/queries/{v2['id']}/runs", headers=auth).json()
    assert [r["step"] for r in runs] == ["pico", "screen", "dedupe", "fetch"]


@respx.mock
def test_preview_pubmed_error_is_502(client, auth):
    respx.post(f"{EUTILS}/esearch.fcgi").mock(return_value=httpx.Response(400, text="bad"))
    v = client.post("/queries/preview", json={"query_string": "x"}, headers=auth)
    assert v.status_code == 502


@pytest.fixture
def loaded(client, auth):
    with respx.mock:
        mock_pubmed([r["pmid"] for r in parse_efetch(FIXTURE.read_bytes())])
        v = client.post("/queries/preview", json={"query_string": "metformin"}, headers=auth).json()
        client.post(f"/queries/{v['id']}/fetch", headers=auth)
    return v


def test_records_list_and_status_filter(client, auth, loaded):
    rows = client.get("/records", headers=auth).json()
    assert len(rows) == 16 and all(r["source"] == "machine" for r in rows)
    excluded = client.get("/records?status=exclude", headers=auth).json()
    assert excluded and all(r["status"] == "exclude" and r["reason"] for r in excluded)
    assert client.get(f"/records?query_version_id={loaded['id'] + 99}", headers=auth).json() == []


def test_screen_decision_overrides_machine_and_is_logged(client, auth, loaded):
    rid = client.get("/records?status=exclude", headers=auth).json()[0]["id"]
    url = f"/records/{rid}/decisions"
    assert (
        client.post(
            url, json={"decision_type": "screen", "value": {"label": "exclude"}}, headers=auth
        ).status_code
        == 422
    )
    body = {"decision_type": "screen", "value": {"label": "include", "reason": "relevant"}, "note": "checked"}
    detail = client.post(url, json=body, headers=auth).json()
    assert detail["status"] == {"label": "include", "reason": "relevant", "source": "human"}
    detail = client.post(
        url, json={"decision_type": "screen", "value": {"label": "maybe"}}, headers=auth
    ).json()
    assert detail["status"]["label"] == "maybe"
    assert [h["value"]["label"] for h in detail["history"]] == ["maybe", "include"]
    assert detail["history"][1]["note"] == "checked" and detail["history"][0]["reviewer"] == "Demo Reviewer"


def test_duplicate_decision_hides_record(client, auth, loaded):
    a, b = [r["id"] for r in client.get("/records", headers=auth).json()[:2]]
    url = f"/records/{b}/decisions"
    assert (
        client.post(
            url, json={"decision_type": "duplicate", "value": {"duplicate_of": b}}, headers=auth
        ).status_code
        == 422
    )
    assert (
        client.post(
            url, json={"decision_type": "duplicate", "value": {"duplicate_of": 9999}}, headers=auth
        ).status_code
        == 404
    )
    detail = client.post(
        url, json={"decision_type": "duplicate", "value": {"duplicate_of": a}}, headers=auth
    ).json()
    assert detail["duplicate_of"] == a
    rows = {r["id"]: r for r in client.get("/records", headers=auth).json()}
    assert b not in rows and rows[a]["duplicates"] == 1
    client.post(url, json={"decision_type": "duplicate", "value": {"duplicate_of": None}}, headers=auth)
    assert b in {r["id"] for r in client.get("/records", headers=auth).json()}


def test_pico_decision_replaces_spans(client, auth, loaded):
    rid = next(r["id"] for r in client.get("/records?status=include", headers=auth).json())
    abstract = client.get(f"/records/{rid}", headers=auth).json()["abstract"]
    url = f"/records/{rid}/decisions"
    spans = [{"type": "P", "start": 0, "end": 10}]
    detail = client.post(url, json={"decision_type": "pico", "value": {"spans": spans}}, headers=auth).json()
    assert detail["pico"] == [{"type": "P", "start": 0, "end": 10, "text": abstract[:10]}]
    bad = {"decision_type": "pico", "value": {"spans": [{"type": "O", "start": 0, "end": len(abstract) + 1}]}}
    assert client.post(url, json=bad, headers=auth).status_code == 422
    overlap = [{"type": "P", "start": 0, "end": 10}, {"type": "I", "start": 5, "end": 15}]
    assert (
        client.post(
            url, json={"decision_type": "pico", "value": {"spans": overlap}}, headers=auth
        ).status_code
        == 422
    )
    assert client.get("/records/9999", headers=auth).status_code == 404


def test_export_included_csv(client, auth, loaded):
    rows = client.get("/records", headers=auth).json()
    included = [r for r in rows if r["status"] == "include"]
    excluded = next(r for r in rows if r["status"] == "exclude")
    client.post(
        f"/records/{included[0]['id']}/decisions",
        json={"decision_type": "screen", "value": {"label": "exclude", "reason": "off topic"}},
        headers=auth,
    )
    client.post(
        f"/records/{excluded['id']}/decisions",
        json={"decision_type": "screen", "value": {"label": "include"}},
        headers=auth,
    )
    res = client.get("/export/included.csv", headers=auth)
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    out = list(csv.DictReader(io.StringIO(res.text)))
    assert {r["pmid"] for r in out} == {r["pmid"] for r in included[1:]} | {excluded["pmid"]}
    assert list(out[0]) == ["pmid", "doi", "title", "authors", "year", "journal"] + [
        "population",
        "intervention",
        "comparator",
        "outcome",
    ]
    assert any(r["population"] or r["intervention"] or r["outcome"] for r in out)
    assert client.get("/export/included.csv").status_code == 401


def test_fuzzy_duplicate_needs_review_until_decided(client, auth, loaded, db):
    from app.models import DedupGroup, DedupGroupMember

    a, b = [r["id"] for r in client.get("/records", headers=auth).json()[:2]]
    group = DedupGroup(representative_record_id=a)
    db.add(group)
    db.flush()
    db.add(
        DedupGroupMember(group_id=group.id, record_id=b, match_method="fuzzy", score=90, needs_review=True)
    )
    db.commit()
    flagged = client.get("/records?needs_review=true", headers=auth).json()
    assert [r["id"] for r in flagged] == [a] and flagged[0]["needs_review"]
    client.post(
        f"/records/{b}/decisions",
        json={"decision_type": "duplicate", "value": {"duplicate_of": None}},
        headers=auth,
    )
    assert client.get("/records?needs_review=true", headers=auth).json() == []


def test_cors_allows_origin_regex(client, monkeypatch):
    import importlib

    import app.main

    monkeypatch.setattr(settings, "cors_origin_regex", r"https://.*\.vercel\.app")
    reloaded = importlib.reload(app.main)
    try:
        r = TestClient(reloaded.app).get("/health", headers={"Origin": "https://pr-1.vercel.app"})
        assert r.headers["access-control-allow-origin"] == "https://pr-1.vercel.app"
    finally:
        monkeypatch.undo()
        importlib.reload(app.main)


@respx.mock
def test_diff_against_parent_version(client, auth):
    pmids = [r["pmid"] for r in parse_efetch(FIXTURE.read_bytes())]
    mock_pubmed(pmids)
    v1 = client.post("/queries/preview", json={"query_string": "metformin"}, headers=auth).json()
    client.post(f"/queries/{v1['id']}/fetch", headers=auth)
    respx.reset()
    mock_pubmed(pmids[3:])
    v2 = client.post("/queries/preview", json={"query_string": "metformin NOT mice"}, headers=auth).json()
    client.post(f"/queries/{v2['id']}/fetch", headers=auth)

    d = client.get(f"/queries/{v2['id']}/diff", headers=auth).json()
    assert d["against"] == v1["id"] and d["added"] == [] and d["unchanged"] == len(pmids) - 3
    assert sorted(r["pmid"] for r in d["removed"]) == sorted(pmids[:3])
    assert client.get(f"/queries/{v1['id']}/diff", headers=auth).status_code == 404


def test_restore_appends_an_earlier_value(client, auth, loaded):
    rid = next(r["id"] for r in client.get("/records?status=include", headers=auth).json())
    url = f"/records/{rid}/decisions"
    first = client.post(
        url,
        json={"decision_type": "pico", "value": {"spans": [{"type": "P", "start": 0, "end": 10}]}},
        headers=auth,
    ).json()
    client.post(url, json={"decision_type": "pico", "value": {"spans": []}}, headers=auth)
    old = first["history"][0]  # its spans carry the server-derived `text`, as the UI sends them back
    r = client.post(
        url, json={"decision_type": "pico", "value": old["value"], "note": "Restored"}, headers=auth
    )
    assert r.status_code == 200
    assert r.json()["pico"] == first["pico"] and len(r.json()["history"]) == 3


def test_reviewer_disagreement_is_flagged(client, auth, loaded, db):
    from app.auth import create_token, hash_password
    from app.models import Reviewer

    other = Reviewer(email="b@example.com", password_hash=hash_password("x"), name="B")
    db.add(other)
    db.commit()
    auth_b = {"Authorization": f"Bearer {create_token(other.id)}"}
    rid = client.get("/records", headers=auth).json()[0]["id"]
    url = f"/records/{rid}/decisions"
    client.post(url, json={"decision_type": "screen", "value": {"label": "include"}}, headers=auth)
    assert client.get("/records?conflict=true", headers=auth).json() == []
    client.post(url, json={"decision_type": "screen", "value": {"label": "maybe"}}, headers=auth_b)
    flagged = client.get("/records?conflict=true", headers=auth).json()
    assert [r["id"] for r in flagged] == [rid] and flagged[0]["status"] == "maybe"
    client.post(url, json={"decision_type": "screen", "value": {"label": "maybe"}}, headers=auth)
    assert client.get("/records?conflict=true", headers=auth).json() == []
