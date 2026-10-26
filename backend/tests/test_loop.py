"""Level 2: sources, the working set, revert, diff with merged groups, import, criteria and group decisions."""

import json

import httpx
import respx
from sqlalchemy import select
from test_api import FIXTURE, auth, loaded, mock_pubmed, token  # noqa: F401  (fixtures)

from app.models import MachineResult, Record
from app.services import europepmc
from app.services.pubmed import parse_efetch

PMIDS = [r["pmid"] for r in parse_efetch(FIXTURE.read_bytes())]
EPMC = [
    {
        "id": "42815506",
        "source": "MED",
        "pmid": "42815506",
        "title": "Already stored via PubMed",
        "pubYear": "2026",
    },
    {  # a preprint copy of a PubMed record: no PMID, same DOI
        "id": "PPR1",
        "source": "PPR",
        "doi": "10.1371/journal.pone.0356480",
        "title": '"A better system" - managing the adverse effects of metformin',
        "pubYear": "2026",
        "authorList": {"author": [{"lastName": "Logan", "initials": "A"}]},
        "abstractText": "<h4>Methods</h4>Adults with type 2 diabetes were interviewed.",
    },
    {
        "id": "PPR2",
        "source": "PPR",
        "title": "Metformin in older adults: a cohort study",
        "pubYear": "2025",
        "language": "eng",
        "authorList": {"author": [{"lastName": "Novak", "initials": "J"}]},
        "abstractText": "Adults with type 2 diabetes received metformin. The primary outcome was HbA1c.",
    },
]


def mock_europepmc(results=EPMC):
    def search(request):
        if request.url.params["resultType"] == "idlist":
            return httpx.Response(200, json={"hitCount": len(results)})
        return httpx.Response(200, json={"hitCount": len(results), "resultList": {"result": results}})

    return respx.get(europepmc.SEARCH).mock(side_effect=search)


def post(client, auth, url, body=None):
    return client.post(url, json=body, headers=auth).json()


def screen_as(client, headers, rid, label, reason=""):
    body = {"decision_type": "screen", "value": {"label": label, "reason": reason}}
    return client.post(f"/records/{rid}/decisions", json=body, headers=headers).json()


@respx.mock
def test_europepmc_source_diff_and_merged_groups(client, auth, db):
    mock_pubmed(PMIDS)
    mock_europepmc()
    v1 = post(client, auth, "/queries/preview", {"query_string": "metformin"})
    post(client, auth, f"/queries/{v1['id']}/fetch")
    edit = {"query_string": "metformin", "sources": ["pubmed", "europepmc"], "parent_version_id": v1["id"]}
    v2 = post(client, auth, "/queries/preview", edit)
    assert v2["source_hits"] == {"pubmed": 16, "europepmc": 3} and v2["hit_count"] == 19

    logs = post(client, auth, f"/queries/{v2['id']}/fetch")
    assert all(entry["status"] == "ok" for entry in logs)
    by_source = {"pubmed": 16, "europepmc": 3}
    assert logs[0]["details"] == {"found": 18, "new": 2, "already_known": 16, "by_source": by_source}
    preprint = db.scalar(select(Record).where(Record.source_id == "PPR:PPR1"))
    assert (
        preprint.source == "europepmc" and preprint.doi is None and preprint.abstract.startswith("METHODS: ")
    )

    listed = {r["id"]: r for r in client.get("/records", headers=auth).json()}
    assert preprint.id not in listed and len(listed) == 17  # the preprint is a duplicate (same DOI)
    logan = db.scalar(select(Record).where(Record.pmid == "42758689"))
    assert listed[logan.id]["duplicates"] == 1 and listed[logan.id]["origin"] == "pubmed"

    d = client.get(f"/queries/{v2['id']}/diff", headers=auth).json()
    assert {r["title"] for r in d["added"]} == {preprint.title, "Metformin in older adults: a cohort study"}
    assert d["removed"] == [] and d["unchanged"] == 16
    assert [[r["id"] for r in g["records"]] for g in d["merged"]] == [[logan.id, preprint.id]]
    assert all(r["status"] in ("include", "exclude", "maybe") for r in d["added"])


@respx.mock
def test_revert_gives_the_same_records_and_groups(client, auth):
    mock_pubmed(PMIDS)
    mock_europepmc()
    v1 = post(
        client, auth, "/queries/preview", {"query_string": "metformin", "sources": ["pubmed", "europepmc"]}
    )
    post(client, auth, f"/queries/{v1['id']}/fetch")
    before = client.get("/records", headers=auth).json()

    respx.reset()
    mock_pubmed(PMIDS[5:])
    v2 = post(
        client, auth, "/queries/preview", {"query_string": "metformin NOT x", "parent_version_id": v1["id"]}
    )
    post(client, auth, f"/queries/{v2['id']}/fetch")
    versions = {v["id"]: v for v in client.get("/queries", headers=auth).json()}
    assert versions[v2["id"]]["active"] and not versions[v1["id"]]["active"]  # the edit replaced v1
    assert len(client.get("/records", headers=auth).json()) == 11

    out = post(client, auth, f"/queries/{v1['id']}/revert")
    assert out["identical_to_original"] and out["records"] == 18 and out["groups"] == 1

    def key(rows):
        return [(r["id"], r["duplicates"], r["status"]) for r in rows]

    assert key(client.get("/records", headers=auth).json()) == key(before)
    assert client.post(f"/queries/{v1['id'] + 99}/revert", headers=auth).status_code == 404


