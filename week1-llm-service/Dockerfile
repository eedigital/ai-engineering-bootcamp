# Build from the REPO ROOT so the shared llm/ package is included:
#   docker build -f week1-llm-service/Dockerfile -t week1 .
#   docker run -p 8000:8000 --env-file .env week1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv
WORKDIR /srv

COPY week1-llm-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY llm/ ./llm/
COPY week1-llm-service/app/ ./app/

RUN useradd --create-home appuser
USER appuser

# Render sets $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
