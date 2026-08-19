"""
api/documents.py
Document upload/delete/reindex.
"""
import logging
import os
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from config import cfg
from api import _resolve_module_name

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])


@router.get("/api/documents", summary="Elenca documenti di un modulo")
async def list_documents(module: str, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    module_name = _resolve_module_name(module)
    modulo_path = os.path.join(cfg.DOCS_DIR, module_name)
    if not os.path.exists(modulo_path):
        return {"documents": []}
    files = []
    for fname in os.listdir(modulo_path):
        fpath = os.path.join(modulo_path, fname)
        if os.path.isfile(fpath):
            files.append({
                "name": fname,
                "size_kb": round(os.path.getsize(fpath) / 1024, 1)
            })
    return {"documents": files}


@router.post("/api/documents/upload", summary="Carica un documento")
async def upload_document(module: str, file: UploadFile = File(...), _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    module_name = _resolve_module_name(module)
    modulo_path = os.path.join(cfg.DOCS_DIR, module_name)
    os.makedirs(modulo_path, exist_ok=True)

    from core.input_validator import sanitize_upload_name
    safe_name = sanitize_upload_name(file.filename)
    dest_path = os.path.join(modulo_path, safe_name)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"message": f"File {safe_name} caricato con successo"}


@router.delete("/api/documents/{filename}", summary="Elimina un documento")
async def delete_document(module: str, filename: str, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    module_name = _resolve_module_name(module)
    if any(sep in filename for sep in ("/", "\\")) or ".." in filename:
        raise HTTPException(status_code=400, detail="Nome file non valido")

    fpath = os.path.join(cfg.DOCS_DIR, module_name, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="File non trovato")

    os.remove(fpath)
    return {"message": f"File {filename} eliminato con successo"}


@router.get("/api/documents/content/{filename}", summary="Legge il contenuto di un documento")
async def read_document_content(module: str, filename: str, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    module_name = _resolve_module_name(module)
    if any(sep in filename for sep in ("/", "\\")) or ".." in filename:
        raise HTTPException(status_code=400, detail="Nome file non valido")
    fpath = os.path.join(cfg.DOCS_DIR, module_name, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="File non trovato")

    lower = filename.lower()
    if lower.endswith(".pdf"):
        try:
            import pymupdf
            doc = pymupdf.open(fpath)
            pages = [page.get_text() for page in doc]
            doc.close()
            content = "\n--- Pagina {} ---\n".join([""] + pages)
            if not content.strip():
                content = f"[PDF di {os.path.getsize(fpath) / 1024:.0f} KB — nessun testo estraibile]"
        except Exception:
            size_kb = os.path.getsize(fpath) / 1024
            content = f"[File PDF di {size_kb:.0f} KB — impossibile estrarre il testo]"
    elif lower.endswith(".docx"):
        try:
            import docx
            d = docx.Document(fpath)
            content = "\n".join(p.text for p in d.paragraphs)
        except Exception:
            content = "[File DOCX — impossibile estrarre il testo]"
    else:
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

    return PlainTextResponse(content)


@router.post("/api/reindex", summary="Rigenera l'indice di un modulo")
async def reindex_documents(module: str, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    module_name = _resolve_module_name(module)
    from core.ai.utils import save_hash
    from legacy_winsarp.core.rag_engine import get_index
    try:
        save_hash(cfg.HASH_FILE, module_name, "")
        index = get_index(module_name, "", cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE)
        if index is None:
            raise HTTPException(status_code=500, detail="Errore rigenerazione indice")
        return {"message": f"Indice per '{module}' rigenerato con successo"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore rigenerazione indice: {e}")