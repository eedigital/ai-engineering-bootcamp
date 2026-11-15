"""A PostHog SQL (HogQL) query that measures the result: conversion rate per variant.

Each user's variant is the first value of the feature flag PostHog recorded for them ($feature_flag_called
events carry $feature_flag and $feature_flag_response). A user converts if they did the conversion event
after first seeing the exposure step. Users who saw more than one variant are excluded, since they'd blur the result.
"""

from __future__ import annotations

import re


def _ident(s: str) -> str:
    """Event names and flag keys go into SQL string literals: keep them to safe characters."""
    return re.sub(r"[^A-Za-z0-9_$\-.:]", "", s)[:80]


def query(flag_key: str, exposure_event: str, conversion_event: str, variants: int = 2) -> str:
    flag, exposure, conversion = _ident(flag_key), _ident(exposure_event), _ident(conversion_event)
    return f"""-- Conversion rate per variant for feature flag '{flag}'
WITH assignment AS (
    SELECT person_id,
           argMin(properties.$feature_flag_response, timestamp) AS variant,
           uniqExact(properties.$feature_flag_response) AS variants_seen
    FROM events
    WHERE event = '$feature_flag_called'
      AND properties.$feature_flag = '{flag}'
      AND timestamp >= now() - INTERVAL 90 DAY
    GROUP BY person_id
),
exposed AS (
    SELECT person_id, min(timestamp) AS first_exposed
    FROM events
    WHERE event = '{exposure}' AND timestamp >= now() - INTERVAL 90 DAY
    GROUP BY person_id
),
converted AS (
    SELECT person_id, min(timestamp) AS first_converted
    FROM events
    WHERE event = '{conversion}' AND timestamp >= now() - INTERVAL 90 DAY
    GROUP BY person_id
)
SELECT a.variant,
       count() AS users,
       countIf(c.first_converted >= e.first_exposed) AS conversions,
       round(conversions / users, 4) AS conversion_rate
FROM assignment a
JOIN exposed e ON e.person_id = a.person_id
LEFT JOIN converted c ON c.person_id = a.person_id
WHERE a.variants_seen = 1
GROUP BY a.variant
ORDER BY a.variant"""
