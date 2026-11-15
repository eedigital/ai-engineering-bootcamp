Run 2026-11-15 08:14 UTC against https://week1-job-extractor.onrender.com, 15 calls over 15 posts (held-out: never used to change the code).

| Metric | Value |
| --- | --- |
| Field accuracy | 99% (121/122 fields) |
| Posts with every field right | 14/15 |
| Success rate | 100% |
| Validation failures (502) | 0% |
| Needed a repair re-prompt | 7% |
| Rate limited (429) | 0 |
| Answered by | groq 15 |
| Median latency | 522 ms |
| p90 latency | 783 ms |

Accuracy by field:

| Field | Right |
| --- | --- |
| title | 15/15 |
| company | 12/12 |
| location | 11/11 |
| work_mode | 15/15 |
| seniority | 15/15 |
| salary_min | 12/12 |
| salary_max | 11/12 |
| currency | 15/15 |
| skills | 15/15 |

What it got wrong:

| Post | Field | Got | Expected |
| --- | --- | --- | --- |
| 11 | salary_max | 10000000 | 11000000 |
