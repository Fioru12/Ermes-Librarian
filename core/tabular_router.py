"""core/tabular_router.py
Router Agentico Ibrido: Rilevamento Intento Tabulare e Arricchimento Evidenze SQL.

Identifica quando una domanda dell'utente richiede calcoli analitici, somme, medie,
conteggi o filtri su dati tabulari (CSV, Excel XLSX) presenti nella biblioteca,
eseguendo l'introspezione e l'interrogazione tramite il motore sandboxed in-memory
e integrando i risultati direttamente nel flusso delle evidenze RAG.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.storage_provider import get_storage_provider
from core.tabular_engine import (
    TabularQueryError,
    get_tabular_schema,
    query_tabular_data,
)

_logger = logging.getLogger("ermes.tabular_router")

# Parole chiave che indicano un potenziale intento analitico/quantitativo su tabelle
_TABULAR_INTENT_PATTERNS = [
    r"\b(quant[ioae]|conteggio|conta|numerosità)\b",
    r"\b(somma|totale|totali|complessiv[oa]|ammontare)\b",
    r"\b(media|medie|mediament[eo])\b",
    r"\b(massim[oa]|minim[oa]|più alt[oa]|più bass[oa]|top|miglior[ie]|peggior[ie])\b",
    r"\b(elenc[ao]|list[ao]|tabell[ae]|righe|colonn[ae]|dataset)\b",
    r"\b(stipendi[o]?|salari[o]?|prezz[io]|cost[io]|fatturat[oi]|bilanci[o]?|ricav[io])\b",
    r"\b(raggrupp[ao]|ripartit[oa]|distribuzion[ie]|per ciascun[oa]|per dipartimento)\b",
    r"\b(filtra|maggiore di|minore di|superiore a|inferiore a|uguale a)\b",
]

_INTENT_REGEX = re.compile("|".join(_TABULAR_INTENT_PATTERNS), re.IGNORECASE)


def detect_tabular_intent(question: str) -> bool:
    """Restituisce True se la domanda dell'utente contiene termini di calcolo o aggregazione tabulare."""
    if not question or len(question.strip()) < 3:
        return False
    return bool(_INTENT_REGEX.search(question))


def is_tabular_filename(filename: str) -> bool:
    """Verifica se il file è in un formato tabulare supportato (.csv, .tsv, .xlsx)."""
    if not filename:
        return False
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    return ext in {"csv", "tsv", "xlsx"}


def enrich_with_tabular_evidence(
    library_id: str,
    question: str,
    store: Any,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """Identifica documenti tabulari pertinenti nella biblioteca ed estrae evidenze analitiche e schemi.

    Restituisce una lista di citazioni strutturate conformi al formato delle evidenze RAG.
    """
    if not detect_tabular_intent(question):
        return []

    try:
        # Recupera l'elenco dei documenti della biblioteca
        docs = store.list_documents(library_id)
    except Exception as e:
        _logger.warning("Impossibile elencare i documenti della biblioteca %s per routing tabulare: %s", library_id, e)
        return []

    tabular_docs = [d for d in docs if is_tabular_filename(str(d.get("filename", "")))]
    if not tabular_docs:
        return []

    storage = get_storage_provider()
    tabular_citations: list[dict[str, Any]] = []

    for doc in tabular_docs[:limit]:
        doc_id = str(doc.get("id", ""))
        filename = str(doc.get("filename", ""))
        storage_path = str(doc.get("storage_path", ""))

        try:
            content = storage.get(storage_path)
            if not content:
                continue

            schema = get_tabular_schema(content, filename, table_name="data")
            col_names = [c.name for c in schema.columns]

            # Esegui una query top aggregata / preview
            preview_res = query_tabular_data(content, filename, "SELECT * FROM data LIMIT 10", table_name="data")

            schema_desc = f"Tabella: data ({schema.row_count} righe totali)\nColonne: {', '.join(col_names)}"
            excerpt_text = f"Struttura Tabella '{filename}':\n{schema_desc}\n\nAnteprima Dati:\n{preview_res.markdown_table}"

            tabular_citations.append({
                "document_id": doc_id,
                "citation": {
                    "filename": filename,
                    "version": int(doc.get("version", 1)),
                    "locator": f"Dataset: {schema.row_count} righe, {len(schema.columns)} colonne",
                },
                "excerpt": excerpt_text,
                "relevance_score": 0.95,
                "injection_suspected": False,
                "is_tabular": True,
            })
        except TabularQueryError as t_err:
            _logger.debug("Routing tabulare non riuscito per %s: %s", filename, t_err)
        except Exception as err:
            _logger.warning("Errore durante l'elaborazione tabulare per %s: %s", filename, err)

    return tabular_citations
