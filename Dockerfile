# ClipForge — ein Container mit Oberfläche (Next.js) und Backend (FastAPI + FFmpeg).
#
# Der Browser spricht nur mit der Oberfläche (Port $PORT, Standard 3000); diese
# reicht /api/* intern an das Backend auf 127.0.0.1:8000 weiter. Alle Daten
# liegen unter /data (als Volume einhängen!).
#
#   docker build -t clipforge .
#   docker run -p 3000:3000 -v clipforge-data:/data -e CLIPFORGE_SECRET_KEY=... clipforge

# ---------- 1) Oberfläche bauen
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY VERSION /VERSION
ENV NEXT_PUBLIC_API_BASE_URL=same-origin NEXT_TELEMETRY_DISABLED=1
RUN npm run build && npm prune --omit=dev

# ---------- 2) Laufzeit
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
COPY --from=web /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY api/requirements.txt api/requirements.txt
RUN pip install -r api/requirements.txt
COPY api/ api/
COPY scripts/ scripts/
COPY feature_flags.json VERSION ./
COPY --from=web /web/.next web/.next
COPY --from=web /web/node_modules web/node_modules
COPY --from=web /web/public web/public
COPY --from=web /web/package.json web/package.json
COPY deploy/entrypoint.sh /app/entrypoint.sh
COPY deploy/backup.sh /app/deploy/backup.sh

RUN useradd --create-home --uid 10001 clipforge \
 && mkdir -p /data && chown -R clipforge:clipforge /data /app/api \
 && chmod +x /app/entrypoint.sh /app/deploy/backup.sh
USER clipforge

# Online-Betrieb: Konten, sichere Cookies, Daten unter /data
ENV CLIPFORGE_AUTH=accounts \
    CLIPFORGE_COOKIE_SECURE=1 \
    CLIPFORGE_TRUST_PROXY=1 \
    CLIPFORGE_PROXY_ANY_HOST=1 \
    CLIPFORGE_DATA_DIR=/data \
    PORT=3000
EXPOSE 3000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','3000'), timeout=4)"
ENTRYPOINT ["/app/entrypoint.sh"]
