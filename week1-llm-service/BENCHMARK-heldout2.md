Run 2026-11-15 08:24 UTC against https://week1-job-extractor.onrender.com, 10 calls over 10 posts (held-out: never used to change the code).

| Metric | Value |
| --- | --- |
| Field accuracy | 96% (85/89 fields) |
| Posts with every field right | 8/10 |
| Success rate | 100% |
| Validation failures (502) | 0% |
| Needed a repair re-prompt | 20% |
| Rate limited (429) | 0 |
| Answered by | groq 10 |
| Median latency | 494 ms |
| p90 latency | 905 ms |

Accuracy by field:

| Field | Right |
| --- | --- |
| title | 10/10 |
| company | 10/10 |
| location | 9/9 |
| work_mode | 10/10 |
| seniority | 10/10 |
| salary_min | 8/10 |
| salary_max | 8/10 |
| currency | 10/10 |
| skills | 10/10 |

What it got wrong:

| Post | Field | Got | Expected |
| --- | --- | --- | --- |
| 1 | salary_min | null | 60000000 |
| 1 | salary_max | null | 85000000 |
| 2 | salary_min | null | 240000000 |
| 2 | salary_max | null | 360000000 |
