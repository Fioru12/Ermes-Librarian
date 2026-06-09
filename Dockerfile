# Dockerfile per Ermes - Enterprise Knowledge Hub
# Build: docker build -t ermes-ai-hub .
# Run: docker run -p 8502:8502 -v $(pwd)/documenti:/app/documenti -v $(pwd)/chroma_db:/app/chroma_db -v $(pwd)/logs:/app/logs ermes-ai-hub

FROM python:3.11-slim as builder

# Imposta working directory
WORKDIR /app

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage finale
FROM python:3.11-slim

WORKDIR /app

# Copia dipendenze dal builder
COPY --from=builder /root/.local /root/.local

# Assicura che gli script siano nel PATH
ENV PATH=/root/.local/bin:$PATH

# Copia codice applicazione
COPY *.py ./
COPY modules/ ./modules/
COPY docs/ ./docs/

# Crea directory necessarie con permessi corretti
RUN mkdir -p documenti chroma_db logs security backups && \
    chmod 755 documenti chroma_db logs security backups

# Imposta variabili ambiente default
ENV ERMES_HOST=0.0.0.0
ENV ERMES_PORT=8502
ENV PYTHONUNBUFFERED=1

# Espone porta
EXPOSE 8502

# Health check per verificare che l'applicazione sia in esecuzione
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

# Comando di avvio (Streamlit)
CMD ["streamlit", "run", "app.py", "--server.port=8502", "--server.address=0.0.0.0", "--server.headless=true"]
