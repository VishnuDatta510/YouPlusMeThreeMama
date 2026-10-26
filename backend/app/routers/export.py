import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import current_reviewer
from app.db import get_db
from app.routers.records import representatives
from app.services import state

router = APIRouter(prefix="/export", tags=["export"], dependencies=[Depends(current_reviewer)])

PICO_COLUMNS = {"P": "population", "I": "intervention", "C": "comparator", "O": "outcome"}


@router.get("/included.csv")
def included_csv(query_version_id: int | None = None, db: Session = Depends(get_db)):
    records, dup = representatives(db, query_version_id)
    ids = [r.id for r in records]
    statuses = state.screen_status(db, ids, dup)
    spans = state.pico_spans(db, ids)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["pmid", "doi", "title", "authors", "year", "journal", *PICO_COLUMNS.values()])
    for r in records:
        if statuses.get(r.id, {}).get("label") != "include":
            continue
        pico = {k: [s["text"] for s in spans.get(r.id, []) if s["type"] == k] for k in PICO_COLUMNS}
        writer.writerow(
            [r.pmid, r.doi or r.raw.get("doi"), r.title, "; ".join(r.authors), r.year, r.journal]
            + [" | ".join(pico[k]) for k in PICO_COLUMNS]
        )
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="included.csv"'},
    )
