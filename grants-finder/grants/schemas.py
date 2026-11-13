"""Data shapes: the applicant, a grant, and what the AI must return."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class OrgType(str, Enum):
    small_business = "small_business"
    nonprofit_501c3 = "nonprofit_501c3"
    nonprofit_other = "nonprofit_other"
    for_profit = "for_profit"
    individual = "individual"
    tribal = "tribal"
    local_government = "local_government"
    higher_ed = "higher_ed"


ORG_TYPE_LABELS = {
    OrgType.small_business: "Small business",
    OrgType.nonprofit_501c3: "Nonprofit with 501(c)(3) status",
    OrgType.nonprofit_other: "Nonprofit without 501(c)(3) status",
    OrgType.for_profit: "For-profit company (not a small business)",
    OrgType.individual: "Individual",
    OrgType.tribal: "Tribal government or organization",
    OrgType.local_government: "City, county or local government",
    OrgType.higher_ed: "College or university",
}


class Profile(BaseModel):
    """Who is applying. Kept short on purpose: everything here goes into prompts."""

    org_name: str = Field(min_length=1, max_length=120)
    org_type: OrgType
    state: str = Field(min_length=2, max_length=40)
    about: str = Field(min_length=20, max_length=1500, description="What the organization does")
    project: str = Field(min_length=20, max_length=1500, description="What the money would pay for")
    amount_needed: int | None = Field(default=None, ge=0, le=1_000_000_000)
    keywords: str | None = Field(default=None, max_length=200)


class Grant(BaseModel):
    """One Grants.gov opportunity, cleaned up."""

    id: str
    number: str | None = None
    title: str
    agency: str | None = None
    close_date: str | None = None  # ISO yyyy-mm-dd
    award_floor: int | None = None
    award_ceiling: int | None = None
    total_funding: int | None = None
    applicant_types: list[str] = Field(default_factory=list)
    eligibility_text: str = ""
    description: str = ""
    cost_sharing: bool | None = None
    url: str


# --- What the AI returns -----------------------------------------------------


class Requirement(BaseModel):
    requirement: str = Field(max_length=200)
    evidence: str = Field(default="", max_length=400, description="Exact words from the grant")
    status: Literal["met", "not_met", "unknown"]
    why: str = Field(max_length=300)
    evidence_found: bool = True  # set by our own check, not the AI


class Assessment(BaseModel):
    verdict: Literal["strong_match", "possible_match", "not_eligible"]
    fit_score: int = Field(ge=0, le=100)
    summary: str = Field(max_length=500)
    requirements: list[Requirement] = Field(default_factory=list, max_length=8)
    questions: list[str] = Field(default_factory=list, max_length=5)


class SearchQueries(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=3)


class Draft(BaseModel):
    project_title: str = Field(max_length=150)
    summary: str = Field(max_length=1500)
    need: str = Field(max_length=2000)
    fit: str = Field(max_length=2000)
    budget: str = Field(max_length=1200)
    to_verify: list[str] = Field(default_factory=list, max_length=10)


# --- API requests ------------------------------------------------------------


class SearchRequest(BaseModel):
    profile: Profile


class GrantRequest(BaseModel):
    profile: Profile
    grant_id: str = Field(pattern=r"^\d{1,10}$")


class RuleResult(BaseModel):
    status: Literal["eligible", "ineligible", "unclear"]
    reasons: list[str] = Field(default_factory=list)
