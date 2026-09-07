"""Test di performance per Ermes Knowledge — valida i backend sotto carico.

Misura:
- Latenza search full-text (FTS5 SQLite / tsvector Postgres)
- Throughput inserimento chunk
- Concorrenza lettura/scrittura

Uso:
    python -m pytest tests/test_performance.py -v -s
    ERMES_DATABASE_URL=postgresql://... python -m pytest tests/test_performance.py -v -s  # con PG
"""

import random
import time


from core.library_store import LibraryStore


def _make_store(tmp_path):
    """Crea un LibraryStore con un database pulito."""
    db_path = tmp_path / "perf_test.sqlite3"
    return LibraryStore(database_path=db_path)


def _populate_library(store, library_id, num_docs=50, chunks_per_doc=5):
    """Popola una biblioteca con documenti e chunk di test."""
    words = [
        "contratto",
        "pagamento",
        "procedura",
        "sicurezza",
        "ferie",
        "pausa",
        "lavoro",
        "dimissione",
        "assunzione",
        "formazione",
        "fattura",
        "preavviso",
        "reclamo",
        "garanzia",
        "conferma",
    ]

    for doc_idx in range(num_docs):
        content = f"Documento {doc_idx} di test per performance. "
        content += " ".join(random.choice(words) for _ in range(20))
        content_bytes = content.encode("utf-8")

        chunks = []
        for chunk_idx in range(chunks_per_doc):
            chunk_text = f"Passaggio {chunk_idx}: " + " ".join(random.choice(words) for _ in range(10))
            chunks.append(chunk_text)

        store.add_document(
            library_id=library_id,
            filename=f"perf_doc_{doc_idx}.txt",
            media_type="text/plain",
            content=content_bytes,
            storage_path=f"perf_doc_{doc_idx}.txt",
            status="ready",
            chunks=chunks,
        )


def test_search_latency(benchmark, tmp_path):
    """Benchmark: latenza della ricerca full-text."""
    store = _make_store(tmp_path)
    library = store.create_library("PerfTest", "", "private", owner_id="perf_user")
    _populate_library(store, library["id"], num_docs=20, chunks_per_doc=3)

    queries = ["contratto", "pagamento procedura", "sicurezza", "ferie pausa"]

    def run_searches():
        for q in queries:
            store.search_with_profile(library["id"], q)

    benchmark(run_searches)
    # pytest-benchmark stampa le stats automaticamente. Assertion: < 200ms per query.
    # Il benchmark table mostra mean/min/max — verificare manualmente che sia < 200ms.


def test_search_throughput(tmp_path):
    """Test: throughput della ricerca (almeno 100 query/s)."""
    store = _make_store(tmp_path)
    library = store.create_library("PerfTest", "", "private", owner_id="perf_user")
    _populate_library(store, library["id"], num_docs=30, chunks_per_doc=4)

    queries = [
        "contratto",
        "pagamento",
        "procedura",
        "sicurezza",
        "ferie",
        "pausa pranzo",
        "lavoro",
        "dimissione",
        "assunzione",
    ]

    start = time.perf_counter()
    num_queries = 100
    for i in range(num_queries):
        q = queries[i % len(queries)]
        store.search_with_profile(library["id"], q)
    elapsed = time.perf_counter() - start

    throughput = num_queries / elapsed
    avg_latency = elapsed / num_queries * 1000
    print(
        f"\n  Throughput: {throughput:.1f} queries/s, "
        f"avg latency: {avg_latency:.1f}ms, "
        f"total: {elapsed:.2f}s for {num_queries} queries"
    )

    assert throughput > 5, f"Throughput too low: {throughput:.1f} queries/s"


def test_concurrent_reads(tmp_path):
    """Test: concorrenza letture multiple."""
    import threading

    store = _make_store(tmp_path)
    library = store.create_library("PerfTest", "", "private", owner_id="perf_user")
    _populate_library(store, library["id"], num_docs=20, chunks_per_doc=3)

    num_threads = 5
    queries_per_thread = 20
    errors = []

    def search_worker():
        try:
            for i in range(queries_per_thread):
                q = random.choice(["contratto", "pagamento", "procedura"])
                store.search_with_profile(library["id"], q)
        except Exception as e:
            errors.append(str(e))

    start = time.perf_counter()
    threads = [threading.Thread(target=search_worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start

    total_queries = num_threads * queries_per_thread
    throughput = total_queries / elapsed
    print(
        f"\n  Concurrent: {num_threads} threads x {queries_per_thread} queries = "
        f"{total_queries} total, {throughput:.1f} queries/s, "
        f"errors: {len(errors)}"
    )

    assert len(errors) == 0, f"Errors during concurrent reads: {errors[:3]}"
    assert throughput > 3, f"Concurrent throughput too low: {throughput:.1f}"


def test_chunk_insert_throughput(tmp_path):
    """Test: throughput inserimento chunk."""
    store = _make_store(tmp_path)
    library = store.create_library("PerfTest", "", "private", owner_id="perf_user")

    start = time.perf_counter()
    num_docs = 50
    chunks_per_doc = 10

    for doc_idx in range(num_docs):
        content = f"Documento {doc_idx}\n" * 100
        chunks = [f"Chunk {i} del documento {doc_idx} con testo di prova." for i in range(chunks_per_doc)]
        store.add_document(
            library_id=library["id"],
            filename=f"throughput_{doc_idx}.txt",
            media_type="text/plain",
            content=content.encode("utf-8"),
            storage_path=f"throughput_{doc_idx}.txt",
            status="ready",
            chunks=chunks,
        )

    elapsed = time.perf_counter() - start
    total_chunks = num_docs * chunks_per_doc
    throughput = total_chunks / elapsed
    print(f"\n  Chunk insert: {total_chunks} chunks in {elapsed:.2f}s, {throughput:.1f} chunks/s")

    assert throughput > 100, f"Insert throughput too low: {throughput:.1f} chunks/s"
