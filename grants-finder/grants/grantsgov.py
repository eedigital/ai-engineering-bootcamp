"""Grants.gov's public API: search2 and fetchOpportunity. No key needed.

The API's field names aren't fully documented, so `normalize` reads
defensively and tests pin the shapes we've seen. If Grants.gov changes a
field, fix it here and in tests/fixtures.
"""

from __future__ import annotations

import html
import os
import re
import time
from datetime import datetime

import httpx

from .schemas import Grant, OrgType

BASE = os.getenv("GRANTS_API_BASE", "https://api.grants.gov/v1/api")
TIMEOUT = 20.0

# Grants.gov applicant-type codes used to narrow a search. The rule check
# matches on the published descriptions instead, so a wrong code here only
# makes a search broader or narrower, never a wrong eligibility verdict.
SEARCH_CODES: dict[OrgType, list[str]] = {
    OrgType.small_business: ["23"],
    OrgType.nonprofit_501c3: ["12"],
    OrgType.nonprofit_other: ["13"],
    OrgType.for_profit: ["22"],
    OrgType.individual: ["21"],
    OrgType.tribal: ["07", "11"],
    OrgType.local_government: ["01", "02", "04"],
    OrgType.higher_ed: ["06", "20"],
}
OPEN_CODES = ["25", "99"]  # "Others" and "Unrestricted"


class GrantsGovError(Exception):
    pass


def _post(path: str, body: dict) -> dict:
    try:
        r = httpx.post(f"{BASE}/{path}", json=body, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise GrantsGovError(f"Grants.gov unreachable: {type(e).__name__}") from e
    if r.status_code != 200:
        raise GrantsGovError(f"Grants.gov returned HTTP {r.status_code}")
    data = r.json()
    if data.get("errorcode") not in (0, None):
        raise GrantsGovError(f"Grants.gov error: {data.get('msg')}")
    return data


def search(keyword: str, org_type: OrgType | None = None, rows: int = 15) -> list[dict]:
    """Open opportunities matching a keyword. Returns raw hits (id, title, agency...)."""
    body: dict = {"keyword": keyword, "oppStatuses": "posted", "rows": rows}
    if org_type is not None:
        body["eligibilities"] = "|".join(SEARCH_CODES[org_type] + OPEN_CODES)
    hits = (_post("search2", body).get("data") or {}).get("oppHits") or []
    if not hits and org_type is not None:
        return search(keyword, None, rows)  # filter too narrow: search without it
    return hits


# --- details ---------------------------------------------------------------

_cache: dict[str, tuple[float, Grant]] = {}
CACHE_SECONDS = 6 * 3600


def fetch(grant_id: str) -> Grant:
    hit = _cache.get(grant_id)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    raw = _post("fetchOpportunity", {"opportunityId": int(grant_id)})
    grant = normalize(raw)
    _cache[grant_id] = (time.time(), grant)
    return grant


_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"[ \t\r\f\v]+")


def clean_text(s: str | None, limit: int | None = None) -> str:
    if not s:
        return ""
    s = _TAG.sub(" ", s.replace("<br>", "\n").replace("<br/>", "\n").replace("</p>", "\n"))
    s = html.unescape(s)
    s = "\n".join(_SPACE.sub(" ", line).strip() for line in s.splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s[:limit] if limit else s


def parse_money(v) -> int | None:
    """Grants.gov sends numbers, "$1,000", "none" or "" for money."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if v > 0 else None
    digits = re.sub(r"[^\d.]", "", str(v))
    try:
        n = int(float(digits)) if digits else None
    except ValueError:
        return None
    return n if n and n > 0 else None


def parse_date(v) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    for pattern, fmt in (
        (r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y"),          # 12/15/2026
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),          # 2026-12-15
        (r"[A-Z][a-z]{2} \d{1,2}, \d{4}", "%b %d, %Y"),  # Dec 15, 2026 12:00:00 AM EST
    ):
        m = re.search(pattern, s)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], "none", "None"):
            return v
    return None


def normalize(raw: dict) -> Grant:
    d = raw.get("data", raw) or {}
    syn = d.get("synopsis") or d.get("forecast") or {}
    both = {**d, **syn}

    types = _first(syn, "applicantTypes") or []
    applicant_types = [
        (t.get("description") or t.get("label") or "").strip() if isinstance(t, dict) else str(t)
        for t in types
    ]
    gid = str(_first(d, "id", "opportunityId") or "")
    return Grant(
        id=gid,
        number=_first(d, "opportunityNumber", "number"),
        title=clean_text(_first(d, "opportunityTitle", "title") or "Untitled opportunity", 300),
        agency=_first(syn, "agencyName") or _first(d, "agencyName", "owningAgencyCode", "agencyCode"),
        close_date=parse_date(_first(syn, "responseDate", "responseDateStr", "estApplicationResponseDate")),
        award_floor=parse_money(_first(both, "awardFloor", "awardFloorFormatted")),
        award_ceiling=parse_money(_first(both, "awardCeiling", "awardCeilingFormatted")),
        total_funding=parse_money(_first(both, "estimatedFunding", "estimatedFundingFormatted")),
        applicant_types=[t for t in applicant_types if t],
        eligibility_text=clean_text(_first(syn, "applicantEligibilityDesc"), 2500),
        description=clean_text(_first(syn, "synopsisDesc", "forecastDesc"), 4000),
        cost_sharing=syn.get("costSharing") if isinstance(syn.get("costSharing"), bool) else None,
        url=f"https://www.grants.gov/search-results-detail/{gid}",
    )


def from_hit(hit: dict) -> dict:
    """The few fields a search hit carries, for showing results before details load."""
    return {
        "id": str(hit.get("id")),
        "number": hit.get("number"),
        "title": clean_text(hit.get("title"), 300),
        "agency": hit.get("agencyName") or hit.get("agencyCode"),
        "close_date": parse_date(hit.get("closeDate")),
        "url": f"https://www.grants.gov/search-results-detail/{hit.get('id')}",
    }
