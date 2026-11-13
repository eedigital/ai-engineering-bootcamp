# AI Engineering Bootcamp: the free build

Four deployable AI projects in four weeks, using only free tools.

| Week | Project | Status |
| --- | --- | --- |
| 1 | [LLM service with structured outputs and guardrails](week1-llm-service/) | Live: [try it](https://week1-job-extractor.onrender.com/docs) |
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
