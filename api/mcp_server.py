"""
api/mcp_server.py
Model Context Protocol (MCP) Server Endpoint for Ermes Knowledge.
Exposes Ermes document libraries, vector search, and evidence Q&A as standard MCP tools
for AI agent frameworks (Claude Desktop, Cursor, Antigravity, LangChain, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import _verify_api_key
from api.libraries import _answer_question, get_library_store
from core.library_store import LibraryStore

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
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of relevant chunks to return (default 5).",
                    "default": 5,
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


@router.get("/info", summary="Metadati del Server MCP Ermes")
def get_mcp_info(user: dict = Depends(_verify_api_key)) -> dict[str, Any]:
    return MCP_SERVER_INFO


@router.get("/tools", summary="Elenco degli strumenti MCP disponibili")
def list_mcp_tools(user: dict = Depends(_verify_api_key)) -> dict[str, Any]:
    return {"tools": AVAILABLE_TOOLS}


@router.post("/call", summary="Esegue direttamente uno strumento MCP")
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
) -> dict[str, Any]:
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
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            res = _dispatch_mcp_tool(tool_name, arguments, user, store)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {"content": [{"type": "text", "text": str(res)}]},
            }
        except Exception as err:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": str(err)},
            }

    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


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
        lib_id = args.get("library_id")
        question = args.get("question")
        if not lib_id or not question:
            raise HTTPException(status_code=400, detail="library_id e question sono obbligatori")

        lib = store.get_library(lib_id, user)
        if not lib:
            raise HTTPException(status_code=404, detail="Biblioteca non trovata o non autorizzata")

        ans = _answer_question(store, lib_id, question, 5, user)
        return {
            "library_id": lib_id,
            "question": question,
            "answer": ans.get("answer"),
            "evidence_only": ans.get("evidence_only", False),
            "citations": ans.get("citations", []),
        }

    if name == "search_documents":
        lib_id = args.get("library_id")
        query = args.get("query")
        top_k = int(args.get("top_k", 5))

        if not lib_id or not query:
            raise HTTPException(status_code=400, detail="library_id e query sono obbligatori")

        lib = store.get_library(lib_id, user)
        if not lib:
            raise HTTPException(status_code=404, detail="Biblioteca non trovata")

        results = store.search_library(lib_id, query, top_k=top_k)
        return {
            "library_id": lib_id,
            "query": query,
            "matches": [
                {
                    "filename": r.get("filename"),
                    "score": r.get("score"),
                    "excerpt": r.get("text"),
                    "section": r.get("section"),
                }
                for r in results
            ],
        }

    raise HTTPException(status_code=400, detail=f"Strumento MCP sconosciuto: {name}")
