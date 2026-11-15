Run 2026-11-15 07:53 UTC against https://week1-job-extractor.onrender.com, 16 calls over 8 sample posts.

| Metric | Value |
| --- | --- |
| Field accuracy | 90% (121/134 fields) |
| Posts with every field right | 10/16 |
| Success rate | 100% |
| Validation failures (502) | 0% |
| Needed a repair re-prompt | 0% |
| Rate limited (429) | 0 |
| Answered by | groq 16 |
| Median latency | 625 ms |
| p90 latency | 693 ms |

Accuracy by field:

| Field | Right |
| --- | --- |
| title | 14/14 |
| company | 12/12 |
| location | 12/12 |
| work_mode | 16/16 |
| seniority | 14/16 |
| salary_min | 14/16 |
| salary_max | 14/16 |
| currency | 15/16 |
| skills | 10/16 |

What it got wrong:

| Post | Field | Got | Expected |
| --- | --- | --- | --- |
| 4 | seniority | "unknown" | ["senior", "lead"] |
| 4 | skills | [] | ["Kubernetes", "Terraform"] |
| 5 | skills | [] | ["Java", "C#"] |
| 7 | salary_min | null | 95000 |
| 7 | salary_max | null | 120000 |
| 7 | skills | [] | ["RAG", "LangGraph"] |
| 7 | currency | null | "EUR" |
