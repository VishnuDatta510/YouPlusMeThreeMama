"""Runs fetch → dedupe → screen → pico for a query version, writing one run_log row per step."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, update
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
from app.services import europepmc, pico, pubmed, screening, state

log = logging.getLogger(__name__)
EFETCH_BATCH = 100
SOURCES = ("pubmed", "europepmc")


def store(db: Session, parsed: list[dict], source: str) -> tuple[list[int], int]:
    """Insert the records not stored yet (matched on PMID, else source id). Returns all their ids and the new count."""
    pmids = [p["pmid"] for p in parsed if p.get("pmid")]
    sids = [p["source_id"] for p in parsed if p.get("source_id")]
    by_pmid = dict(db.execute(select(Record.pmid, Record.id).where(Record.pmid.in_(pmids))).all())
    by_sid = dict(db.execute(select(Record.source_id, Record.id).where(Record.source_id.in_(sids))).all())
    taken = set(
        db.scalars(select(Record.doi).where(Record.doi.in_({p["doi"] for p in parsed if p.get("doi")})))
    )
    ids, new = [], 0
    for p in parsed:
        known, key = (by_pmid, p["pmid"]) if p.get("pmid") else (by_sid, p.get("source_id"))
        if key in known:
            ids.append(known[key])
            continue
        doi = p.get("doi")
        if doi in taken:
            doi = None  # DOI column is unique; the copy stays in raw so dedupe still matches it
        elif doi:
            taken.add(doi)
        rec = Record(**{**p, "doi": doi}, source=source, raw=p)
        db.add(rec)
        db.flush()
        known[key] = rec.id
        ids.append(rec.id)
        new += 1
    return ids, new


def link(db: Session, qv: QueryVersion, ids: list[int]) -> None:
    if ids:
        rows = [{"record_id": i, "query_version_id": qv.id} for i in dict.fromkeys(ids)]
        db.execute(insert(RecordQueryLink).values(rows).on_conflict_do_nothing())


def activate(db: Session, qv: QueryVersion) -> None:
    """A fetched version joins the working set. An edited query replaces the version it was edited from."""
    qv.status, qv.active = "fetched", True
    if qv.parent_version_id:
        db.execute(update(QueryVersion).where(QueryVersion.id == qv.parent_version_id).values(active=False))


def fetch(db: Session, qv: QueryVersion, entry: RunLog) -> dict:
    """Incremental: records already stored are linked to this version but not stored again (PubMed skips EFetch)."""
    ids, new, by_source = [], 0, {}
    for source in qv.sources:
        if source == "pubmed":
            pmids = pubmed.search_ids(qv.query_string, qv.date_from, qv.date_to, settings.max_fetch)
            stored = set(db.scalars(select(Record.pmid).where(Record.pmid.in_(pmids))))
            todo = [i for i in pmids if i not in stored]
            parsed = []
            for start in range(0, len(todo), EFETCH_BATCH):
                parsed += pubmed.parse_efetch(pubmed.efetch(todo[start : start + EFETCH_BATCH]))
            _, n = store(db, parsed, "pubmed")
            found = list(db.scalars(select(Record.id).where(Record.pmid.in_(pmids))))
        elif source == "europepmc":
            # ponytail: Europe PMC has no cheap id-only + fetch-by-id split, so known records are downloaded again
            # (and only linked); fine at MAX_FETCH sizes.
            parsed = europepmc.search(qv.query_string, qv.date_from, qv.date_to, settings.max_fetch)
            found, n = store(db, parsed, "europepmc")
        else:
            raise ValueError(f"Unknown source {source!r}")
        ids += found
        new += n
        by_source[source] = len(found)
    link(db, qv, ids)
    activate(db, qv)
    db.commit()
    total = len(set(ids))
    return {"found": total, "new": new, "already_known": total - new, "by_source": by_source}


def dedupe(db: Session, qv: QueryVersion, entry: RunLog) -> dict:
    """Rebuilt over the working set each run as a new snapshot (tagged with this run); old snapshots are kept."""
    ids = state.working_set(db)
    rows = db.execute(
        select(
            Record.id,
            Record.pmid,
            Record.doi,
            Record.raw["doi"].astext,
            Record.title,
            Record.year,
            Record.first_author,
            Record.journal,
            Record.pages,
        ).where(Record.id.in_(ids))
    ).all()
    candidates = [
        dedupe_service.Candidate(
            id=r[0],
            pmid=r[1],
            doi=r[2] or r[3],
            title=r[4],
            year=r[5],
            first_author=r[6],
            journal=r[7],
            pages=r[8],
        )
        for r in rows
    ]
    matches = dedupe_service.find_duplicates(candidates)
    groups: dict[int, DedupGroup] = {}
    for m in matches:
        if m.representative_id not in groups:
            groups[m.representative_id] = DedupGroup(
                representative_record_id=m.representative_id, run_id=entry.id
            )
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


def screen(db: Session, qv: QueryVersion, entry: RunLog) -> dict:
    criteria = screening.active_criteria(db)
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


def tag_records(db: Session, records: list[Record], query_version_id: int) -> int:
    """PICO-tag the records that are included or maybe and have an abstract. The caller commits."""
    method = pico.method_version()
    status = state.screen_status(db, [r.id for r in records])
    tagged = 0
    for r in records:
        if r.abstract and status.get(r.id, {}).get("label") in ("include", "maybe"):
            db.add(
                MachineResult(
                    record_id=r.id,
                    query_version_id=query_version_id,
                    step="pico",
                    method_version=method,
                    output=pico.extract_pico(r.abstract),
                )
            )
            tagged += 1
    return tagged


def tag_pico(db: Session, qv: QueryVersion, entry: RunLog) -> dict:
    method = pico.method_version()
    tagged = tag_records(db, list(_records_without_result(db, qv, "pico", method)), qv.id)
    db.commit()
    return {"method_version": method, "tagged": tagged}


Step = Callable[[Session, QueryVersion, RunLog], dict]
STEPS: list[tuple[str, Step]] = [("fetch", fetch), ("dedupe", dedupe), ("screen", screen), ("pico", tag_pico)]
RESCREEN = STEPS[1:]  # the working set changed or criteria changed; nothing new to fetch


def run(db: Session, qv: QueryVersion, steps: list[tuple[str, Step]] = STEPS) -> list[RunLog]:
    logs = []
    for name, fn in steps:
        entry = RunLog(query_version_id=qv.id, step=name, status="running", details={})
        db.add(entry)
        db.commit()
        logs.append(entry)
        try:
            entry.details, entry.status = fn(db, qv, entry), "ok"
        except Exception as e:
            log.exception("pipeline step %s failed for query version %s", name, qv.id)
            db.rollback()
            entry.details, entry.status = {"error": str(e)}, "error"
        entry.finished_at = datetime.now(UTC)
        db.commit()
        if entry.status == "error":
            break
    return logs
