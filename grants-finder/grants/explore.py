"""Explore by cause: no organization needed.

Start from the causes someone cares about and who they are, and show each
grant's own eligibility rules: who may apply, what it requires, and whether it
favors groups like women-owned or rural applicants. Everything here is plain
code except the plain-English summary, which the AI writes and we fact-check.
"""

from __future__ import annotations

import re

from .ai import AIError, DATA_RULE, _norm, ask_json, grant_block
from .schemas import CRITERIA, FOCUS_AREAS, Grant, GrantBrief

# Grants.gov applicant-type descriptions -> short plain labels.
# Order matters: the first matching rule wins.
APPLICANT_LABELS: list[tuple[str, str]] = [
    ("unrestricted", "Anyone"),
    ("other than small businesses", "Larger companies"),
    ("small business", "Small businesses"),
    ("do not have a 501(c)(3)", "Other nonprofits"),
    ("501(c)(3)", "Nonprofits (501(c)(3))"),
    ("individual", "Individuals"),
    ("state government", "State governments"),
    ("county government", "County governments"),
    ("city or township", "City governments"),
    ("special district", "Special districts"),
    ("independent school", "School districts"),
    ("public and state controlled institutions of higher", "Public colleges"),
    ("private institutions of higher", "Private colleges"),
    ("native american tribal governments", "Tribal governments"),
    ("native american tribal organizations", "Tribal organizations"),
    ("public housing", "Public housing authorities"),
    ("others", "Others (see the notice)"),
]


def applicant_labels(types: list[str]) -> list[str]:
    out: list[str] = []
    for t in types:
        low = t.lower()
        label = next((lab for key, lab in APPLICANT_LABELS if key in low), t.strip())
        if label not in out:
            out.append(label)
    return out


def who_can_apply(grant: Grant) -> dict:
    labels = applicant_labels(grant.applicant_types)
    open_to_individuals = any(lab in ("Anyone", "Individuals") for lab in labels)
    return {
        "labels": labels,
        "open_to_individuals": open_to_individuals,
        "needs_organization": bool(labels) and not open_to_individuals,
    }


def queries_for(causes: list[str], criteria: list[str]) -> list[str]:
    """One search per cause, plus cause+criterion searches so targeted grants surface."""
    base = [FOCUS_AREAS[c] for c in causes]
    extra = [f"{CRITERIA[k][1]} {base[0]}" for k in criteria[:2]]
    seen, out = set(), []
    for q in base + extra:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:5]


def criteria_mentions(grant: Grant, criteria: list[str]) -> list[dict]:
    """Which of the user's criteria the grant's own text mentions, with the sentence it's in.
    Plain text search, so the quote is always real."""
    text = " ".join([grant.eligibility_text, grant.description])
    out = []
    for key in criteria:
        label, _, words = CRITERIA[key]
        for w in words:
            m = re.search(re.escape(w), text, re.IGNORECASE)
            if m:
                out.append({"criterion": key, "label": label, "quote": _sentence_around(text, m.start(), m.end())})
                break
    return out


def _sentence_around(text: str, start: int, end: int, limit: int = 220) -> str:
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start))
    right_candidates = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    s = text[left + 1 if left != -1 else 0:right].strip()
    if len(s) > limit:  # keep the match in view
        mid = start - (left + 1 if left != -1 else 0)
        s = ("…" if mid > limit // 2 else "") + s[max(0, mid - limit // 2): max(0, mid - limit // 2) + limit].strip() + "…"
    return s


def amount_note(grant: Grant, amount_needed: int | None) -> str | None:
    if not amount_needed or not grant.award_ceiling:
        return None
    if grant.award_ceiling < amount_needed:
        return f"Awards are at most ${grant.award_ceiling:,}, less than the ${amount_needed:,} you need."
    if grant.award_floor and grant.award_floor > amount_needed:
        return f"The smallest award is ${grant.award_floor:,}, more than you're asking for."
    return None


BRIEF_SYSTEM = f"""You explain a US federal grant to someone deciding whether it suits a cause they care about.
- summary: 1-2 plain sentences on what the grant pays for and who it's meant to help. No jargon.
- requirements: the grant's real eligibility requirements (who may apply, location, matching funds,
  registrations, project type), up to 6, most important first. For each, copy the grant's exact words as
  "evidence". Copy, don't paraphrase. If the grant says nothing, leave evidence empty.
{DATA_RULE}"""


def brief(grant: Grant) -> tuple[GrantBrief, str]:
    b, provider = ask_json(BRIEF_SYSTEM, grant_block(grant), GrantBrief)
    source = _norm(" ".join([grant.title, grant.eligibility_text, grant.description, *grant.applicant_types]))
    for r in b.requirements:
        r.evidence_found = (not r.evidence) or (_norm(r.evidence) in source)
    return b, provider


# Steps every Grants.gov applicant takes, whatever the grant. Fixed text, not AI.
STANDARD_STEPS = [
    {"item": "Register the organization in SAM.gov and get its Unique Entity ID (UEI). Registration can take several weeks, so start early.",
     "link": "https://sam.gov/content/entity-registration"},
    {"item": "Create a Grants.gov account and link it to the organization with the right roles (an E-Business Point of Contact must approve).",
     "link": "https://www.grants.gov/applicants/registration"},
    {"item": "Download the full notice (NOFO) and application package from the grant's Grants.gov page, and read the required sections and page limits.",
     "link": None},
    {"item": "Prepare the standard federal forms in the package, usually the SF-424 family (application, budget and assurances).",
     "link": "https://www.grants.gov/forms"},
    {"item": "Submit before the deadline, allowing a few days for Grants.gov validation emails and fixing any errors.",
     "link": None},
]

CHECKLIST_SYSTEM = f"""You list what an applicant must prepare for one specific US federal grant, based only on its notice text.
- items: up to 8 concrete things this grant asks for beyond the usual registrations: documents, letters of support,
  matching funds, plans, data, eligibility proof, page limits, pre-application steps, deadlines.
- Write each item as a short instruction ("Get a letter of support from your county").
- For each, copy the grant's exact words as "evidence". Copy, don't paraphrase. Skip anything the text doesn't say.
- Don't repeat generic steps (SAM.gov, Grants.gov account, SF-424): those are listed separately.
{DATA_RULE}"""


def checklist(grant: Grant):
    from .schemas import Checklist
    c, _ = ask_json(CHECKLIST_SYSTEM, grant_block(grant), Checklist)
    source = _norm(" ".join([grant.title, grant.eligibility_text, grant.description, *grant.applicant_types]))
    for it in c.items:
        it.evidence_found = (not it.evidence) or (_norm(it.evidence) in source)
    return c  # unverified quotes stay, flagged, so the page can warn instead of silently dropping


__all__ = ["AIError", "who_can_apply", "queries_for", "criteria_mentions", "amount_note", "brief", "applicant_labels"]
