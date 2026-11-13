"""The contract: what /extract promises to return, enforced by Pydantic."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class WorkMode(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"


class Seniority(str, Enum):
    intern = "intern"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"
    unknown = "unknown"


class JobPosting(BaseModel):
    """Structured fields pulled from a free-text job post."""

    title: str = Field(min_length=1, max_length=120)
    company: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    work_mode: WorkMode = WorkMode.unknown
    seniority: Seniority = Seniority.unknown
    salary_min: int | None = Field(default=None, ge=0, le=10_000_000)
    salary_max: int | None = Field(default=None, ge=0, le=10_000_000)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    skills: list[str] = Field(default_factory=list, max_length=25)

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, v: list[str]) -> list[str]:
        seen, out = set(), []
        for s in (x.strip() for x in v):
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s[:50])
        return out

    @model_validator(mode="after")
    def salary_order(self) -> "JobPosting":
        if self.salary_min and self.salary_max and self.salary_min > self.salary_max:
            raise ValueError("salary_min is greater than salary_max")
        return self


class ExtractRequest(BaseModel):
    text: str = Field(description="The raw job post")


class ExtractResponse(BaseModel):
    ok: bool
    data: JobPosting | None = None
    error: str | None = None
    # What happened on the way, for debugging and for your README numbers.
    provider: str | None = None
    latency_ms: float | None = None
    attempts: int = 0
    redactions: int = 0
