# syntax=docker/dockerfile:1

FROM node:24-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.14-slim AS runtime

WORKDIR /app

# pdftotext is the preferred PDF text reader and Tesseract is the local scan reader.
RUN apt-get update \
    && apt-get install --no-install-recommends -y poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY backend/ ./backend/
COPY data/ ./data/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

# Build the offline demo state from the tracked inbox, then warm PDF page-image
# caches. This keeps Render's first request from having to run the pipeline or
# render document pages.
RUN GEMINI_ENABLED=false python -m backend.app.precompute_demo

# Demo mode restores its read-only JSON snapshot into this ephemeral directory at startup.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p backend/derived/cache backend/derived/logs backend/derived/meta backend/derived/pages backend/derived/text \
    && chown -R appuser:appuser /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEMO_MODE=1 \
    GEMINI_ENABLED=false \
    RESULTS_SNAPSHOT=results_snapshot.json

USER appuser

CMD ["sh", "-c", "exec gunicorn --bind \"0.0.0.0:${PORT:-10000}\" --workers 1 --threads 4 --timeout 120 --graceful-timeout 30 app:app"]
