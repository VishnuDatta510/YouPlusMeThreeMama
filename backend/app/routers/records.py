from collections import Counter

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_reviewer
from app.db import get_db
from app.models import HumanDecision, MachineResult, QueryVersion, Record, RecordQueryLink, Reviewer
from app.schemas import DecisionIn, RecordRow
from app.services import pico, pipeline, state

router = APIRouter(prefix="/records", tags=["records"], dependencies=[Depends(current_reviewer)])


def representatives(db: Session, query_version_id: int | None = None) -> tuple[list[Record], dict[int, int]]:
    """Working-set records that are not a duplicate of another record, plus the {dup_id: rep_id} map.
    With `query_version_id`, the records that version found instead of the working set."""
    dup = state.duplicate_of(db)
    if query_version_id is None:
        ids = state.working_set(db)
    else:
        ids = db.scalars(
            select(RecordQueryLink.record_id).where(RecordQueryLink.query_version_id == query_version_id)
        ).all()
    q = select(Record).where(Record.id.in_(ids), Record.id.not_in(list(dup))).order_by(Record.id)
    return list(db.scalars(q)), dup


def review_reps(db: Session) -> set[int]:
    """Representatives with a fuzzy (85-95) duplicate that no reviewer has confirmed or rejected yet."""
    decided = state.latest_human(db, "duplicate")
    rows = state.snapshot(db, state.current_run(db))
    return {rep for rec, rep, _, _, needs_review in rows if needs_review and rec not in decided}


@router.get("", response_model=list[RecordRow])
def list_records(
    status: str | None = None,
    query_version_id: int | None = None,
    needs_review: bool = False,
    conflict: bool = False,
    db: Session = Depends(get_db),
):
    # ponytail: filters in Python over the whole set; push status into SQL once projects reach ~50k records
    records, dup = representatives(db, query_version_id)
    ids = [r.id for r in records]
    statuses = state.screen_status(db, ids, dup)
    dup_counts = Counter(dup.values())
    review = review_reps(db)
    conflicts = state.screen_conflicts(db, ids, dup)
    rows = []
    for r in records:
        s = statuses.get(r.id, {"label": "unscreened", "reason": "", "source": ""})
        if (
            (status and s["label"] != status)
            or (needs_review and r.id not in review)
            or (conflict and r.id not in conflicts)
        ):
            continue
        rows.append(
            RecordRow(
                id=r.id,
                pmid=r.pmid,
                doi=r.doi or r.raw.get("doi"),
                title=r.title,
                first_author=r.first_author,
                journal=r.journal,
                year=r.year,
                origin=r.source,
                status=s["label"],
                reason=s["reason"],
                source=s["source"],
                duplicates=dup_counts[r.id],
                needs_review=r.id in review,
                conflict=r.id in conflicts,
            )
        )
    return rows


def _detail(db: Session, r: Record) -> dict:
    dup = state.duplicate_of(db)
    rep = dup.get(r.id, r.id)
    members = state.group_members(dup, [rep])[rep]
    match = next(
        (
            {"match_method": m, "score": s, "needs_review": n}
            for rec, _, m, s, n in state.snapshot(db, state.current_run(db))
            if rec == r.id
        ),
        None,
    )
    names = dict(db.execute(select(Reviewer.id, Reviewer.name)).all())
    votes = state.screen_votes(db, members)
    own = state.screen_status(db, members)
    group = [
        {
            "id": m.id,
            "pmid": m.pmid,
            "title": m.title,
            "year": m.year,
            "journal": m.journal,
            "origin": m.source,
            "status": own.get(m.id),
            "votes": [{"reviewer": names[rv], "label": label} for rec, rv, label in votes if rec == m.id],
        }
        for m in db.scalars(select(Record).where(Record.id.in_(members)).order_by(Record.id))
    ]
    history = db.execute(
        select(HumanDecision, Reviewer.name)
        .join(Reviewer, Reviewer.id == HumanDecision.reviewer_id)
        .where(HumanDecision.target_type == "record", HumanDecision.target_id == r.id)
        .order_by(HumanDecision.id.desc())
    ).all()
    versions = db.execute(
        select(QueryVersion.id, QueryVersion.version_number, QueryVersion.active)
        .join(RecordQueryLink, RecordQueryLink.query_version_id == QueryVersion.id)
        .where(RecordQueryLink.record_id == r.id)
        .order_by(QueryVersion.version_number)
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
        "pages": r.pages,
        "language": r.language,
        "publication_types": r.publication_types,
        "mesh_terms": r.mesh_terms,
        "origin": r.source,
        "source_id": r.source_id,
        "status": state.screen_status(db, [rep], dup).get(rep),
        "conflict": rep in state.screen_conflicts(db, [rep], dup),
        "pico": state.pico_spans(db, [r.id]).get(r.id, []),
        "duplicate_of": dup.get(r.id),
        "match": match,
        "duplicates": [g for g in group if g["id"] != rep],
        "group": group,
        "versions": [v._asdict() for v in versions],
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


def _tag_untagged(db: Session, ids: list[int]) -> None:
    """A record a human includes is PICO-tagged straight away if the machine never tagged it."""
    tagged = set(
        db.scalars(
            select(MachineResult.record_id).where(
                MachineResult.step == "pico",
                MachineResult.method_version == pico.method_version(),
                MachineResult.record_id.in_(ids),
            )
        )
    )
    todo = list(db.scalars(select(Record).where(Record.id.in_(set(ids) - tagged))))
    for r in todo:
        version = db.scalar(
            select(func.max(RecordQueryLink.query_version_id)).where(RecordQueryLink.record_id == r.id)
        )
        if version is not None:
            pipeline.tag_records(db, [r], version)


@router.post("/{record_id}/decisions")
def decide(
    record_id: int,
    body: DecisionIn = Body(),
    db: Session = Depends(get_db),
    reviewer: Reviewer = Depends(current_reviewer),
):
    r = _get(db, record_id)
    value = body.value.model_dump()
    targets = [r.id]
    if body.decision_type == "screen":
        # The decision belongs to the duplicate group: every member gets it, so the group reads the same everywhere.
        dup = state.duplicate_of(db)
        rep = dup.get(r.id, r.id)
        targets = state.group_members(dup, [rep])[rep]
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
    db.add_all(
        HumanDecision(
            target_type="record",
            target_id=t,
            decision_type=body.decision_type,
            value=value,
            note=body.note.strip(),
            reviewer_id=reviewer.id,
        )
        for t in targets
    )
    db.flush()
    if body.decision_type == "screen" and value["label"] in ("include", "maybe"):
        _tag_untagged(db, targets)
    db.commit()
    return _detail(db, r)
