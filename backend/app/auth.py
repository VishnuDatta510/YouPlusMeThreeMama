from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Reviewer

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(reviewer_id: int) -> str:
    exp = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(reviewer_id), "exp": exp}, settings.jwt_secret, algorithm="HS256")


def current_reviewer(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> Reviewer:
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    try:
        reviewer_id = int(jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid token")
    reviewer = db.get(Reviewer, reviewer_id)
    if reviewer is None:
        raise HTTPException(401, "Unknown reviewer")
    return reviewer
