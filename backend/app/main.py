import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import auth, export, queries, records

# Render sets RENDER=true; a deployed API must never sign tokens with the public default secret.
if os.environ.get("RENDER") and settings.jwt_secret == "dev-secret-change-me":
    raise RuntimeError("Set JWT_SECRET to a long random value before deploying")

app = FastAPI(title="Mini-Rayyan API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(queries.router)
app.include_router(records.router)
app.include_router(export.router)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("select 1"))
    return {"status": "ok"}
