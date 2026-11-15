Run 2026-11-15 08:49 UTC against https://week1-job-extractor.onrender.com, 12 calls over 12 posts (real ads from public Greenhouse job boards, scored against the employer data).

| Metric | Value |
| --- | --- |
| Field accuracy | 75% (18/24 fields) |
| Posts with every field right | 1/6 |
| Success rate | 50% |
| Validation failures (502) | 8% |
| Needed a repair re-prompt | 17% |
| Rate limited (429) | 0 |
| Answered by | groq 6 |
| Median latency | 1,220 ms |
| p90 latency | 1,451 ms |

Accuracy by field:

| Field | Right |
| --- | --- |
| title | 5/6 |
| location | 1/6 |
| salary_min | 4/4 |
| salary_max | 4/4 |
| currency | 4/4 |

What it got wrong:

| Post | Field | Got | Expected |
| --- | --- | --- | --- |
| 1 | location | "US - Remote Eligible" | ["United States"] |
| 3 | location | null | ["Canada"] |
| 4 | location | null | ["N", "A"] |
| 8 | title | "Machine Learning / AI Engineer" | ["Software Engineer - Machine Learning", "Software Engineer"] |
| 8 | location | "United States (remote or US hubs)" | ["San Francisco, CA • New York, NY • United States", "San Francisco"] |
| 9 | location | null | ["San Francisco Bay Area", "Los Angeles Area"] |

Failed calls:

- post 2: HTTP 422: input too long (max 8000 characters)
- post 5: HTTP 422: input too long (max 8000 characters)
- post 6: HTTP 422: input too long (max 8000 characters)
- post 10: HTTP 502: model output failed validation
- post 11: HTTP 422: input too long (max 8000 characters)
- post 12: HTTP 422: input too long (max 8000 characters)

Ad lengths: median 7,348 characters, 5 of 12 over the 8,000-character limit.

The ads (fetched fresh each run, not stored here):

1. https://careers.airbnb.com/positions/6757302?gh_jid=6757302
2. https://careers.airbnb.com/positions/6852954?gh_jid=6852954
3. https://stripe.com/jobs/search?gh_jid=5416444
4. https://stripe.com/jobs/search?gh_jid=5601879
5. https://job-boards.greenhouse.io/gitlab/jobs/8396674002
6. https://job-boards.greenhouse.io/gitlab/jobs/8490477002
7. https://boards.greenhouse.io/figma/jobs/5426468004?gh_jid=5426468004
8. https://boards.greenhouse.io/figma/jobs/5551532004?gh_jid=5551532004
9. https://job-boards.greenhouse.io/discord/jobs/8214127002
10. https://job-boards.greenhouse.io/discord/jobs/8299493002
11. https://boards.greenhouse.io/cloudflare/jobs/5390243?gh_jid=5390243
12. https://boards.greenhouse.io/cloudflare/jobs/6528593?gh_jid=6528593
