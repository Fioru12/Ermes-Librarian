"""tests/test_rag_tracing.py
Unit tests for distributed RAG tracing and APM spans (core/rag_tracer.py).
"""

from unittest.mock import MagicMock
from core.rag_tracer import RAGTracer, trace_rag_query


def test_rag_tracer_lifecycle_and_spans():
    tracer = RAGTracer(
        query="Come funziona il RAG in Ermes?",
        library_id="lib_123",
        username="mario",
        conversation_id="conv_456",
    )

    with tracer:
        with tracer.span("query_expansion", strategy="history_rewrite") as s1:
            s1.set_metadata("rewritten_to", "Come funziona il RAG?")

        with tracer.span("retrieval", limit=5) as s2:
            s2.set_metadata("chunks_found", 3)

        with tracer.span("llm_generation", model="llama3.2") as s3:
            s3.set_metadata("output_tokens", 42)

    summary = tracer.export_summary()

    assert summary["trace_id"] == tracer.trace_id
    assert summary["library_id"] == "lib_123"
    assert summary["username"] == "mario"
    assert summary["duration_seconds"] >= 0.0
    assert len(summary["spans"]) == 3

    span_names = [s["name"] for s in summary["spans"]]
    assert span_names == ["query_expansion", "retrieval", "llm_generation"]

    assert summary["spans"][0]["metadata"]["rewritten_to"] == "Come funziona il RAG?"
    assert summary["spans"][1]["metadata"]["chunks_found"] == 3
    assert summary["spans"][2]["metadata"]["output_tokens"] == 42
    for sp in summary["spans"]:
        assert sp["status"] == "ok"
        assert sp["duration_ms"] >= 0.0


def test_rag_tracer_span_error_recording():
    tracer = RAGTracer(query="error test", library_id="lib_err")

    with tracer:
        try:
            with tracer.span("failing_span"):
                raise ValueError("Simulated network timeout")
        except ValueError:
            pass

    summary = tracer.export_summary()
    assert len(summary["spans"]) == 1
    assert summary["spans"][0]["status"] == "error"
    assert "Simulated network timeout" in summary["spans"][0]["metadata"]["error"]


def test_rag_tracer_langfuse_integration(monkeypatch):
    mock_lf = MagicMock()
    mock_trace = MagicMock()
    mock_span = MagicMock()
    mock_lf.trace.return_value = mock_trace
    mock_trace.span.return_value = mock_span

    from config import cfg
    monkeypatch.setattr(cfg, "LANGFUSE_PUBLIC_KEY", "pk-lf-12345")
    monkeypatch.setattr(cfg, "LANGFUSE_SECRET_KEY", "sk-lf-67890")

    monkeypatch.setattr("core.ai.utils._get_langfuse", lambda: mock_lf)

    with trace_rag_query("test query", "lib_1", username="alice") as tracer:
        with tracer.span("retrieval", count=2):
            pass

    mock_lf.trace.assert_called_once()
    mock_trace.span.assert_called_once()
    mock_span.end.assert_called_once()
