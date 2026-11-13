"""Plain-code eligibility checks. These run before the AI and win over it.

Hard facts (who may apply, the deadline) are checked with code, because
code can't hallucinate. The AI only judges the fuzzy parts.
"""

from __future__ import annotations

from datetime import date

from .schemas import Grant, OrgType, Profile, RuleResult

# Words in Grants.gov's applicant-type descriptions that admit each org type.
MATCH_WORDS: dict[OrgType, list[str]] = {
    OrgType.small_business: ["small business"],
    OrgType.nonprofit_501c3: ["having a 501(c)(3)", "nonprofits having"],
    OrgType.nonprofit_other: ["do not have a 501(c)(3)", "without 501(c)(3)"],
    OrgType.for_profit: ["for profit organizations other than small"],
    OrgType.individual: ["individual"],
    OrgType.tribal: ["tribal", "native american"],
    OrgType.local_government: ["county government", "city or township", "special district"],
    OrgType.higher_ed: ["institutions of higher education"],
}
# Descriptions that contain a match word but mean the opposite.
EXCLUDE_WORDS: dict[OrgType, list[str]] = {
    OrgType.small_business: ["other than small"],
}
OPEN_WORDS = ["unrestricted"]
SEE_TEXT_WORDS = ["others", "see text", "additional information"]


def admits(applicant_type: str, org_type: OrgType) -> bool:
    t = applicant_type.lower()
    if any(x in t for x in EXCLUDE_WORDS.get(org_type, [])):
        return False
    return any(w in t for w in MATCH_WORDS[org_type])


def check(profile: Profile, grant: Grant, today: date | None = None) -> RuleResult:
    today = today or date.today()
    reasons: list[str] = []
    status = "eligible"

    if grant.close_date and date.fromisoformat(grant.close_date) < today:
        return RuleResult(status="ineligible", reasons=[f"The deadline ({grant.close_date}) has passed."])

    types = [t.lower() for t in grant.applicant_types]
    if not types:
        status = "unclear"
        reasons.append("The grant doesn't list applicant types, so eligibility depends on its text.")
    elif any(admits(t, profile.org_type) for t in types):
        reasons.append("Your organization type is on the grant's list of eligible applicants.")
    elif any(w in t for t in types for w in OPEN_WORDS):
        reasons.append("The grant is open to any applicant type.")
    elif any(w in t for t in types for w in SEE_TEXT_WORDS):
        status = "unclear"
        reasons.append("Your type isn't listed by name; the grant's eligibility text decides.")
    else:
        return RuleResult(
            status="ineligible",
            reasons=["Your organization type isn't on the grant's list of eligible applicants."],
        )

    if profile.amount_needed and grant.award_ceiling and profile.amount_needed > grant.award_ceiling:
        reasons.append(
            f"You need ${profile.amount_needed:,}, but the largest award is ${grant.award_ceiling:,}."
        )
        if status == "eligible":
            status = "unclear"
    if grant.cost_sharing:
        reasons.append("The grant requires cost sharing: you'd fund part of the project yourself.")
    return RuleResult(status=status, reasons=reasons)
