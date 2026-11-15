# Experiment Designer: a Linear agent for A/B tests

Assign it a Linear issue (or @mention it) like **"Test shorter checkout"** and it replies in the issue with:

- a **hypothesis** and the primary metric
- the **sample size and how long the test needs to run**, rounded up to full weeks
- **guardrail metrics** to watch
- a **PostHog SQL query** that measures conversion per variant

Reply in the thread with your own numbers ("baseline 2.4%, detect a 15% lift, 5,000 visitors a day") and it recalculates.

There's also a try-it box on the home page that needs no Linear.

## How it works

| Part | How |
| --- | --- |
| Sample size and duration | Plain maths, no AI (`expagent/stats.py`): a two-sided test of two proportions. 10% → 12% needs 3,841 users per variant; 5% → 5.5% needs 31,234. |
| Numbers from the issue | Plain code reads the baseline, the lift (relative or in percentage points), traffic per day/week/month, traffic share, variants, power and significance. Anything missing gets a stated default the team can correct. |
| Hypothesis, metrics, guardrails, event names | AI (Claude, then Groq, then Gemini), as structured JSON with one repair attempt. It may only quote sample sizes and run times from the calculated table, and reuses the issue's event names. If the AI is busy, a template still gives a complete plan and says so. |
| PostHog query | Built in code (`expagent/posthog.py`): each user's variant from `$feature_flag_called`, conversions after first exposure, users who saw two variants excluded. Names are sanitised before they go into SQL. |
| Linear | An agent installed with `actor=app` and the `app:mentionable` and `app:assignable` scopes, so it appears in the assignee and @-mention menus. Its own app tokens request the same five scopes; asking for fewer narrows the app's permissions in the workspace. It answers `AgentSessionEvent` webhooks with Agent Activities: a thought within 10 seconds, actions while it works, then the plan as a response. |
| Security | Every webhook is checked: HMAC-SHA256 of the raw body against `Linear-Signature`, and `webhookTimestamp` within 60 seconds. Duplicate deliveries are answered once. The install link's state is signed. |
| Tokens | After the one-time install, the server mints app-actor tokens with the client-credentials grant (valid 30 days), so nothing needs storing on Render's free plan. |

## Set up

1. In Linear: **Settings → API → New application**. Name it *Experiment Designer*.
2. Callback URL: `https://experiment-agent.onrender.com/oauth/callback`
3. Webhooks on, URL `https://experiment-agent.onrender.com/webhooks/linear`, tick **Agent session events**.
4. Turn on **Client credentials**. Save, then put the client ID, client secret and webhook signing secret into Render as `LINEAR_CLIENT_ID`, `LINEAR_CLIENT_SECRET` and `LINEAR_WEBHOOK_SECRET`.
5. As a workspace admin, open the service's home page and click **Install in Linear**.

The home page shows the exact URLs to paste and whether each secret is set.

## Tests

`pytest -q experiment-agent` (34 tests): the maths against known values, reading numbers from issue text, the plan with and without the AI, the PostHog query's safety, and the full Linear flow with Linear's API faked: signed webhooks, a thought before anything else, the plan as a response, recalculating on a reply, after a restart, the stop signal, duplicates, errors, and the install link's scopes.
