"""
api/graph.py
Knowledge Graph endpoint.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["Knowledge Graph"])


@router.get("/api/graph", summary="Dati del grafo formule WinSarp")
async def knowledge_graph(_auth: None = Depends(__import__('api.auth', fromlist=['_verify_api_key'])._verify_api_key)):
    """Return graph data of WinSarp formulas."""
    graph_path = Path(__file__).parent.parent / "data" / "winsarp_graph.json"
    try:
        raw = json.loads(graph_path.read_text("utf-8"))
        nodes = raw.get("nodes", {})
        edges = raw.get("edges", [])
        tipo_to_group = {
            "inizio": "standard",
            "giornata": "calcolo",
            "fine": "controllo",
            "subroutine": "chiamata",
            "alert": "reset",
        }
        node_list = []
        for nid, ndata in nodes.items():
            group = tipo_to_group.get(ndata.get("tipo_cat", ""), "standard")
            node_list.append({"id": str(nid), "label": str(nid), "group": group})
        link_list = []
        for e in edges:
            link_list.append({
                "source": str(e["source"]),
                "target": str(e["target"]),
                "label": "R" if e["type"] == "calls_r" else "P",
            })
        return {"nodes": node_list, "links": link_list}
    except Exception as ex:
        raise HTTPException(500, f"graph error: {ex}")