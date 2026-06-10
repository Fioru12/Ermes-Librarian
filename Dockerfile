# Dockerfile per Ermes - Enterprise Knowledge Hub
# Build: docker build -t ermes-ai-hub .
# Run: docker compose up

FROM python:3.14-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage finale
FROM python:3.14-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY *.py ./
COPY core/ ./core/
COPY ui/ ./ui/
COPY modules/ ./modules/
COPY evaluation/ ./evaluation/
COPY data/ ./data/
COPY docs/ ./docs/

# Create runtime directories
RUN mkdir -p documenti chroma_db logs security backups data && \
    chmod 755 documenti chroma_db logs security backups data

ENV ERMES_HOST=0.0.0.0
ENV ERMES_PORT=8502
ENV PYTHONUNBUFFERED=1

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port=8502", "--server.address=0.0.0.0", "--server.headless=true"]
