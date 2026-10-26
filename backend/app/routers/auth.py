from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_token, current_reviewer, verify_password
from app.db import get_db
from app.models import Reviewer
from app.schemas import LoginIn, ReviewerOut, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    reviewer = db.scalar(select(Reviewer).where(Reviewer.email == body.email.strip().lower()))
    if reviewer is None or not verify_password(body.password, reviewer.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return TokenOut(access_token=create_token(reviewer.id))


@router.get("/me", response_model=ReviewerOut)
def me(reviewer: Reviewer = Depends(current_reviewer)):
    return reviewer
