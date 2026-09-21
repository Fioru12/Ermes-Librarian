"""Unit tests for native pgvector HNSW integration in core/postgres_backend.py."""

from unittest.mock import MagicMock

from core.postgres_backend import (
    enable_pgvector,
    format_vector_for_sql,
    search_chunks_vector,
    sync_vector_embeddings,
)


def test_format_vector_for_sql():
    vec = [0.123456789, -0.987654321, 0.0]
    formatted = format_vector_for_sql(vec)
    assert formatted.startswith("[")
    assert formatted.endswith("]")
    assert "0.12345679" in formatted
    assert "-0.98765432" in formatted


def test_enable_pgvector_success():
    conn = MagicMock()
    result = enable_pgvector(conn, vector_dim=1536)
    assert result is True
    assert conn.execute.call_count >= 3
    # Check that vector extension, column and hnsw index were executed
    executed_sqls = [call.args[0] for call in conn.execute.call_args_list]
    assert any("CREATE EXTENSION IF NOT EXISTS vector" in sql for sql in executed_sqls)
    assert any("embedding_vector vector(1536)" in sql for sql in executed_sqls)
    assert any("USING hnsw (embedding_vector vector_cosine_ops)" in sql for sql in executed_sqls)
    conn.commit.assert_called_once()


def test_enable_pgvector_unsupported_graceful():
    conn = MagicMock()
    conn.execute.side_effect = Exception("extension 'vector' is not available")
    result = enable_pgvector(conn)
    assert result is False
    conn.rollback.assert_called_once()


def test_search_chunks_vector_sql_generation():
    conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {"id": "chunk-1", "document_id": "doc-1", "ordinal": 0, "text": "test content", "source_locator": "p.1", "score": 0.88}
    ]
    conn.execute.return_value = mock_cursor

    query_vec = [0.1, 0.2, 0.3]
    results = search_chunks_vector(
        connection=conn,
        library_id="lib-123",
        query_vector=query_vec,
        top_k=5,
        document_ids=["doc-1", "doc-2"],
    )

    assert len(results) == 1
    assert results[0]["id"] == "chunk-1"
    assert results[0]["score"] == 0.88

    # Verify SQL query used cosine distance <=>
    called_sql, params = conn.execute.call_args[0]
    assert "<=>" in called_sql
    assert "c.embedding_vector" in called_sql
    assert "ORDER BY c.embedding_vector <=>" in called_sql
    assert params["library_id"] == "lib-123"
    assert params["limit"] == 5
    assert params["doc_ids"] == ["doc-1", "doc-2"]


def test_sync_vector_embeddings():
    conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        {"id": "chunk-1", "embedding_json": "[0.1, 0.2, 0.3]"},
        {"id": "chunk-2", "embedding_json": [0.4, 0.5, 0.6]},
        {"id": "chunk-3", "embedding_json": "invalid-json"},
    ]
    conn.execute.return_value = mock_cursor

    migrated = sync_vector_embeddings(conn, batch_size=100)
    assert migrated == 2
    # Verify update calls
    update_calls = [c for c in conn.execute.call_args_list if "UPDATE document_chunks" in str(c)]
    assert len(update_calls) == 2
    conn.commit.assert_called_once()
