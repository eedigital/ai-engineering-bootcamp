# AI Engineering Bootcamp: the free build

Deployable AI projects built with free tools: a four-week bootcamp, plus product prototypes built on the same stack. Every project below is live.

| Week | Project | Status |
| --- | --- | --- |
| 1 | [LLM service with structured outputs and guardrails](week1-llm-service/) | Live: [try it](https://week1-job-extractor.onrender.com/docs) |
| + | [Grant Finder: eligible US federal grants, with reasons and a first draft](grants-finder/) | Live: [try it](https://grant-finder-fhuv.onrender.com) |
| + | [Pitch Perfect: pitch deck review, numbers check and investor practice](pitch-perfect/) | Live: [try it](https://pitch-perfect-j6rj.onrender.com) |
| + | [Deal Desk: get one export deal right (concept for ICC One Click)](deal-desk/) | Live: [try it](https://deal-desk-gzud.onrender.com) |
| + | [Experiment Designer: a Linear agent that plans A/B tests](experiment-agent/) | Live: [home and setup](https://experiment-agent.onrender.com) |
| + | [Growth Lab: a growth PM's first 90 days, on invented data](growth-lab/) | Live: [try it](https://growth-lab.onrender.com) |
| + | [Prompt Lab: test prompt versions on real cases, then ship the best on quality, cost and speed](prompt-lab/) | Live: [try it](https://prompt-lab.onrender.com) |
| 2 | [RAG pipeline: measured, broken, fixed](week2-rag/) | Not started |
| 3 | [Agent from the raw loop up, then ADK or LangGraph with MCP](week3-agent/) | Not started |
| 4 | [TRACE evals and an agent with memory](week4-evals-memory/) | Not started |

## Free stack

- **Models:** Gemini API free tier, then Groq free tier, then a local model through Ollama. `llm/` tries them in order, so a rate limit on one doesn't stop you.
- **Hosting:** Render free web service (`render.yaml`).
- **CI:** GitHub Actions. Tests use a fake model, so CI needs no keys.

## Layout

```
llm/                 shared client used by every week
week1-llm-service/   FastAPI service, guardrails, tests, Dockerfile
grants-finder/       grant search, eligibility checks, application drafts
pitch-perfect/       pitch deck review, numbers check, investor practice
deal-desk/           export deal planner, built to plug into ICC One Click
experiment-agent/    Linear agent: assign it an issue, get an A/B test plan back
growth-lab/          a growth PM's first 90 days: funnel, sized roadmap, readouts, launch
prompt-lab/          prompt versions run on test cases: code-checked scores, held-out cases, cost per call
week2-rag/ ...       one folder per week
render.yaml          Render deploy config
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r week1-llm-service/requirements.txt pytest
cp .env.example .env    # add a free Gemini or Groq key
pytest -q
```
