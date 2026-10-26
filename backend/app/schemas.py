from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ReviewerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str


class QueryIn(BaseModel):
    query_string: str = Field(min_length=1, max_length=4000)
    date_from: date | None = None
    date_to: date | None = None
    parent_version_id: int | None = None  # set when the query was edited from an earlier version
    sources: list[Literal["pubmed", "europepmc"]] = Field(default=["pubmed"], min_length=1)

    @model_validator(mode="after")
    def check_dates(self):
        self.sources = list(dict.fromkeys(self.sources))
        self.query_string = self.query_string.strip()
        if not self.query_string:
            raise ValueError("query_string is empty")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before date_to")
        return self


class QueryVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version_number: int
    parent_version_id: int | None
    query_string: str
    date_from: date | None
    date_to: date | None
    sources: list
    hit_count: int
    source_hits: dict
    status: str
    active: bool
    created_at: datetime


class ActiveIn(BaseModel):
    active: bool


class ImportIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=50_000_000)


class CriteriaIn(BaseModel):
    active: list[str]
    note: str = Field("", max_length=2000)


class RunLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    query_version_id: int
    step: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    details: dict


class RecordRow(BaseModel):
    id: int
    pmid: str | None
    doi: str | None
    title: str
    first_author: str
    journal: str
    year: int | None
    origin: str  # pubmed / europepmc / import: where the record came from
    status: str  # include / exclude / maybe / unscreened
    reason: str
    source: str  # machine / human / ""
    duplicates: int
    needs_review: bool  # has a fuzzy duplicate awaiting a reviewer's decision
    conflict: bool  # reviewers' latest screening labels disagree


class ScreenValue(BaseModel):
    label: Literal["include", "exclude", "maybe"]
    reason: str = Field("", max_length=1000)

    @model_validator(mode="after")
    def exclude_needs_reason(self):
        self.reason = self.reason.strip()
        if self.label == "exclude" and not self.reason:
            raise ValueError("A reason is required to exclude a record")
        return self


class DuplicateValue(BaseModel):
    duplicate_of: int | None  # None = not a duplicate (overrides the machine grouping)


class PicoSpanIn(BaseModel):
    type: Literal["P", "I", "C", "O"]
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class PicoValue(BaseModel):
    spans: list[PicoSpanIn] = Field(max_length=200)


class ScreenDecision(BaseModel):
    decision_type: Literal["screen"]
    value: ScreenValue
    note: str = Field("", max_length=2000)


class DuplicateDecision(BaseModel):
    decision_type: Literal["duplicate"]
    value: DuplicateValue
    note: str = Field("", max_length=2000)


class PicoDecision(BaseModel):
    decision_type: Literal["pico"]
    value: PicoValue
    note: str = Field("", max_length=2000)


DecisionIn = Annotated[
    ScreenDecision | DuplicateDecision | PicoDecision, Field(discriminator="decision_type")
]
