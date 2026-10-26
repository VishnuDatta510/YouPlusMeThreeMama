from datetime import date, datetime

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
    parent_version_id: int | None = None

    @model_validator(mode="after")
    def check_dates(self):
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
    status: str
    created_at: datetime


class RunLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    step: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    details: dict
