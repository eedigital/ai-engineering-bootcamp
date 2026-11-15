# Build from the REPO ROOT so the shared llm/ package is included:
#   docker build -f growth-lab/Dockerfile -t growthlab .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv
WORKDIR /srv

COPY growth-lab/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY llm/ ./llm/
COPY growth-lab/growthlab/ ./growthlab/

RUN useradd --create-home appuser
USER appuser

CMD ["sh", "-c", "uvicorn growthlab.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
