"""
api/formule.py
Formula WinSarp generation, catalog, validation, import.
"""
import asyncio
import json
import logging
import threading
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import cfg

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Formula"])


class FormulaRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    module: str = Field(default="WinSarp")
    model: str | None = Field(default=None)
    request_id: str | None = Field(default=None, description="ID client per annullamento")
    dialogue_ctx: dict | None = Field(default=None, description="Contesto del dialogo multi-turno")


class ValidateFormulaRequest(BaseModel):
    formula: str = Field(..., min_length=1, max_length=10000, description="Formula WinSarp compatta da validare")
    flow: str | None = Field(None, description="Flusso target: IG, FG Standard, FG GUGEST, FG NEW")


# ── Cancel registry ──
_generation_cancel_events: dict[str, threading.Event] = {}
_generation_cancel_lock = threading.Lock()


@router.post("/api/formula/generate", tags=["Formula"])
async def formula_generate(request: FormulaRequest, req: Request, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from api.auth import _rate_limit
    from legacy_winsarp.core.formula_builder import FormulaBuilder, DialogueContext
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    _rate_limit(req)

    rid = request.request_id or str(uuid.uuid4())
    cancel_event = threading.Event()

    with _generation_cancel_lock:
        _generation_cancel_events[rid] = cancel_event

    try:
        kg = KnowledgeGraph()
        builder = FormulaBuilder(kg)

        dialogue_ctx_obj = None
        if request.dialogue_ctx:
            dialogue_ctx_obj = DialogueContext.from_dict(request.dialogue_ctx)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: builder.generate(request.query)
        )
        result["request_id"] = rid
        if result and "dialogue_ctx" in result and result["dialogue_ctx"]:
            result["dialogue_ctx"] = result["dialogue_ctx"].to_dict()
        # Production flow validation
        if result.get("formula") and result.get("success"):
            try:
                from legacy_winsarp.core.production_flow_validator import ProductionFlowValidator
                pv = ProductionFlowValidator()
                result["production_validation"] = pv.summary(result["formula"])
            except Exception as e:
                _logger.warning("Production validation error: %s", e)
        return result
    except Exception as e:
        _logger.error("Formula generation error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        with _generation_cancel_lock:
            _generation_cancel_events.pop(rid, None)


async def _stream_generate(request: FormulaRequest):
    """Generator per SSE: esegue generate() e invia eventi."""
    from legacy_winsarp.core.formula_builder import FormulaBuilder, DialogueContext
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    rid = request.request_id or str(uuid.uuid4())
    meta = json.dumps({"request_id": rid}, ensure_ascii=False)
    yield f"event: meta\ndata: {meta}\n\n"

    progress = []
    kg = KnowledgeGraph()
    builder = FormulaBuilder(kg)

    dialogue_ctx_obj = None
    if request.dialogue_ctx:
        dialogue_ctx_obj = DialogueContext.from_dict(request.dialogue_ctx)

    def _run():
        return builder.generate(request.query)

    task = asyncio.get_event_loop().run_in_executor(None, _run)

    last_len = 0
    while not task.done():
        await asyncio.sleep(0.5)
        if len(progress) > last_len:
            for msg in progress[last_len:]:
                data = json.dumps({"message": msg}, ensure_ascii=False)
                yield f"event: progress\ndata: {data}\n\n"
            last_len = len(progress)

    for msg in progress[last_len:]:
        data = json.dumps({"message": msg}, ensure_ascii=False)
        yield f"event: progress\ndata: {data}\n\n"

    result = task.result()
    result["request_id"] = rid
    if result and "dialogue_ctx" in result and result["dialogue_ctx"]:
        result["dialogue_ctx"] = result["dialogue_ctx"].to_dict()
    if result.get("formula") and result.get("success"):
        try:
            from legacy_winsarp.core.production_flow_validator import ProductionFlowValidator
            pv = ProductionFlowValidator()
            result["production_validation"] = pv.summary(result["formula"])
        except Exception as e:
            _logger.warning("Production validation error: %s", e)
    yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"


@router.post("/api/formula/generate/stream", tags=["Formula"])
async def formula_generate_stream(request: FormulaRequest, req: Request, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from api.auth import _rate_limit
    _rate_limit(req)
    return StreamingResponse(
        _stream_generate(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/formula/cancel/{request_id}", tags=["Formula"])
async def formula_cancel(request_id: str, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    with _generation_cancel_lock:
        event = _generation_cancel_events.get(request_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Richiesta non trovata o già completata")
    event.set()
    return {"success": True, "message": "Generazione annullata"}


# ── Catalog ──

@router.get("/api/winsarp/catalog", tags=["Formula"])
async def winsarp_catalog(limit: int = 50, q: str | None = None, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    formulas = list(kg.data.get("nodes", {}).values())
    if q:
        ql = q.lower().strip()
        formulas = [
            f for f in formulas
            if ql in str(f.get("id", "")).lower()
            or ql in (f.get("name", "") or "").lower()
            or ql in (f.get("scopo", "") or "").lower()
            or ql in (f.get("tipo", "") or "").lower()
        ]
    formulas = sorted(formulas, key=lambda x: x.get("id", 0))[:limit]
    return {
        "count": len(formulas),
        "items": [
            {
                "id": f.get("id"),
                "name": f.get("name"),
                "tipo": f.get("tipo"),
                "categoria": f.get("tipo_cat") or f.get("categoria"),
                "scopo": f.get("scopo"),
                "calls_r": f.get("calls_r", []),
                "calls_p": f.get("calls_p", []),
                "called_by": f.get("called_by", []),
                "fields_read": f.get("numeric_refs", []),
                "fields_write": f.get("reset_fields", []),
            }
            for f in formulas
        ],
    }


@router.get("/api/winsarp/catalog/{formula_id}", tags=["Formula"])
async def winsarp_formula_detail(formula_id: int, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from legacy_winsarp.core.winsarp.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()
    node = kg.get_formula(formula_id)
    if not node:
        raise HTTPException(status_code=404, detail="Formula non trovata")
    return {
        "id": node["id"],
        "name": node["name"],
        "tipo": node["tipo"],
        "categoria": node["tipo_cat"],
        "scopo": node["scopo"],
        "code": node["code"],
        "calls_r": node["calls_r"],
        "calls_p": node["calls_p"],
        "called_by": node["called_by"],
        "fields_read": node["numeric_refs"],
        "fields_write": node["reset_fields"],
        "operators": node["operators"],
        "comparisons": node["comparisons"],
        "key_sum": node["key_sum"],
        "bracket_refs": node["bracket_refs"],
    }


# ── Validation ──

@router.post("/api/formula/production-validate", tags=["Formula"])
async def formula_production_validate(request: ValidateFormulaRequest, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from legacy_winsarp.core.production_flow_validator import ProductionFlowValidator
    pv = ProductionFlowValidator()
    result = pv.summary(request.formula, flow_name=request.flow)
    return result


@router.post("/api/formula/validate", tags=["Formula"])
async def formula_validate(request: ValidateFormulaRequest, _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    from legacy_winsarp.core.formula_builder import FormulaValidator
    from legacy_winsarp.core.winsarp.linter import WinSarpLinter
    from legacy_winsarp.core.winsarp.validator import LarkFormulaValidator
    from legacy_winsarp.core.winsarp.semantic_validator import SemanticFormulaValidator
    from legacy_winsarp.core.winsarp.workbook_retriever import WorkbookRetriever

    retriever = WorkbookRetriever()
    v = FormulaValidator(retriever)
    l = WinSarpLinter()
    lark_v = LarkFormulaValidator()
    sem_v = SemanticFormulaValidator()

    v_issues = v.validate(request.formula)
    l_issues = l.lint_compact(request.formula)
    lark_issues = lark_v.validate(request.formula)
    sem_issues = sem_v.validate_compact(request.formula)

    from legacy_winsarp.core.production_flow_validator import ProductionFlowValidator
    pv = ProductionFlowValidator()
    pv_summary = pv.summary(request.formula)

    all_issues = v_issues + l_issues + lark_issues + sem_issues

    errors = [
        {"severity": i.severity, "message": i.message, "line": getattr(i, 'line', 0)}
        for i in all_issues
        if i.severity == "error"
    ]
    warnings = [
        {"severity": i.severity, "message": i.message, "line": getattr(i, 'line', 0)}
        for i in all_issues
        if i.severity == "warning"
    ]
    infos = [
        {"severity": "info", "message": i.message, "line": getattr(i, 'line', 0)}
        for i in all_issues
        if i.severity == "info"
    ]

    return {
        "valid": len(errors) == 0,
        "issues": errors + warnings + infos,
        "warnings": warnings,
        "infos": infos,
        "production_validation": pv_summary,
    }


# ── Import ──

@router.post("/api/formula/import", tags=["Formula"])
async def formula_import(file: UploadFile = File(...), _auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    """Import a custom WinSarp workbook markdown file."""
    from legacy_winsarp.core.winsarp.catalog import parse_catalog_text, save_catalog_json
    from legacy_winsarp.core.winsarp.knowledge_graph import build_graph, save_graph, GRAPH_PATH
    from pathlib import Path

    if not file.filename or not file.filename.endswith((".txt", ".md")):
        raise HTTPException(status_code=400, detail="File must be .txt or .md")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File must be UTF-8 or Latin-1 encoded")

    formulas = parse_catalog_text(text)
    if not formulas:
        raise HTTPException(status_code=422, detail="No formulas found in the uploaded file")

    cat_path = Path(cfg.CATALOGO_PATH)
    cat_json_path = Path(cfg.CATALOGO_JSON_PATH)

    # Backup current workbook
    backup_path = cat_path.with_suffix(".txt.bak")
    if cat_path.exists():
        import shutil
        shutil.copy2(cat_path, backup_path)

    # Save new workbook
    cat_path.parent.mkdir(parents=True, exist_ok=True)
    cat_path.write_text(text, encoding="utf-8")

    # Rebuild JSON catalog
    save_catalog_json(cat_json_path, cat_path)

    # Rebuild knowledge graph
    if GRAPH_PATH.exists():
        GRAPH_PATH.unlink()
    graph = build_graph()
    save_graph(graph)

    # Invalidate in-memory cache
    try:
        from legacy_winsarp.core.winsarp import knowledge_graph as _kg_mod
        if hasattr(_kg_mod, "_cached_graph"):
            _kg_mod._cached_graph = None
    except Exception:
        pass

    _logger.info("Workbook imported: %d formulas, graph rebuilt", len(formulas))

    return {
        "success": True,
        "formulas_imported": len(formulas),
        "formula_ids": [f["id"] for f in formulas],
        "graph_nodes": len(graph.get("nodes", {})),
        "graph_edges": len(graph.get("edges", [])),
        "backup": str(backup_path) if backup_path.exists() else None,
    }