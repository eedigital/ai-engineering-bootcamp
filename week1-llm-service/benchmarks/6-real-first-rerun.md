Run 2026-11-15 09:04 UTC against https://week1-job-extractor.onrender.com, 12 calls over 12 posts (real ads from public Greenhouse job boards, scored against the employer data).

| Metric | Value |
| --- | --- |
| Field accuracy | 93% (28/30 fields) |
| Posts with every field right | 6/8 |
| Success rate | 67% |
| Validation failures (502) | 33% |
| Needed a repair re-prompt | 0% |
| Rate limited (429) | 0 |
| Answered by | groq 8 |
| Median latency | 1,150 ms |
| p90 latency | 1,723 ms |

Accuracy by field:

| Field | Right |
| --- | --- |
| title | 8/8 |
| location | 5/7 |
| salary_min | 5/5 |
| salary_max | 5/5 |
| currency | 5/5 |

What it got wrong:

| Post | Field | Got | Expected |
| --- | --- | --- | --- |
| 5 | location | "San Francisco, California" | ["Remote, US", "Remote"] |
| 11 | location | null | ["In-Office"] |

Failed calls:

- post 8: HTTP 502: model unavailable: groq attempt 1: HTTP 429 (Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m7abpvwke5jty1mnna8s634x` service tier `on_demand` on tokens per day (TPD): Limit 
- post 9: HTTP 502: model unavailable: groq attempt 1: HTTP 429 (Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m7abpvwke5jty1mnna8s634x` service tier `on_demand` on tokens per day (TPD): Limit 
- post 10: HTTP 502: model unavailable: groq attempt 1: HTTP 429 (Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m7abpvwke5jty1mnna8s634x` service tier `on_demand` on tokens per day (TPD): Limit 
- post 12: HTTP 502: model unavailable: groq attempt 1: HTTP 429 (Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m7abpvwke5jty1mnna8s634x` service tier `on_demand` on tokens per day (TPD): Limit 

Ad lengths: median 7,436 characters, 5 of 12 over the 8,000-character limit.

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
