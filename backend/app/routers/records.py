from collections import Counter

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_reviewer
from app.db import get_db
from app.models import DedupGroup, DedupGroupMember, HumanDecision, Record, RecordQueryLink, Reviewer
from app.schemas import DecisionIn, RecordRow
from app.services import state

router = APIRouter(prefix="/records", tags=["records"], dependencies=[Depends(current_reviewer)])


def representatives(db: Session, query_version_id: int | None = None) -> tuple[list[Record], dict[int, int]]:
    """Records that are not a duplicate of another record, plus the {dup_id: rep_id} map."""
    dup = state.duplicate_of(db)
    q = select(Record).where(Record.id.not_in(list(dup))).order_by(Record.id)
    if query_version_id is not None:
        q = q.join(RecordQueryLink, RecordQueryLink.record_id == Record.id).where(
            RecordQueryLink.query_version_id == query_version_id
        )
    return list(db.scalars(q)), dup


def review_reps(db: Session) -> set[int]:
    """Representatives with a fuzzy (85-95) duplicate that no reviewer has confirmed or rejected yet."""
    decided = state.latest_human(db, "duplicate")
    pending = db.execute(
        select(DedupGroupMember.record_id, DedupGroup.representative_record_id)
        .join(DedupGroup, DedupGroup.id == DedupGroupMember.group_id)
        .where(DedupGroupMember.needs_review)
    ).all()
    return {rep for rec, rep in pending if rec not in decided}


@router.get("", response_model=list[RecordRow])
def list_records(
    status: str | None = None,
    query_version_id: int | None = None,
    needs_review: bool = False,
    db: Session = Depends(get_db),
):
    # ponytail: filters in Python over the whole set; push status into SQL once projects reach ~50k records
    records, dup = representatives(db, query_version_id)
    statuses = state.screen_status(db, [r.id for r in records])
    dup_counts = Counter(dup.values())
    review = review_reps(db)
    rows = []
    for r in records:
        s = statuses.get(r.id, {"label": "unscreened", "reason": "", "source": ""})
        if (status and s["label"] != status) or (needs_review and r.id not in review):
            continue
        rows.append(
            RecordRow(
                id=r.id,
                pmid=r.pmid,
                title=r.title,
                year=r.year,
                status=s["label"],
                reason=s["reason"],
                source=s["source"],
                duplicates=dup_counts[r.id],
                needs_review=r.id in review,
            )
        )
    return rows


def _detail(db: Session, r: Record) -> dict:
    dup = state.duplicate_of(db)
    match = db.execute(
        select(DedupGroupMember.match_method, DedupGroupMember.score, DedupGroupMember.needs_review)
        .join(DedupGroup, DedupGroup.id == DedupGroupMember.group_id)
        .where(DedupGroupMember.record_id == r.id)
    ).first()
    dup_ids = sorted(i for i, rep in dup.items() if rep == r.id)
    history = db.execute(
        select(HumanDecision, Reviewer.name)
        .join(Reviewer, Reviewer.id == HumanDecision.reviewer_id)
        .where(HumanDecision.target_type == "record", HumanDecision.target_id == r.id)
        .order_by(HumanDecision.id.desc())
    ).all()
    return {
        "id": r.id,
        "pmid": r.pmid,
        "doi": r.doi or r.raw.get("doi"),
        "title": r.title,
        "abstract": r.abstract,
        "authors": r.authors,
        "year": r.year,
        "journal": r.journal,
        "language": r.language,
        "publication_types": r.publication_types,
        "mesh_terms": r.mesh_terms,
        "status": state.screen_status(db, [r.id]).get(r.id),
        "pico": state.pico_spans(db, [r.id]).get(r.id, []),
        "duplicate_of": dup.get(r.id),
        "match": match._asdict() if match else None,
        "duplicates": [
            {"id": d.id, "pmid": d.pmid, "title": d.title, "year": d.year}
            for d in db.scalars(select(Record).where(Record.id.in_(dup_ids)).order_by(Record.id))
        ],
        "history": [
            {
                "id": h.id,
                "decision_type": h.decision_type,
                "value": h.value,
                "note": h.note,
                "reviewer": name,
                "created_at": h.created_at,
            }
            for h, name in history
        ],
    }


def _get(db: Session, record_id: int) -> Record:
    r = db.get(Record, record_id)
    if r is None:
        raise HTTPException(404, "Record not found")
    return r


@router.get("/{record_id}")
def get_record(record_id: int, db: Session = Depends(get_db)):
    return _detail(db, _get(db, record_id))


@router.post("/{record_id}/decisions")
def decide(
    record_id: int,
    body: DecisionIn = Body(),
    db: Session = Depends(get_db),
    reviewer: Reviewer = Depends(current_reviewer),
):
    r = _get(db, record_id)
    value = body.value.model_dump()
    if body.decision_type == "duplicate" and (target := body.value.duplicate_of) is not None:
        if target == r.id:
            raise HTTPException(422, "A record cannot be a duplicate of itself")
        _get(db, target)
    if body.decision_type == "pico":
        value["spans"].sort(key=lambda s: s["start"])
        last_end = 0
        for s in value["spans"]:
            if s["end"] <= s["start"] or s["end"] > len(r.abstract):
                raise HTTPException(422, f"Span {s['start']}-{s['end']} is outside the abstract")
            if s["start"] < last_end:
                raise HTTPException(422, f"Span {s['start']}-{s['end']} overlaps another span")
            last_end = s["end"]
            s["text"] = r.abstract[s["start"] : s["end"]]  # text is derived, never trusted from the client
    db.add(
        HumanDecision(
            target_type="record",
            target_id=r.id,
            decision_type=body.decision_type,
            value=value,
            note=body.note.strip(),
            reviewer_id=reviewer.id,
        )
    )
    db.commit()
    return _detail(db, r)
