from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_reviewer
from app.db import get_db
from app.models import HumanDecision, QueryVersion, Reviewer
from app.schemas import CriteriaIn, RunLogOut
from app.services import pipeline, screening

router = APIRouter(prefix="/screening", tags=["screening"], dependencies=[Depends(current_reviewer)])


@router.get("/criteria")
def get_criteria(db: Session = Depends(get_db)):
    active = screening.active_criteria(db)
    return [
        {"key": k, "label": c.label, "why": c.why, "basis": c.basis, "active": k in active}
        for k, c in screening.CRITERIA.items()
    ]


@router.put("/criteria", response_model=list[RunLogOut])
def set_criteria(
    body: CriteriaIn, db: Session = Depends(get_db), reviewer: Reviewer = Depends(current_reviewer)
):
    """Saves the reviewer's choice (append-only, so it is audited) and re-screens the working set with it."""
    if unknown := set(body.active) - screening.CRITERIA.keys():
        raise HTTPException(422, f"Unknown criteria: {sorted(unknown)}")
    db.add(
        HumanDecision(
            target_type="project",
            target_id=0,
            decision_type="criteria",
            value={"active": [k for k in screening.CRITERIA if k in body.active]},
            note=body.note.strip(),
            reviewer_id=reviewer.id,
        )
    )
    db.commit()
    logs = []
    for qv in db.scalars(select(QueryVersion).where(QueryVersion.active).order_by(QueryVersion.id)):
        logs += pipeline.run(db, qv, pipeline.RESCREEN[1:])
    return logs
