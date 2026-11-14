# Build from the REPO ROOT so the shared llm/ package is included:
#   docker build -f deal-desk/Dockerfile -t dealdesk .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv
WORKDIR /srv

COPY deal-desk/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY llm/ ./llm/
COPY deal-desk/dealdesk/ ./dealdesk/

RUN useradd --create-home appuser
USER appuser

CMD ["sh", "-c", "uvicorn dealdesk.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