def test_toggle_working_set(client, auth, loaded):
    assert len(client.get("/records", headers=auth).json()) == 16
    logs = client.patch(f"/queries/{loaded['id']}", json={"active": False}, headers=auth).json()
    assert [entry["step"] for entry in logs] == ["dedupe", "screen", "pico"]
    assert client.get("/records", headers=auth).json() == []
    client.patch(f"/queries/{loaded['id']}", json={"active": True}, headers=auth)
    assert len(client.get("/records", headers=auth).json()) == 16


def test_import_snapshot_files(client, auth):
    logs = post(
        client, auth, "/queries/import", {"filename": "frozen.xml", "content": FIXTURE.read_text("utf-8")}
    )
    assert [(e["step"], e["status"]) for e in logs] == [
        ("fetch", "ok"),
        ("dedupe", "ok"),
        ("screen", "ok"),
        ("pico", "ok"),
    ]
    assert logs[0]["details"]["new"] == 16 and len(client.get("/records", headers=auth).json()) == 16

    content = json.dumps({"resultList": {"result": EPMC}})
    epmc = post(client, auth, "/queries/import", {"filename": "epmc.json", "content": content})
    assert epmc[0]["details"] == {"found": 3, "new": 2, "already_known": 1, "by_source": {"import": 3}}
    latest = client.get("/queries", headers=auth).json()[0]
    assert latest["sources"] == ["import"] and latest["active"]
    bad = client.post(
        "/queries/import", json={"filename": "x.txt", "content": "not a snapshot"}, headers=auth
    )
    assert bad.status_code == 422


def test_criteria_can_be_switched_off_and_rescreen(client, auth, loaded):
    criteria = client.get("/screening/criteria", headers=auth).json()
    assert len(criteria) == 8 and all(c["active"] and c["why"] and c["basis"] for c in criteria)
    excluded = client.get("/records?status=exclude", headers=auth).json()
    french = [r["id"] for r in excluded if r["reason"] == "non-English (fre)"]
    assert french

    body = {"active": ["case_report"], "note": "translator joined"}
    logs = client.put("/screening/criteria", json=body, headers=auth).json()
    assert [e["step"] for e in logs] == ["screen", "pico"] and logs[0]["details"]["screened"] == 16
    rows = {r["id"]: r for r in client.get("/records", headers=auth).json()}
    assert all(rows[i]["status"] != "exclude" for i in french)
    active = [c["key"] for c in client.get("/screening/criteria", headers=auth).json() if c["active"]]
    assert active == ["case_report"]
    assert client.put("/screening/criteria", json={"active": ["nope"]}, headers=auth).status_code == 422

    # Switching back reruns too, so the earlier criteria's results become effective again.
    every = {"active": [c["key"] for c in criteria]}
    assert client.put("/screening/criteria", json=every, headers=auth).json()[0]["details"]["screened"] == 16
    rows = {r["id"]: r for r in client.get("/records", headers=auth).json()}
    assert all(rows[i]["status"] == "exclude" for i in french)


def test_decisions_follow_the_group_and_merges_show_conflicts(client, auth, loaded, db):
    from app.auth import create_token, hash_password
    from app.models import Reviewer

    other = Reviewer(email="b@example.com", password_hash=hash_password("x"), name="B")
    db.add(other)
    db.commit()
    auth_b = {"Authorization": f"Bearer {create_token(other.id)}"}
    a, b = [r["id"] for r in client.get("/records", headers=auth).json()[:2]]
    screen_as(client, auth, a, "include")
    screen_as(client, auth_b, b, "exclude", "off topic")
    assert client.get("/records?conflict=true", headers=auth).json() == []

    # The two records turn out to be one: the merged group now holds conflicting decisions.
    dup = {"decision_type": "duplicate", "value": {"duplicate_of": a}}
    client.post(f"/records/{b}/decisions", json=dup, headers=auth)
    flagged = client.get("/records?conflict=true", headers=auth).json()
    assert [r["id"] for r in flagged] == [a] and flagged[0]["status"] == "exclude"
    detail = client.get(f"/records/{a}", headers=auth).json()
    assert detail["conflict"] and [g["id"] for g in detail["group"]] == [a, b]
    assert detail["group"][1]["votes"] == [{"reviewer": "B", "label": "exclude"}]

    # A decision on the group is written to every member; once both reviewers agree the conflict clears.
    screen_as(client, auth_b, a, "include")
    assert client.get("/records?conflict=true", headers=auth).json() == []
    assert client.get(f"/records/{b}", headers=auth).json()["history"][0]["value"]["label"] == "include"


def test_human_include_gets_pico_tags(client, auth, loaded, db):
    excluded = client.get("/records?status=exclude", headers=auth).json()
    rid = next(r["id"] for r in excluded if "case report" in r["reason"])
    assert client.get(f"/records/{rid}", headers=auth).json()["pico"] == []
    screen_as(client, auth, rid, "include")
    q = select(MachineResult).where(MachineResult.record_id == rid, MachineResult.step == "pico")
    assert len(db.scalars(q).all()) == 1
