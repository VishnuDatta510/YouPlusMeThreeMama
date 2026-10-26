import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_reviewer
from app.db import get_db
from app.models import QueryVersion, Reviewer
from app.schemas import QueryIn, QueryVersionOut, RunLogOut
from app.services import pipeline, pubmed

router = APIRouter(prefix="/queries", tags=["queries"], dependencies=[Depends(current_reviewer)])


@router.post("/preview", response_model=QueryVersionOut)
def preview(body: QueryIn, db: Session = Depends(get_db), reviewer: Reviewer = Depends(current_reviewer)):
    if body.parent_version_id and db.get(QueryVersion, body.parent_version_id) is None:
        raise HTTPException(404, "Parent version not found")
    try:
        hits = pubmed.count(body.query_string, body.date_from, body.date_to)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"PubMed request failed: {e}")
    parent_id = body.parent_version_id or db.scalar(select(func.max(QueryVersion.id)))
    qv = QueryVersion(
        version_number=(db.scalar(select(func.max(QueryVersion.version_number))) or 0) + 1,
        parent_version_id=parent_id,
        query_string=body.query_string,
        date_from=body.date_from,
        date_to=body.date_to,
        sources=["pubmed"],
        hit_count=hits,
        status="previewed",
        created_by=reviewer.id,
    )
    db.add(qv)
    db.commit()
    return qv


@router.get("", response_model=list[QueryVersionOut])
def list_versions(db: Session = Depends(get_db)):
    return db.scalars(select(QueryVersion).order_by(QueryVersion.version_number.desc())).all()


@router.post("/{version_id}/fetch", response_model=list[RunLogOut])
def fetch(version_id: int, db: Session = Depends(get_db)):
    qv = db.get(QueryVersion, version_id)
    if qv is None:
        raise HTTPException(404, "Query version not found")
    return pipeline.run(db, qv)
