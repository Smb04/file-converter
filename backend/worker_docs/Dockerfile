FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/tmp/lo-home

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-nogui \
    poppler-utils \
    ghostscript \
    qpdf \
    pandoc \
    fonts-dejavu-core \
    fonts-liberation \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/worker_docs/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY backend/__init__.py /app/backend/__init__.py
COPY backend/shared /app/backend/shared
COPY backend/worker_docs /app/backend/worker_docs

RUN groupadd -g 1000 appgroup && useradd -u 1000 -g 1000 -M -s /sbin/nologin appuser
USER 1000:1000

CMD ["python", "-m", "backend.worker_docs.worker"]
