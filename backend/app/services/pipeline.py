"""Runs fetch → dedupe → screen → pico for a query version, writing one run_log row per step."""

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    DedupGroup,
    DedupGroupMember,
    MachineResult,
    QueryVersion,
    Record,
    RecordQueryLink,
    RunLog,
)
from app.services import dedupe as dedupe_service
from app.services import pubmed, screening

log = logging.getLogger(__name__)
EFETCH_BATCH = 100


def fetch(db: Session, qv: QueryVersion) -> dict:
    """Incremental: PMIDs already in records are linked to this version but not re-fetched."""
    ids = pubmed.search_ids(qv.query_string, qv.date_from, qv.date_to, settings.max_fetch)
    known = dict(db.execute(select(Record.pmid, Record.id).where(Record.pmid.in_(ids))).all())
    new_ids = [i for i in ids if i not in known]
    for start in range(0, len(new_ids), EFETCH_BATCH):
        parsed = pubmed.parse_efetch(pubmed.efetch(new_ids[start : start + EFETCH_BATCH]))
        dois = {p["doi"] for p in parsed if p["doi"]}
        taken = set(db.scalars(select(Record.doi).where(Record.doi.in_(dois))))
        for p in parsed:
            if p["pmid"] in known:
                continue
            doi = p["doi"]
            if doi in taken:
                doi = None  # DOI column is unique; the copy stays in raw so dedupe still matches it
            elif doi:
                taken.add(doi)
            rec = Record(**{**p, "doi": doi}, source="pubmed", raw=p)
            db.add(rec)
            db.flush()
            known[p["pmid"]] = rec.id
    linked = [{"record_id": known[i], "query_version_id": qv.id} for i in ids if i in known]
    if linked:
        db.execute(insert(RecordQueryLink).values(linked).on_conflict_do_nothing())
    qv.status = "fetched"
    db.commit()
    return {"found": len(ids), "new": len(new_ids), "already_known": len(ids) - len(new_ids)}


def dedupe(db: Session, qv: QueryVersion) -> dict:
    """Groups are derived data: rebuilt over the whole record set. Human duplicate decisions live elsewhere."""
    rows = db.execute(
        select(
            Record.id,
            Record.pmid,
            Record.doi,
            Record.raw["doi"].astext,
            Record.title,
            Record.year,
            Record.first_author,
        )
    ).all()
    candidates = [
        dedupe_service.Candidate(
            id=r[0], pmid=r[1], doi=r[2] or r[3], title=r[4], year=r[5], first_author=r[6]
        )
        for r in rows
    ]
    matches = dedupe_service.find_duplicates(candidates)
    db.execute(delete(DedupGroupMember))
    db.execute(delete(DedupGroup))
    groups: dict[int, DedupGroup] = {}
    for m in matches:
        if m.representative_id not in groups:
            groups[m.representative_id] = DedupGroup(representative_record_id=m.representative_id)
            db.add(groups[m.representative_id])
    db.flush()
    db.add_all(
        DedupGroupMember(
            group_id=groups[m.representative_id].id,
            record_id=m.record_id,
            match_method=m.method,
            score=m.score,
            needs_review=m.needs_review,
        )
        for m in matches
    )
    db.commit()
    return {
        "records": len(candidates),
        "groups": len(groups),
        "duplicates": len(matches),
        "needs_review": sum(m.needs_review for m in matches),
    }


def _records_without_result(db: Session, qv: QueryVersion, step: str, method: str):
    """Records linked to this version that have no machine result for (step, method) yet."""
    done = select(MachineResult.record_id).where(
        MachineResult.step == step, MachineResult.method_version == method
    )
    return db.scalars(
        select(Record)
        .join(RecordQueryLink, RecordQueryLink.record_id == Record.id)
        .where(RecordQueryLink.query_version_id == qv.id, Record.id.not_in(done))
        .order_by(Record.id)
    ).all()


def screen(db: Session, qv: QueryVersion) -> dict:
    criteria = screening.active_criteria()
    method = screening.method_version(criteria)
    counts = {"include": 0, "exclude": 0, "maybe": 0}
    for r in _records_without_result(db, qv, "screen", method):
        out = screening.screen(r, criteria)
        counts[out["label"]] += 1
        db.add(
            MachineResult(
                record_id=r.id, query_version_id=qv.id, step="screen", method_version=method, output=out
            )
        )
    db.commit()
    return {"method_version": method, "screened": sum(counts.values()), **counts}


STEPS = [("fetch", fetch), ("dedupe", dedupe), ("screen", screen)]


def run(db: Session, qv: QueryVersion) -> list[RunLog]:
    logs = []
    for name, fn in STEPS:
        entry = RunLog(query_version_id=qv.id, step=name, status="running", details={})
        db.add(entry)
        db.commit()
        logs.append(entry)
        try:
            entry.details, entry.status = fn(db, qv), "ok"
        except Exception as e:
            log.exception("pipeline step %s failed for query version %s", name, qv.id)
            db.rollback()
            entry.details, entry.status = {"error": str(e)}, "error"
        entry.finished_at = datetime.now(UTC)
        db.commit()
        if entry.status == "error":
            break
    return logs
