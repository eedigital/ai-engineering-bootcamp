Run 2026-11-15 08:56 UTC against https://week1-job-extractor.onrender.com, 12 calls over 12 posts (a fresh set of real ads, never used to change the code, scored against the employer data).

| Metric | Value |
| --- | --- |
| Field accuracy | 100% (45/45 fields) |
| Posts with every field right | 12/12 |
| Success rate | 100% |
| Validation failures (502) | 0% |
| Needed a repair re-prompt | 0% |
| Rate limited (429) | 0 |
| Answered by | groq 12 |
| Median latency | 835 ms |
| p90 latency | 938 ms |

Accuracy by field:

| Field | Right |
| --- | --- |
| title | 12/12 |
| location | 9/9 |
| salary_min | 8/8 |
| salary_max | 8/8 |
| currency | 8/8 |

Ad lengths: median 7,440 characters, 4 of 12 over the 8,000-character limit.

The ads (fetched fresh each run, not stored here):

1. https://careers.airbnb.com/positions/7107054?gh_jid=7107054
2. https://careers.airbnb.com/positions/7230257?gh_jid=7230257
3. https://stripe.com/jobs/search?gh_jid=5601881
4. https://stripe.com/jobs/search?gh_jid=5895430
5. https://job-boards.greenhouse.io/gitlab/jobs/8530337002
6. https://job-boards.greenhouse.io/gitlab/jobs/8532272002
7. https://boards.greenhouse.io/figma/jobs/5551686004?gh_jid=5551686004
8. https://boards.greenhouse.io/figma/jobs/5551730004?gh_jid=5551730004
9. https://job-boards.greenhouse.io/discord/jobs/8649856002
10. https://job-boards.greenhouse.io/discord/jobs/8652853002
11. https://boards.greenhouse.io/cloudflare/jobs/6557318?gh_jid=6557318
12. https://boards.greenhouse.io/cloudflare/jobs/6578726?gh_jid=6578726
