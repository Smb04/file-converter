FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY backend/__init__.py /app/backend/__init__.py
COPY backend/shared /app/backend/shared
COPY backend/api /app/backend/api

RUN groupadd -g 1000 appgroup && useradd -u 1000 -g 1000 -M -s /sbin/nologin appuser && \
    mkdir -p /auth-data && chown 1000:1000 /auth-data
USER 1000:1000

EXPOSE 8000
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
