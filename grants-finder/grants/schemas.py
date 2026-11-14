"""Data shapes: the applicant, a grant, and what the AI must return."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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


# Topics a user can tap instead of typing. Each maps to the Grants.gov search it runs.
FOCUS_AREAS: dict[str, str] = {
    "education": "education",
    "health": "health",
    "food_agriculture": "agriculture",
    "arts_culture": "arts",
    "environment": "environment",
    "energy": "energy",
    "housing": "housing",
    "jobs_training": "workforce training",
    "small_business": "small business",
    "community": "community development",
    "science_tech": "research",
    "youth_families": "youth",
    "justice_safety": "justice",
    "veterans": "veterans",
    # causes added for explore mode
    "conservation": "conservation",
    "social_development": "social services",
    "animal_welfare": "wildlife",
    "mental_health": "mental health",
    "disaster_relief": "disaster",
    "seniors": "aging",
    "disability": "disability",
    "civil_rights": "civil rights",
    "water": "water",
    "international": "international development",
}

ORG_SIZES = {
    "solo": "Just one person",
    "2_10": "2 to 10 people",
    "11_50": "11 to 50 people",
    "51_500": "51 to 500 people",
    "500_plus": "More than 500 people",
}


class Profile(BaseModel):
    """Who is applying. Only type and state are required; the rest sharpens matches and drafts."""

    org_type: OrgType
    state: str = Field(min_length=2, max_length=40)
    focus_areas: list[str] = Field(default_factory=list, max_length=3)
    amount_needed: int | None = Field(default=None, ge=0, le=1_000_000_000)
    org_size: str | None = None
    # Optional details
    org_name: str | None = Field(default=None, max_length=120)
    about: str | None = Field(default=None, max_length=1500, description="What the organization does")
    project: str | None = Field(default=None, max_length=1500, description="What the money would pay for")
    keywords: str | None = Field(default=None, max_length=200)

    @field_validator("focus_areas")
    @classmethod
    def known_areas(cls, v: list[str]) -> list[str]:
        unknown = [a for a in v if a not in FOCUS_AREAS]
        if unknown:
            raise ValueError(f"unknown focus areas: {unknown}")
        return v

    @field_validator("org_size")
    @classmethod
    def known_size(cls, v: str | None) -> str | None:
        if v is not None and v not in ORG_SIZES:
            raise ValueError("unknown organization size")
        return v

    @field_validator("org_name", "about", "project", "keywords", mode="before")
    @classmethod
    def blank_is_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v

    @model_validator(mode="after")
    def something_to_search(self) -> "Profile":
        if not (self.focus_areas or self.project or self.about or self.keywords):
            raise ValueError("pick at least one topic, or describe your project")
        return self


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


# Who the applicant is, for grants that favor certain groups.
# key -> (label, search word, words that signal it in a grant's text)
CRITERIA: dict[str, tuple[str, str, list[str]]] = {
    "women": ("Woman or women-owned", "women", ["women-owned", "women owned", "woman-owned", "women"]),
    "minority": ("Minority or minority-owned", "minority", ["minority", "socially and economically disadvantaged", "underrepresented", "historically underserved"]),
    "veteran": ("Veteran", "veteran", ["veteran"]),
    "rural": ("Rural", "rural", ["rural"]),
    "tribal": ("Native American or tribal", "tribal", ["tribal", "native american", "alaska native", "native hawaiian", "indian tribe"]),
    "low_income": ("Low-income community", "low-income", ["low-income", "low income", "underserved", "economically distressed", "poverty"]),
    "disability": ("Person with a disability", "disability", ["disabilit", "disabled"]),
    "youth": ("Under 25", "youth", ["youth", "young adult", "students"]),
}


class ExploreRequest(BaseModel):
    causes: list[str] = Field(min_length=1, max_length=3)
    criteria: list[str] = Field(default_factory=list, max_length=4)
    amount_needed: int | None = Field(default=None, ge=0, le=1_000_000_000)

    @field_validator("causes")
    @classmethod
    def known_causes(cls, v):
        if bad := [c for c in v if c not in FOCUS_AREAS]:
            raise ValueError(f"unknown causes: {bad}")
        return v

    @field_validator("criteria")
    @classmethod
    def known_criteria(cls, v):
        if bad := [c for c in v if c not in CRITERIA]:
            raise ValueError(f"unknown criteria: {bad}")
        return v


class ExploreGrantRequest(BaseModel):
    grant_id: str = Field(pattern=r"^\d{1,10}$")
    criteria: list[str] = Field(default_factory=list, max_length=4)
    amount_needed: int | None = Field(default=None, ge=0, le=1_000_000_000)


class EligibilityPoint(BaseModel):
    requirement: str = Field(max_length=200)
    evidence: str = Field(default="", max_length=400, description="Exact words from the grant")
    evidence_found: bool = True  # set by our own check, not the AI


class GrantBrief(BaseModel):
    summary: str = Field(max_length=500, description="What the grant pays for, in plain words")
    requirements: list[EligibilityPoint] = Field(default_factory=list, max_length=6)


class SearchRequest(BaseModel):
    profile: Profile


class GrantRequest(BaseModel):
    profile: Profile
    grant_id: str = Field(pattern=r"^\d{1,10}$")


class RuleResult(BaseModel):
    status: Literal["eligible", "ineligible", "unclear"]
    reasons: list[str] = Field(default_factory=list)
