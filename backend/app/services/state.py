"""Effective state = latest human decision if any, else latest machine result.

Screening decisions belong to the duplicate group, not the record: a group's status is the newest human decision on
any of its members, and a group whose members were judged differently is flagged as a conflict.
"""

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DedupGroup,
    DedupGroupMember,
    HumanDecision,
    MachineResult,
    QueryVersion,
    RecordQueryLink,
    RunLog,
)


def latest_machine(db: Session, step: str, ids: list[int]) -> dict[int, MachineResult]:
    rows = db.scalars(
        select(MachineResult)
        .where(MachineResult.step == step, MachineResult.record_id.in_(ids))
        .order_by(MachineResult.record_id, MachineResult.id.desc())
        .distinct(MachineResult.record_id)
    )
    return {r.record_id: r for r in rows}


def latest_human(db: Session, decision_type: str, ids: list[int] | None = None) -> dict[int, HumanDecision]:
    q = select(HumanDecision).where(
        HumanDecision.target_type == "record", HumanDecision.decision_type == decision_type
    )
    if ids is not None:
        q = q.where(HumanDecision.target_id.in_(ids))
    rows = db.scalars(
        q.order_by(HumanDecision.target_id, HumanDecision.id.desc()).distinct(HumanDecision.target_id)
    )
    return {r.target_id: r for r in rows}


def working_set(db: Session) -> list[int]:
    """Record ids found by any active query version: the set that is deduplicated, listed and exported."""
    active = select(QueryVersion.id).where(QueryVersion.active)
    return sorted(
        set(db.scalars(select(RecordQueryLink.record_id).where(RecordQueryLink.query_version_id.in_(active))))
    )


def current_run(db: Session) -> int | None:
    """The dedupe run whose group snapshot is in effect: the newest one that finished ok."""
    return db.scalar(select(func.max(RunLog.id)).where(RunLog.step == "dedupe", RunLog.status == "ok"))


def snapshot(db: Session, run_id: int | None) -> list[tuple[int, int, str, float, bool]]:
    """(record_id, representative_id, match_method, score, needs_review) rows of one dedupe run."""
    if run_id is None:
        return []
    return db.execute(
        select(
            DedupGroupMember.record_id,
            DedupGroup.representative_record_id,
            DedupGroupMember.match_method,
            DedupGroupMember.score,
            DedupGroupMember.needs_review,
        )
        .join(DedupGroup, DedupGroup.id == DedupGroupMember.group_id)
        .where(DedupGroup.run_id == run_id)
    ).all()


def groups_of(db: Session, run_id: int | None) -> list[frozenset[int]]:
    """A run's machine groups as sets of record ids (representative included)."""
    members: dict[int, set[int]] = defaultdict(set)
    for rec, rep, *_ in snapshot(db, run_id):
        members[rep] |= {rep, rec}
    return sorted((frozenset(m) for m in members.values()), key=min)


def duplicate_of(db: Session) -> dict[int, int]:
    """{duplicate_record_id: representative_id} for the current snapshot, human overrides applied."""
    out = {rec: rep for rec, rep, *_ in snapshot(db, current_run(db))}
    for record_id, h in latest_human(db, "duplicate").items():
        if h.value.get("duplicate_of"):
            out[record_id] = h.value["duplicate_of"]
        else:
            out.pop(record_id, None)
    # A human may point at a record that is itself a duplicate: follow the chain to the record that is shown.
    resolved = {}
    for rec in out:
        seen, rep = {rec}, out[rec]
        while rep in out and rep not in seen:
            seen.add(rep)
            rep = out[rep]
        if rep != rec:
            resolved[rec] = rep
    return resolved


def group_members(dup: dict[int, int], reps: list[int]) -> dict[int, list[int]]:
    members = {r: [r] for r in reps}
    for rec, rep in sorted(dup.items()):
        if rep in members:
            members[rep].append(rec)
    return members


def screen_status(db: Session, ids: list[int], dup: dict[int, int] | None = None) -> dict[int, dict]:
    """{record_id: {"label", "reason", "source"}}. With `dup`, each id is a representative and its whole group counts."""
    members = group_members(dup, ids) if dup is not None else {i: [i] for i in ids}
    every = [m for ms in members.values() for m in ms]
    machine = latest_machine(db, "screen", every)
    human = latest_human(db, "screen", every)
    out = {}
    for rep, ms in members.items():
        decided = [human[m] for m in ms if m in human]
        if decided:
            h = max(decided, key=lambda d: d.id)
            out[rep] = {"label": h.value["label"], "reason": h.value.get("reason", ""), "source": "human"}
        elif found := next((machine[m] for m in ms if m in machine), None):
            out[rep] = {**found.output, "source": "machine"}
    return out


def pico_spans(db: Session, ids: list[int]) -> dict[int, list[dict]]:
    out = {i: m.output for i, m in latest_machine(db, "pico", ids).items()}
    out.update({i: h.value["spans"] for i, h in latest_human(db, "pico", ids).items()})
    return out


def screen_votes(db: Session, ids: list[int]) -> list[tuple[int, int, str]]:
    """(record_id, reviewer_id, label): each reviewer's latest screening label on each record."""
    return db.execute(
        select(HumanDecision.target_id, HumanDecision.reviewer_id, HumanDecision.value["label"].astext)
        .where(
            HumanDecision.target_type == "record",
            HumanDecision.decision_type == "screen",
            HumanDecision.target_id.in_(ids),
        )
        .distinct(HumanDecision.target_id, HumanDecision.reviewer_id)
        .order_by(HumanDecision.target_id, HumanDecision.reviewer_id, HumanDecision.id.desc())
    ).all()


def screen_conflicts(db: Session, reps: list[int], dup: dict[int, int]) -> set[int]:
    """Groups whose latest labels disagree: two reviewers on one record, or records judged differently that turned
    out to be duplicates. The newest decision still applies until someone resolves it."""
    members = group_members(dup, reps)
    rep_of = {m: rep for rep, ms in members.items() for m in ms}
    labels: dict[int, set[str]] = defaultdict(set)
    for record_id, _, label in screen_votes(db, list(rep_of)):
        labels[rep_of[record_id]].add(label)
    return {rep for rep, ls in labels.items() if len(ls) > 1}
