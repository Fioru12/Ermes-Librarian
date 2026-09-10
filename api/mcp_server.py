"""
api/mcp_server.py
Model Context Protocol (MCP) Server Endpoint for Ermes Knowledge.
Exposes Ermes document libraries, vector search, and evidence Q&A as standard MCP tools
for AI agent frameworks (Claude Desktop, Cursor, Antigravity, LangChain, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from api.auth import _verify_api_key, rate_limited
from api.libraries import _answer_question, get_library_store
from core.library_store import LibraryAccessError, LibraryNotFoundError, LibraryStore

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["Model Context Protocol (MCP)"])

MCP_SERVER_INFO = {
    "name": "ermes-knowledge-mcp",
    "version": "2.1.0",
    "description": "Ermes Knowledge Local-First Governed RAG & Evidence Engine",
}

AVAILABLE_TOOLS = [
    {
        "name": "list_libraries",
        "description": "Lists all accessible Ermes document libraries with their metadata and document counts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ask_library",
        "description": "Asks a question against a specific Ermes library. Returns evidence-first answer with precise citations (document, version, excerpt).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {
                    "type": "string",
                    "description": "ID of the target document library.",
                },
                "question": {
                    "type": "string",
                    "description": "Natural language query or question.",
                    "minLength": 2,
                    "maxLength": 2000,
                },
            },
            "required": ["library_id", "question"],
        },
    },
    {
        "name": "search_documents",
        "description": "Performs hybrid semantic and keyword search across chunks in a target library.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "library_id": {
                    "type": "string",
                    "description": "ID of the target document library.",
                },
                "query": {
                    "type": "string",
                    "description": "Search terms or concept.",
                    "minLength": 2,
                    "maxLength": 2000,
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of relevant chunks to return (default 5).",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["library_id", "query"],
        },
    },
]


class JSONRPCRequest(BaseModel):
    jsonrpc: str = Field(default="2.0")
    id: Any = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


# Gli stessi limiti dei modelli delle rotte HTTP equivalenti
# (`AskLibraryRequest` e il controllo sui 2 caratteri di `search_library`).
# Senza questi, un argomento sbagliato di un agente — una domanda da megabyte,
# un `top_k` non numerico — diventava un errore del server invece di un
# rifiuto, e la domanda finiva intera nel prompt del modello.
class _AskArguments(BaseModel):
    library_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=2, max_length=2000)


class _SearchArguments(BaseModel):
    library_id: str = Field(min_length=1, max_length=100)
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)


def _valida(modello: type[BaseModel], args: dict[str, Any]) -> Any:
    try:
        return modello.model_validate(args)
    except ValidationError as errore:
        raise HTTPException(status_code=422, detail=errore.errors(include_url=False)) from errore


@router.get("/info", summary="Metadati del Server MCP Ermes")
def get_mcp_info(user: dict = Depends(_verify_api_key)) -> dict[str, Any]:
    return MCP_SERVER_INFO


@router.get("/tools", summary="Elenco degli strumenti MCP disponibili")
def list_mcp_tools(user: dict = Depends(_verify_api_key)) -> dict[str, Any]:
    return {"tools": AVAILABLE_TOOLS}


# Il limite di frequenza vale sull'esecuzione degli strumenti, non su /info e
# /tools: un client MCP interroga la scoperta a ogni connessione, e strozzarla
# romperebbe il handshake senza proteggere niente.
@router.post("/call", summary="Esegue direttamente uno strumento MCP", dependencies=[Depends(rate_limited)])
def call_mcp_tool(
    request: ToolCallRequest,
    user: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
) -> dict[str, Any]:
    return _dispatch_mcp_tool(request.name, request.arguments, user, store)


@router.post("/rpc", summary="Endpoint JSON-RPC 2.0 per integrazione MCP nativa")
async def mcp_jsonrpc_endpoint(
    req: Request,
    user: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
) -> Any:
    try:
        body = await req.json()
    except Exception:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error"},
            "id": None,
        }

    rpc_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": MCP_SERVER_INFO,
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"tools": AVAILABLE_TOOLS},
        }

    if method == "tools/call":
        # Il limitatore si applica qui e non all'intera rotta: `initialize` e
        # `tools/list` fanno parte del handshake e devono passare sempre.
        rate_limited(req, user)
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            res = _dispatch_mcp_tool(tool_name, arguments, user, store)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                # `str(res)` produceva il repr Python del dizionario: apici
                # singoli e `False` maiuscolo, che nessun client MCP puo'
                # interpretare come JSON.
                "result": {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, default=str)}]},
            }
        except HTTPException as err:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": str(err.detail), "data": {"httpStatus": err.status_code}},
            }
        except Exception:
            # Il messaggio dell'eccezione non torna al chiamante: puo'
            # contenere percorsi del server o frammenti di query.
            _logger.exception("Strumento MCP %s fallito", tool_name)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": "Errore interno nell'esecuzione dello strumento"},
            }

    if method is not None and method.startswith("notifications/"):
        # Una notifica JSON-RPC non attende risposta: rispondere
        # "Method not found" viola il protocollo, e alcuni client abortiscono
        # il handshake subito dopo `initialize`.
        return JSONResponse({}, status_code=202)

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _verifica_accesso(store: LibraryStore, library_id: str, user: dict) -> None:
    """Stessa conversione delle rotte HTTP: biblioteca inesistente e accesso
    negato sono entrambi 404, senza distinguerli.

    Il controllo qui c'era, ma scritto contro il contratto sbagliato — `if not
    lib` dopo `get_library`, che solleva invece di ritornare None. Il ramo era
    codice morto e il rifiuto raggiungeva il client come 500.
    """
    try:
        store.get_library(library_id, user)
    except (LibraryNotFoundError, LibraryAccessError) as errore:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from errore


def _dispatch_mcp_tool(
    name: str,
    args: dict[str, Any],
    user: dict,
    store: LibraryStore,
) -> dict[str, Any]:
    if name == "list_libraries":
        libs = store.list_libraries(user)
        return {
            "libraries": [
                {
                    "id": lib.get("id"),
                    "name": lib.get("name"),
                    "description": lib.get("description"),
                    "document_count": lib.get("document_count", 0),
                    "policy": lib.get("assistant_policy"),
                }
                for lib in libs
            ]
        }

    if name == "ask_library":
        richiesta = _valida(_AskArguments, args)
        lib_id, question = richiesta.library_id, richiesta.question

        _verifica_accesso(store, lib_id, user)

        ans = _answer_question(store, lib_id, question, 5, user)
        return {
            "library_id": lib_id,
            "question": question,
            "answer": ans.get("answer"),
            "evidence_only": ans.get("evidence_only", False),
            "citations": ans.get("citations", []),
        }

    if name == "search_documents":
        ricerca = _valida(_SearchArguments, args)
        lib_id, query, top_k = ricerca.library_id, ricerca.query, ricerca.top_k

        _verifica_accesso(store, lib_id, user)

        results, _profile = store.search_with_profile(lib_id, query, limit=top_k, actor=user)
        return {
            "library_id": lib_id,
            "query": query,
            "matches": [
                {
                    "filename": r.get("filename"),
                    "score": r.get("relevance_score"),
                    "excerpt": r.get("excerpt"),
                    "section": (r.get("citation") or {}).get("locator"),
                }
                for r in results
            ],
        }

    raise HTTPException(status_code=400, detail=f"Strumento MCP sconosciuto: {name}")
