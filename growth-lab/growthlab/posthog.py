"""PostHog: the KPI queries (HogQL, for PostHog's SQL editor) and the browser snippet for the prospect-facing page.

The event names match launch.EVENTS. Payment is tracked server-side ('member_paid'), so ad blockers can't hide revenue.
"""

from __future__ import annotations

import json
import os

KPI_QUERIES = {
    "CVR, direct and rep-assisted, by week": """SELECT toStartOfWeek(timestamp) AS week,
       uniqIf(person_id, event = 'pricing_viewed') AS saw_pricing,
       uniqIf(person_id, event = 'member_paid' AND properties.path = 'direct') AS paid_direct,
       uniqIf(person_id, event = 'member_paid' AND properties.path = 'rep') AS paid_rep,
       round((paid_direct + paid_rep) / nullIf(uniqIf(person_id, event = '$pageview'), 0), 4) AS cvr_per_visitor
FROM events
WHERE timestamp >= now() - INTERVAL 12 WEEK
GROUP BY week ORDER BY week""",
    "Revenue by product line": """SELECT properties.product_line AS product_line,
       count() AS new_members,
       sum(toFloat(properties.value)) AS first_year_value
FROM events
WHERE event = 'member_paid' AND timestamp >= now() - INTERVAL 12 WEEK
GROUP BY product_line ORDER BY first_year_value DESC""",
    "Know your cost: pricing → checkout by variant": """SELECT properties.`$feature/know-your-cost` AS variant,
       uniqIf(person_id, event = 'pricing_viewed') AS saw_pricing,
       uniqIf(person_id, event = 'checkout_started') AS started_checkout,
       round(started_checkout / saw_pricing, 4) AS rate
FROM events
WHERE event IN ('pricing_viewed', 'checkout_started') AND timestamp >= now() - INTERVAL 6 WEEK
GROUP BY variant""",
}


PROXY_PATH = "/ingest"


def ingest_host() -> str:
    return os.getenv("POSTHOG_HOST", "https://us.i.posthog.com").rstrip("/")


def assets_host() -> str:
    return ingest_host().replace(".i.posthog.com", "-assets.i.posthog.com")


def ui_host() -> str:
    return "https://eu.posthog.com" if ingest_host().startswith("https://eu.") else "https://us.posthog.com"


def upstream(path: str) -> str:
    """Where /ingest/<path> goes: the SDK and its config come from the assets host, events from the ingest host."""
    path = path.lstrip("/")
    base = assets_host() if path.startswith(("static/", "array/")) else ingest_host()
    return f"{base}/{path}"


def snippet() -> str:
    """posthog-js for the prospect page, only when a project key is configured. Autocapture off: only the planned events."""
    key = os.getenv("POSTHOG_KEY", "")
    if not key:
        return ""
    # Events go to this app's own /ingest path, which forwards them to PostHog, so ad blockers can't drop them.
    cfg = {"api_host": PROXY_PATH, "ui_host": ui_host(), "autocapture": False, "capture_pageview": True,
           "person_profiles": "identified_only"}
    return ("<script>!function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split('.');"
            "2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}"
            "(p=t.createElement('script')).type='text/javascript',p.crossOrigin='anonymous',p.async=!0,p.src=s.api_host.replace('.i.posthog.com','-assets.i.posthog.com')+'/static/array.js',"
            "(r=t.getElementsByTagName('script')[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a='posthog',u.people=u.people||[],"
            "u.toString=function(t){var e='posthog';return'posthog'!==a&&(e+='.'+a),t||(e+=' (stub)'),e},u.people.toString=function(){return u.toString(1)+'.people (stub)'},"
            "o='capture identify alias people.set people.set_once set_config register register_once unregister opt_out_capturing has_opted_out_capturing opt_in_capturing reset isFeatureEnabled onFeatureFlags getFeatureFlag getFeatureFlagPayload reloadFeatureFlags group'.split(' '),"
            "n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);"
            f"posthog.init({json.dumps(key)},{json.dumps(cfg)});</script>")
