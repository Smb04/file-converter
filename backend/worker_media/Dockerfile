FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libvips42 \
    imagemagick \
    libheif1 \
    libraw-bin \
    librsvg2-bin \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/worker_media/policy.xml /tmp/policy.xml
RUN if [ -d /etc/ImageMagick-6 ]; then cp /tmp/policy.xml /etc/ImageMagick-6/policy.xml; fi && \
    if [ -d /etc/ImageMagick-7 ]; then cp /tmp/policy.xml /etc/ImageMagick-7/policy.xml; fi && \
    rm -f /tmp/policy.xml

WORKDIR /app

COPY backend/worker_media/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY backend/__init__.py /app/backend/__init__.py
COPY backend/shared /app/backend/shared
COPY backend/worker_media /app/backend/worker_media

RUN groupadd -g 1000 appgroup && useradd -u 1000 -g 1000 -M -s /sbin/nologin appuser
USER 1000:1000

CMD ["python", "-m", "backend.worker_media.worker"]
