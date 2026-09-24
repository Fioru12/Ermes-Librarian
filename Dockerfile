# syntax=docker/dockerfile:1.7
# Dockerfile per Ermes - Enterprise Knowledge Hub
# Build: docker build -t ermes-ai-hub .
# Run: docker compose up

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# In una rete aziendale il certificato della CA interna puo essere passato senza
# inserirlo nell'immagine: docker build --secret id=corporate_ca,src=company-ca.crt .
RUN --mount=type=secret,id=corporate_ca,target=/run/secrets/corporate_ca,required=false \
    if [ -s /run/secrets/corporate_ca ]; then \
        cp /run/secrets/corporate_ca /usr/local/share/ca-certificates/corporate-ca.crt && update-ca-certificates; \
    fi && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Build frontend
COPY frontend/ ./frontend/
RUN cd frontend && npm ci && npm run build && rm -rf node_modules

# Stage finale
FROM python:3.11-slim

WORKDIR /app

# tesseract-ocr: OCR delle pagine PDF scansionate (core/ocr.py), con i dati
# per italiano e inglese. Circa 30 MB: e' la differenza tra indicizzare o
# perdere meta' dei documenti di un archivio aziendale reale.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python dependencies to system location so any non-root user can access them
COPY --from=builder /install /usr/local

# Copy application code, scripts, examples and frontend dist
COPY config/ ./config/
COPY api/ ./api/
COPY core/ ./core/
COPY evaluation/ ./evaluation/
COPY docs/ ./docs/
COPY scripts/ ./scripts/
COPY examples/ ./examples/
COPY --from=builder /app/frontend/dist ./frontend/dist/

# Creazione directory applicative necessarie per i volumi
RUN mkdir -p documenti chroma_db logs security backups data storage/libraries

# Creazione utente non-root conforme alle best practice di security enterprise
# (UID 10001 corrisponde esattamente al podSecurityContext definito nei manifesti Helm)
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g 10001 -m -s /bin/sh -d /app appuser && \
    chown -R appuser:appuser /app && \
    chmod 755 documenti chroma_db logs security backups data storage storage/libraries

USER 10001

ENV ERMES_HOST=0.0.0.0
ENV ERMES_PORT=8502
ENV PYTHONUNBUFFERED=1

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f "http://localhost:${ERMES_PORT:-8502}/health" || exit 1

CMD ["sh", "-c", "uvicorn api:app --host ${ERMES_HOST:-0.0.0.0} --port ${ERMES_PORT:-8502}"]
