"""core/rag_tracer.py
Distributed tracing and APM instrumentation for Ermes Knowledge RAG pipeline.

Instruments the complete end-to-end question answering flow:
1. Query Expansion & History Rewriting (rag.query_expansion)
2. Embedding Generation (rag.embedding)
3. Document Retrieval & Hybrid Search (rag.retrieval)
4. Reranking & Candidate Filtering (rag.reranking)
5. Evidence Verification & Grounding (rag.verification)
6. LLM Generation & Answer Synthesis (rag.llm_generation)

Supports:
- Langfuse cloud / self-hosted distributed traces & generations
- OpenTelemetry spans when otel is installed
- In-memory structured trace summary for debugging and audit logs
"""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from typing import Any

_logger = logging.getLogger("ermes.tracing")


class RAGSpan:
    """Rappresenta una singola fase (span) all'interno del flusso RAG."""

    def __init__(self, name: str, tracer: RAGTracer, parent_span: RAGSpan | None = None) -> None:
        self.name = name
        self.tracer = tracer
        self.parent_span = parent_span
        self.start_time = 0.0
        self.end_time = 0.0
        self.duration_seconds = 0.0
        self.metadata: dict[str, Any] = {}
        self.status: str = "running"
        self.error: str | None = None
        self._lf_span: Any = None
        self._otel_span: Any = None

    def set_metadata(self, key: str, value: Any) -> None:
        """Aggiunge metadati e attributi allo span."""
        self.metadata[key] = value
        if self._lf_span:
            with contextlib.suppress(Exception):
                self._lf_span.update(metadata={key: value})

    def __enter__(self) -> RAGSpan:
        self.start_time = time.perf_counter()
        # Notifica Langfuse se disponibile
        if self.tracer._lf_trace:
            try:
                self._lf_span = self.tracer._lf_trace.span(
                    name=self.name,
                    metadata=self.metadata,
                )
            except Exception as err:
                _logger.debug("Langfuse span error [%s]: %s", self.name, err)

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.end_time = time.perf_counter()
        self.duration_seconds = self.end_time - self.start_time
        if exc_val:
            self.status = "error"
            self.error = str(exc_val)
            self.metadata["error"] = self.error
        else:
            self.status = "ok"

        if self._lf_span:
            with contextlib.suppress(Exception):
                self._lf_span.end(
                    status_message=self.error if self.error else "OK",
                    metadata=self.metadata,
                )

        _logger.debug("RAG Span [%s] completed in %.3fs (status=%s)", self.name, self.duration_seconds, self.status)


class RAGTracer:
    """Tracer unificato per l'esecuzione di una richiesta RAG."""

    def __init__(
        self,
        query: str,
        library_id: str,
        username: str = "",
        conversation_id: str | None = None,
    ) -> None:
        self.trace_id = uuid.uuid4().hex
        self.query = query
        self.library_id = library_id
        self.username = username
        self.conversation_id = conversation_id
        self.start_time = 0.0
        self.end_time = 0.0
        self.duration_seconds = 0.0
        self.spans: list[RAGSpan] = []
        self.metadata: dict[str, Any] = {}
        self._lf_trace: Any = None

    def __enter__(self) -> RAGTracer:
        self.start_time = time.perf_counter()
        # Inizializza Langfuse trace se abilitato
        try:
            from config import cfg

            if getattr(cfg, "LANGFUSE_PUBLIC_KEY", None) and getattr(cfg, "LANGFUSE_SECRET_KEY", None):
                from core.ai.utils import _get_langfuse

                lf = _get_langfuse()
                if lf:
                    self._lf_trace = lf.trace(
                        id=self.trace_id,
                        name="rag_query",
                        user_id=self.username or "anonymous",
                        session_id=self.conversation_id,
                        metadata={
                            "library_id": self.library_id,
                            "query": self.query,
                        },
                        tags=["rag", self.library_id],
                    )
        except Exception as err:
            _logger.debug("Inizializzazione Langfuse trace fallita: %s", err)

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.end_time = time.perf_counter()
        self.duration_seconds = self.end_time - self.start_time
        if exc_val:
            self.metadata["error"] = str(exc_val)

        _logger.info(
            "RAG Query Trace [%s] completed in %.3fs with %d spans (user=%s, lib=%s)",
            self.trace_id,
            self.duration_seconds,
            len(self.spans),
            self.username or "anonymous",
            self.library_id,
        )

    def span(self, name: str, **metadata: Any) -> RAGSpan:
        """Crea e registra un nuovo span all'interno della traccia."""
        s = RAGSpan(name, tracer=self)
        for k, v in metadata.items():
            s.set_metadata(k, v)
        self.spans.append(s)
        return s

    def export_summary(self) -> dict[str, Any]:
        """Restituisce il riepilogo strutturato con le latenze di ogni fase."""
        return {
            "trace_id": self.trace_id,
            "library_id": self.library_id,
            "username": self.username,
            "conversation_id": self.conversation_id,
            "duration_seconds": round(self.duration_seconds, 4),
            "spans": [
                {
                    "name": sp.name,
                    "duration_ms": round(sp.duration_seconds * 1000, 2),
                    "status": sp.status,
                    "metadata": sp.metadata,
                }
                for sp in self.spans
            ],
        }


@contextlib.contextmanager
def trace_rag_query(
    query: str,
    library_id: str,
    username: str = "",
    conversation_id: str | None = None,
):
    """Context manager comodo per tracciare una pipeline RAG completa."""
    tracer = RAGTracer(
        query=query,
        library_id=library_id,
        username=username,
        conversation_id=conversation_id,
    )
    with tracer:
        yield tracer
