import json
from xml.etree.ElementTree import ParseError

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_reviewer
from app.db import get_db
from app.models import QueryVersion, Record, RecordQueryLink, Reviewer, RunLog
from app.schemas import ActiveIn, ImportIn, QueryIn, QueryVersionOut, RunLogOut
from app.services import europepmc, pipeline, pubmed, state

router = APIRouter(prefix="/queries", tags=["queries"], dependencies=[Depends(current_reviewer)])
COUNTERS = {"pubmed": pubmed.count, "europepmc": europepmc.count}


def _get(db: Session, version_id: int) -> QueryVersion:
    qv = db.get(QueryVersion, version_id)
    if qv is None:
        raise HTTPException(404, "Query version not found")
    return qv


def _new_version(db: Session, reviewer: Reviewer, **fields) -> QueryVersion:
    qv = QueryVersion(
        version_number=(db.scalar(select(func.max(QueryVersion.version_number))) or 0) + 1,
        created_by=reviewer.id,
        **fields,
    )
    db.add(qv)
    db.commit()
    return qv


@router.post("/preview", response_model=QueryVersionOut)
def preview(body: QueryIn, db: Session = Depends(get_db), reviewer: Reviewer = Depends(current_reviewer)):
    """Counts hits in each source and saves a new version. Versions are never edited: an edit is a child version."""
    if body.parent_version_id:
        _get(db, body.parent_version_id)
    hits = {}
    for source in body.sources:
        try:
            hits[source] = COUNTERS[source](body.query_string, body.date_from, body.date_to)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"{source} request failed: {e}")
    return _new_version(
        db,
        reviewer,
        parent_version_id=body.parent_version_id,
        query_string=body.query_string,
        date_from=body.date_from,
        date_to=body.date_to,
        sources=body.sources,
        source_hits=hits,
        hit_count=sum(hits.values()),
        status="previewed",
    )


@router.get("", response_model=list[QueryVersionOut])
def list_versions(db: Session = Depends(get_db)):
    return db.scalars(select(QueryVersion).order_by(QueryVersion.version_number.desc())).all()


@router.post("/{version_id}/fetch", response_model=list[RunLogOut])
def fetch(version_id: int, db: Session = Depends(get_db)):
    return pipeline.run(db, _get(db, version_id))


@router.patch("/{version_id}", response_model=list[RunLogOut])
def set_active(version_id: int, body: ActiveIn, db: Session = Depends(get_db)):
    """Add a fetched version's records to the working set or take them out, then dedupe the new set."""
    qv = _get(db, version_id)
    if qv.status != "fetched":
        raise HTTPException(409, "Fetch this version first")
    qv.active = body.active
    db.commit()
    return pipeline.run(db, qv, pipeline.RESCREEN)


def _root(versions: dict[int, QueryVersion], v: QueryVersion) -> int:
    while v.parent_version_id in versions:
        v = versions[v.parent_version_id]
    return v.id


def _first_snapshot(db: Session, version_id: int) -> int | None:
    return db.scalar(
        select(func.min(RunLog.id)).where(
            RunLog.query_version_id == version_id, RunLog.step == "dedupe", RunLog.status == "ok"
        )
    )


def _linked(db: Session, version_id: int) -> set[int]:
    return set(
        db.scalars(select(RecordQueryLink.record_id).where(RecordQueryLink.query_version_id == version_id))
    )


def _groups_within(db: Session, run_id: int | None, ids: set[int]) -> set[frozenset[int]]:
    return {g & ids for g in state.groups_of(db, run_id) if len(g & ids) > 1}


@router.post("/{version_id}/revert")
def revert(version_id: int, db: Session = Depends(get_db)):
    """Make this version the only one of its edit history in the working set, then check that its records and
    duplicate groups are exactly what they were when it was first fetched. Nothing is deleted or re-fetched."""
    qv = _get(db, version_id)
    original = _first_snapshot(db, qv.id)
    if qv.status != "fetched" or original is None:
        raise HTTPException(409, "Only a fetched version can be reverted to")
    versions = {v.id: v for v in db.scalars(select(QueryVersion))}
    root = _root(versions, qv)
    for v in versions.values():
        if _root(versions, v) == root:
            v.active = v.id == qv.id
    db.commit()
    logs = pipeline.run(db, qv, pipeline.RESCREEN)
    ids = _linked(db, qv.id)
    before = _groups_within(db, original, ids)
    after = _groups_within(db, state.current_run(db), ids)
    return {
        "logs": [RunLogOut.model_validate(entry) for entry in logs],
        "records": len(ids),
        "groups": len(after),
        "identical_to_original": before == after and all(e.status == "ok" for e in logs),
    }


