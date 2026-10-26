"""Effective state = latest human decision if any, else latest machine result."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DedupGroup, DedupGroupMember, HumanDecision, MachineResult


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


def screen_status(db: Session, ids: list[int]) -> dict[int, dict]:
    """{record_id: {"label", "reason", "source"}} for records that have any status."""
    out = {i: {**m.output, "source": "machine"} for i, m in latest_machine(db, "screen", ids).items()}
    for i, h in latest_human(db, "screen", ids).items():
        out[i] = {"label": h.value["label"], "reason": h.value.get("reason", ""), "source": "human"}
    return out


def pico_spans(db: Session, ids: list[int]) -> dict[int, list[dict]]:
    out = {i: m.output for i, m in latest_machine(db, "pico", ids).items()}
    out.update({i: h.value["spans"] for i, h in latest_human(db, "pico", ids).items()})
    return out


def duplicate_of(db: Session) -> dict[int, int]:
    """{duplicate_record_id: representative_id} across all records, human overrides applied."""
    out = dict(
        db.execute(
            select(DedupGroupMember.record_id, DedupGroup.representative_record_id).join(
                DedupGroup, DedupGroup.id == DedupGroupMember.group_id
            )
        ).all()
    )
    for record_id, h in latest_human(db, "duplicate").items():
        if h.value.get("duplicate_of"):
            out[record_id] = h.value["duplicate_of"]
        else:
            out.pop(record_id, None)
    return out
