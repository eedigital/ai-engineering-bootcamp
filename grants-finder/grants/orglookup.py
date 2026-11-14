"""Find a nonprofit in IRS records (via ProPublica's free Nonprofit Explorer API)
and turn it into a pre-filled profile, so people pick their name instead of typing.

Data: https://projects.propublica.org/nonprofits/api (no key needed).
"""

from __future__ import annotations

import os
import time

import httpx

BASE = os.getenv("PROPUBLICA_API_BASE", "https://projects.propublica.org/nonprofits/api/v2")

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "GU": "Guam",
    "VI": "U.S. Virgin Islands",
}

# NTEE major groups (first letter of the IRS activity code) -> our topic buttons.
NTEE_TOPICS = {
    "A": ["arts_culture"],
    "B": ["education"],
    "C": ["environment"],
    "D": ["environment"],
    "E": ["health"], "F": ["health"], "G": ["health"], "H": ["health", "science_tech"],
    "I": ["justice_safety"],
    "J": ["jobs_training"],
    "K": ["food_agriculture"],
    "L": ["housing"],
    "M": ["justice_safety"],
    "O": ["youth_families"],
    "P": ["youth_families"],
    "S": ["community"],
    "U": ["science_tech"], "V": ["science_tech"],
    "W": ["community"],
}

NTEE_LABELS = {
    "A": "Arts, culture and humanities", "B": "Education", "C": "Environment", "D": "Animal-related",
    "E": "Health care", "F": "Mental health", "G": "Diseases and medical disciplines", "H": "Medical research",
    "I": "Crime and legal", "J": "Employment", "K": "Food, agriculture and nutrition", "L": "Housing and shelter",
    "M": "Public safety and disaster relief", "N": "Recreation and sports", "O": "Youth development",
    "P": "Human services", "Q": "International affairs", "R": "Civil rights and advocacy",
    "S": "Community improvement", "T": "Philanthropy and grantmaking", "U": "Science and technology",
    "V": "Social science", "W": "Public and societal benefit", "X": "Religion", "Y": "Mutual benefit",
    "Z": "Unknown",
}


class LookupError(Exception):
    pass


_cache: dict[str, tuple[float, list[dict]]] = {}


def to_profile_hint(org: dict) -> dict:
    """One ProPublica organization -> the fields our form can pre-fill."""
    ntee = (org.get("ntee_code") or org.get("raw_ntee_code") or "").strip().upper()
    letter = ntee[:1]
    sub = org.get("subseccd")
    state = (org.get("state") or "").upper()
    return {
        "ein": str(org.get("strein") or org.get("ein") or ""),
        "name": (org.get("name") or "").strip().title() if (org.get("name") or "").isupper() else (org.get("name") or "").strip(),
        "city": (org.get("city") or "").strip().title(),
        "state": STATES.get(state, state or None),
        "org_type": "nonprofit_501c3" if sub == 3 else "nonprofit_other",
        "focus_areas": NTEE_TOPICS.get(letter, [])[:3],
        "category": NTEE_LABELS.get(letter),
        "tax_status": f"501(c)({sub})" if sub else None,
    }


def search(query: str, limit: int = 8) -> list[dict]:
    q = query.strip()
    key = q.lower()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    try:
        r = httpx.get(f"{BASE}/search.json", params={"q": q}, timeout=10,
                      headers={"User-Agent": "grant-finder (github.com/eedigital/ai-engineering-bootcamp)"})
    except httpx.HTTPError as e:
        raise LookupError(f"nonprofit search unreachable: {type(e).__name__}") from e
    if r.status_code == 404:  # ProPublica answers 404 when nothing matches
        results: list[dict] = []
    elif r.status_code != 200:
        raise LookupError(f"nonprofit search returned HTTP {r.status_code}")
    else:
        results = [to_profile_hint(o) for o in (r.json().get("organizations") or [])[:limit]]
    _cache[key] = (time.time(), results)
    return results
