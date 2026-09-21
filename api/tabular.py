"""api/tabular.py
Endpoint per interrogazioni SQL in sola lettura e schema introspection su file tabulari (CSV, XLSX).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import _verify_api_key, rate_limited
from api.libraries import get_library_store
from config import cfg
from core.governance import append_audit
from core.library_store import LibraryStore
from core.storage_provider import get_storage_provider
from core.tabular_engine import (
    TabularQueryError,
    get_tabular_schema,
    query_tabular_data,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/libraries", tags=["Tabular Data Analytics"])


class TabularQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, description="Query SQL in sola lettura (es. SELECT ... FROM data)")


@router.get(
    "/{library_id}/documents/{document_id}/schema",
    summary="Restituisce lo schema e il campione dati di un documento tabulare (CSV/XLSX)",
    dependencies=[Depends(rate_limited)],
)
def get_document_tabular_schema(
    library_id: str,
    document_id: str,
    auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    actor = auth
    store.get_library(library_id, actor)

    doc = store.get_document(library_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    filename = str(doc.get("filename", ""))
    suffix = filename.split(".")[-1].lower() if "." in filename else ""
    if suffix not in {"csv", "tsv", "xlsx"}:
        raise HTTPException(
            status_code=400,
            detail=f"Il documento '{filename}' non è un formato tabulare supportato (.csv, .xlsx)",
        )

    storage_path = str(doc.get("storage_path", ""))
    storage = get_storage_provider()
    content = storage.get(storage_path)
    if not content:
        raise HTTPException(status_code=404, detail="Contenuto binario del documento non disponibile nello storage")

    try:
        schema = get_tabular_schema(content, filename, table_name="data")
        return {
            "document_id": document_id,
            "filename": filename,
            "table_name": schema.table_name,
            "columns": [{"name": c.name, "type": c.data_type} for c in schema.columns],
            "row_count": schema.row_count,
            "sample_rows": schema.sample_rows,
        }
    except TabularQueryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        _logger.exception("Errore introspezione schema tabulare per %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail=f"Errore durante l'analisi dello schema: {e}") from e


@router.post(
    "/{library_id}/documents/{document_id}/query-table",
    summary="Esegue una query SQL in sola lettura sul file tabulare",
    dependencies=[Depends(rate_limited)],
)
def execute_document_tabular_query(
    library_id: str,
    document_id: str,
    req: TabularQueryRequest,
    auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    actor = auth
    store.get_library(library_id, actor)

    doc = store.get_document(library_id, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    filename = str(doc.get("filename", ""))
    suffix = filename.split(".")[-1].lower() if "." in filename else ""
    if suffix not in {"csv", "tsv", "xlsx"}:
        raise HTTPException(
            status_code=400,
            detail=f"Il documento '{filename}' non è un formato tabulare supportato (.csv, .xlsx)",
        )

    storage_path = str(doc.get("storage_path", ""))
    storage = get_storage_provider()
    content = storage.get(storage_path)
    if not content:
        raise HTTPException(status_code=404, detail="Contenuto binario del documento non disponibile nello storage")

    try:
        result = query_tabular_data(content, filename, req.query, table_name="data")

        append_audit(
            cfg.AUDIT_FILE,
            "tabular_query_executed",
            actor.get("username", "anonymous"),
            {
                "library_id": library_id,
                "document_id": document_id,
                "row_count": result.row_count,
                "execution_ms": result.execution_ms,
            },
        )

        return {
            "document_id": document_id,
            "filename": filename,
            "query": req.query,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "execution_ms": result.execution_ms,
            "markdown_table": result.markdown_table,
        }
    except TabularQueryError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        _logger.exception("Errore esecuzione query tabulare per %s: %s", document_id, e)
        raise HTTPException(status_code=500, detail=f"Errore durante l'esecuzione della query: {e}") from e
