# Build from the REPO ROOT so the shared llm/ package is included:
#   docker build -f prompt-lab/Dockerfile -t promptlab .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv
WORKDIR /srv

COPY prompt-lab/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY llm/ ./llm/
COPY prompt-lab/promptlab/ ./promptlab/

RUN useradd --create-home appuser
USER appuser

CMD ["sh", "-c", "uvicorn promptlab.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
