"""Create the demo reviewer if it doesn't exist. Safe to run on every start."""

from sqlalchemy import select

from app.auth import hash_password
from app.config import settings
from app.db import SessionLocal
from app.models import Reviewer


def seed() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Reviewer).where(Reviewer.email == settings.seed_email.lower())):
            return
        db.add(
            Reviewer(
                email=settings.seed_email.lower(),
                password_hash=hash_password(settings.seed_password),
                name="Demo Reviewer",
            )
        )
        db.commit()
        print(f"Seeded reviewer {settings.seed_email}")


if __name__ == "__main__":
    seed()