@router.get("/{version_id}/runs", response_model=list[RunLogOut])
def runs(version_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(RunLog).where(RunLog.query_version_id == version_id).order_by(RunLog.id.desc()).limit(50)
    ).all()


def _latest_snapshot(db: Session, version_id: int) -> int | None:
    return db.scalar(
        select(func.max(RunLog.id)).where(
            RunLog.query_version_id == version_id, RunLog.step == "dedupe", RunLog.status == "ok"
        )
    )


@router.get("/{version_id}/diff")
def diff(version_id: int, against: int | None = None, db: Session = Depends(get_db)):
    """Against `against` (default: the parent): records added and removed, and duplicate groups that this version's
    deduplication formed and the other's did not (merges that can bring conflicting decisions together)."""
    v = _get(db, version_id)
    other = against or v.parent_version_id
    if other is None or db.get(QueryVersion, other) is None:
        raise HTTPException(404, "No version to compare against")
    new, old = _linked(db, version_id), _linked(db, other)
    merged = _groups_within(db, _latest_snapshot(db, version_id), new) - _groups_within(
        db, _latest_snapshot(db, other), old
    )
    shown = (new ^ old) | {i for g in merged for i in g}
    records = {r.id: r for r in db.scalars(select(Record).where(Record.id.in_(shown)))}
    status = state.screen_status(db, list(shown))

    def brief(i: int) -> dict:
        r = records[i]
        s = status.get(i, {})
        return {
            "id": i,
            "pmid": r.pmid,
            "title": r.title,
            "year": r.year,
            "first_author": r.first_author,
            "status": s.get("label", "unscreened"),
            "reason": s.get("reason", ""),
        }

    return {
        "against": other,
        "added": [brief(i) for i in sorted(new - old)],
        "removed": [brief(i) for i in sorted(old - new)],
        "unchanged": len(new & old),
        "merged": [
            {
                "records": [brief(i) for i in sorted(g)],
                "conflict": len({status.get(i, {}).get("label") for i in g} - {None}) > 1,
            }
            for g in sorted(merged, key=min)
        ],
    }


def parse_snapshot(content: str) -> list[dict]:
    """A frozen snapshot: PubMed EFetch XML, or Europe PMC search JSON (a whole response or a list of results)."""
    text = content.lstrip("﻿").strip()
    if text.startswith("<"):
        return pubmed.parse_efetch(text.encode())
    data = json.loads(text)
    results = data if isinstance(data, list) else data.get("resultList", {}).get("result", [])
    return [europepmc.parse_result(r) for r in results]


@router.post("/import", response_model=list[RunLogOut])
def import_snapshot(
    body: ImportIn, db: Session = Depends(get_db), reviewer: Reviewer = Depends(current_reviewer)
):
    """Load records from a file instead of a live search; the run is identical from dedupe onwards."""
    try:
        parsed = parse_snapshot(body.content)
    except (ValueError, AttributeError, KeyError, TypeError, ParseError) as e:
        raise HTTPException(422, f"Not a PubMed XML or Europe PMC JSON file: {e}")
    if not parsed:
        raise HTTPException(422, "The file has no records")
    qv = _new_version(
        db,
        reviewer,
        query_string=f"Imported file: {body.filename}",
        sources=["import"],
        source_hits={"import": len(parsed)},
        hit_count=len(parsed),
        status="previewed",
    )

    def load(db: Session, qv: QueryVersion, entry: RunLog) -> dict:
        ids, new = pipeline.store(db, parsed, "import")
        pipeline.link(db, qv, ids)
        pipeline.activate(db, qv)
        db.commit()
        total = len(set(ids))
        return {"found": total, "new": new, "already_known": total - new, "by_source": {"import": total}}

    return pipeline.run(db, qv, [("fetch", load), *pipeline.RESCREEN])
