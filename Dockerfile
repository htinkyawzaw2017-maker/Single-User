# ── Single-User Burmese/English Movie Dubbing Tool ─────────────────────
# Multi-stage: build the React frontend, then bake it into the FastAPI
# backend image. One container serves both the API and the SPA on :8000.

# ---- stage 1: frontend build -------------------------------------------
FROM node:20-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: runtime ----------------------------------------------------
FROM python:3.11-slim AS runtime

# ffmpeg (with libass + freetype for drawtext), fonts for subtitles/watermark
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-noto \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /build/dist /app/frontend-dist

ENV FRONTEND_DIST=/app/frontend-dist \
    DATA_DIR=/app/data \
    FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
