from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def created_at_col():
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Reviewer(Base):
    __tablename__ = "reviewers"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_col()


class QueryVersion(Base):
    __tablename__ = "query_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_number: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("query_versions.id"))
    query_string: Mapped[str] = mapped_column(Text)
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    sources: Mapped[list] = mapped_column(JSONB, default=lambda: ["pubmed"])
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="previewed")  # previewed / fetched
    created_by: Mapped[int | None] = mapped_column(ForeignKey("reviewers.id"))
    created_at: Mapped[datetime] = created_at_col()


class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(primary_key=True)
    pmid: Mapped[str | None] = mapped_column(String(20), unique=True)
    doi: Mapped[str | None] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(Text, default="")
    abstract: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[list] = mapped_column(JSONB, default=list)
    first_author: Mapped[str] = mapped_column(String(255), default="")
    year: Mapped[int | None] = mapped_column(Integer)
    journal: Mapped[str] = mapped_column(Text, default="")
    pages: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(20), default="")
    publication_types: Mapped[list] = mapped_column(JSONB, default=list)
    mesh_terms: Mapped[list] = mapped_column(JSONB, default=list)
    source: Mapped[str] = mapped_column(String(30), default="pubmed")
    raw: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at_col()


class RecordQueryLink(Base):
    __tablename__ = "record_query_links"
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), primary_key=True)
    query_version_id: Mapped[int] = mapped_column(ForeignKey("query_versions.id"), primary_key=True)


class DedupGroup(Base):
    __tablename__ = "dedup_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    representative_record_id: Mapped[int] = mapped_column(ForeignKey("records.id"))
    created_at: Mapped[datetime] = created_at_col()


class DedupGroupMember(Base):
    """Non-representative members only: a record listed here is a duplicate of its group's representative."""

    __tablename__ = "dedup_group_members"
    group_id: Mapped[int] = mapped_column(ForeignKey("dedup_groups.id"), primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), primary_key=True)
    match_method: Mapped[str] = mapped_column(String(10))  # doi / pmid / fuzzy
    score: Mapped[float] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)


class MachineResult(Base):
    __tablename__ = "machine_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), index=True)
    query_version_id: Mapped[int] = mapped_column(ForeignKey("query_versions.id"))
    step: Mapped[str] = mapped_column(String(10))  # screen / pico
    method_version: Mapped[str] = mapped_column(String(255))
    output: Mapped[dict | list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()


class HumanDecision(Base):
    """Append-only: the latest row per (target, decision_type) wins, so the table is also the audit log."""

    __tablename__ = "human_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20))  # record / group / pico_span
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    decision_type: Mapped[str] = mapped_column(String(20))  # screen / duplicate / pico
    value: Mapped[dict] = mapped_column(JSONB)
    note: Mapped[str] = mapped_column(Text, default="")
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("reviewers.id"))
    created_at: Mapped[datetime] = created_at_col()


class RunLog(Base):
    __tablename__ = "run_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    query_version_id: Mapped[int] = mapped_column(ForeignKey("query_versions.id"))
    step: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # running / ok / error
    started_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
