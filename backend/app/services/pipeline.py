"""Runs fetch → dedupe → screen → pico for a query version, writing one run_log row per step."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import QueryVersion, Record, RecordQueryLink, RunLog
from app.services import pubmed

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


STEPS = [("fetch", fetch)]


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
