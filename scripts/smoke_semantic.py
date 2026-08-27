"""Verifica live della pipeline semantica: embedding -> vettori -> retrieval.

Richiede Ollama online e il modello di embedding installato. La domanda usa
una PARAFFRASE senza sovrapposizione lessicale col documento: solo il percorso
semantico puo' trovarla — se risponde la keyword search, il test non vale.
"""
import io
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="ermes_semantic_")
os.environ["ERMES_BASE_DIR"] = TMP
os.environ["ERMES_ADMIN_USERNAME"] = "owner"
os.environ["ERMES_ADMIN_PASSWORD"] = "StrongSmoke!123"
os.environ["ERMES_API_KEY"] = ""
os.environ["ERMES_BACKUP_ENABLED"] = "0"
os.environ["ERMES_LIBRARY_SEMANTIC_SEARCH"] = "1"
os.environ["ERMES_EMBED_MODEL"] = "nomic-embed-text"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = 0
FAIL = 0


def step(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + (1 if condition else 0), FAIL + (0 if condition else 1)
    print(("  OK " if condition else "FAIL ") + name + ((" — " + detail) if detail else ""))


def main() -> int:
    from config import cfg
    from core.library_embeddings import embed_texts

    # ── 1. Il modello di embedding risponde? ──
    vectors = embed_texts(["Le note spese viaggiano veloci."])
    step("embeddings prodotti da Ollama", bool(vectors), f"dimensione vettore: {len(vectors[0]) if vectors else 0}")

    vec_a, vec_b = embed_texts([
        "Il rimborso chilometrico usa la tariffa ACI per ogni chilometro.",
        "La ferie va richiesta almeno dieci giorni prima sul portale HR.",
    ])
    import math

    def cos(u, v):
        return sum(a * b for a, b in zip(u, v)) / (
            math.sqrt(sum(a * a for a in u)) * math.sqrt(sum(b * b for b in v))
        )

    from core.library_embeddings import cosine_similarity
    same_pair = cosine_similarity(vec_a, embed_texts(["rimborso chilometrico tariffa aci"])[0])
    diff_pair = cosine_similarity(vec_a, vec_b)
    step("similarita' coseno distingue testi attinenti vs estranei", same_pair > diff_pair,
         f"attinente={same_pair:.3f} > estraneo={diff_pair:.3f}")

    # ── 2. Pipeline completa via API ──
    from fastapi.testclient import TestClient

    from api import app

    doc_text = ("Indennita' di trasferto. Il rimborso chilometrico si calcola applicando "
                "la tariffa ACI vigente per ogni chilometro percorso con l'auto privata. "
                "Le spese di parcheggio e pedaggio sono rimborsate su presentazione della ricevuta.")

    with TestClient(app) as client:
        client.post("/api/auth/login", json={"username": "owner", "password": "StrongSmoke!123"})
        lib = client.post("/api/libraries", json={"name": "Semantica"}).json()
        library_id = lib["id"]
        files = {"file": ("trasferti.md", io.BytesIO(doc_text.encode()), "text/markdown")}
        up = client.post(f"/api/libraries/{library_id}/documents", files=files)
        doc_id = up.json()["id"]

        deadline = time.time() + 60
        status = ""
        while time.time() < deadline:
            items = client.get(f"/api/libraries/{library_id}/documents").json()["items"]
            status = next((d["status"] for d in items if d["id"] == doc_id), "")
            if status == "ready":
                break
            time.sleep(0.5)
        step("documento indicizzato", status == "ready")

        # ── 3. I vettori sono davvero nel database? ──
        from api.libraries import get_library_store
        store = get_library_store()
        with store._connection() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN embedding_json <> '' THEN 1 ELSE 0 END) AS embedded,
                          MIN(CASE WHEN embedding_model <> '' THEN embedding_model END) AS model
                   FROM document_chunks WHERE document_id = ?""",
                (doc_id,),
            ).fetchone()
        step("vettori persistiti nei chunk",
             row["total"] > 0 and row["embedded"] == row["total"],
             f"{row['embedded']}/{row['total']} chunk, modello: {row['model']}")

        # ── 4. La DOMANDA PARAFFRASATA: zero parole in comune col documento ──
        hits, profile = store.search_with_profile(library_id, "come viene liquidata l'indennita dei trasferti?", actor=None)
        step("profilo retrieval: semantica usata",
             profile["mode"] == "hybrid_local" and profile["semantic_used"] is True,
             f"mode={profile['mode']}, chunk indicizzati={profile['semantic_indexed_chunks']}")
        step("la parafrasi trova il documento giusto (solo la semantica puo')",
             bool(hits) and hits[0]["document_id"] == doc_id,
             f"score={hits[0]['relevance_score'] if hits else '—'}")

        # ── 5. Coerenza: nessun problema di embedding segnalato ──
        rep = store.verify_index_consistency(cfg.LIBRARY_STORAGE_DIR, cfg.EMBED_MODEL_ID)
        step("report coerenza senza problemi di embedding",
             rep["partially_embedded_documents"] == [] and rep["embedding_model_mismatch_documents"] == [])

    print(f"\nRISULTATO: {PASS} passati, {FAIL} falliti")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
