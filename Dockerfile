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
    pip install --no-cache-dir --user -r requirements.txt

# Build frontend
COPY frontend/ ./frontend/
RUN cd frontend && npm ci && npm run build && rm -rf node_modules

# Stage finale
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code.
# Copy config.py explicitly rather than globbing *.py: a glob silently ships
# whatever happens to sit in the repository root into the production image.
# data/ is deliberately NOT copied — it holds the runtime SQLite database,
# is untracked, and is created empty below; copying it broke clean-clone builds.
COPY config.py ./
COPY api/ ./api/
COPY core/ ./core/
COPY evaluation/ ./evaluation/
COPY docs/ ./docs/
COPY --from=builder /app/frontend/dist ./frontend/dist/

# Create runtime directories
RUN mkdir -p documenti chroma_db logs security backups data storage/libraries && \
    chmod 755 documenti chroma_db logs security backups data storage storage/libraries

ENV ERMES_HOST=0.0.0.0
ENV ERMES_PORT=8502
ENV PYTHONUNBUFFERED=1

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8502/health || exit 1

CMD ["sh", "-c", "uvicorn api:app --host ${ERMES_HOST:-0.0.0.0} --port ${ERMES_PORT:-8502}"]
