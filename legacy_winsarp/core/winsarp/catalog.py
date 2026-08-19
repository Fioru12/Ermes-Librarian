"""Parsing strutturato del catalogo WinSarp.

Questo modulo estrae le formule dal workbook markdown e produce una
struttura pulita con:
- metadati di formula
- campi usati
- chiamate R/P
- riferimenti Vxx
- testo sorgente normalizzato
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import cfg
from legacy_winsarp.core.winsarp.parser_rules import CALL_R, CALL_P, FIELD_REFS, VXX_REF

CATALOGO_PATH = Path(cfg.CATALOGO_PATH)
CATALOGO_JSON_PATH = Path(cfg.CATALOGO_JSON_PATH)

_HEADING_RE = re.compile(r"^##\s*\[(\d+)\]\(#\1\)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*$")
_H3_ANCHOR_RE = re.compile(r"^###\s*<a\s+name=\"(\d+)\">.*?</a>\s*\d+\s*[—–-]\s*(.+)$")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_code_block(section: str) -> str:
    blocks = re.findall(r"```(?:\w+)?\n(.*?)```", section, flags=re.DOTALL)
    if not blocks:
        return ""
    code = blocks[0]
    code = code.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in code.split("\n")).strip()


def parse_catalog_text(text: str) -> list[dict[str, Any]]:
    """Estrae le formule dal testo markdown del catalogo."""
    sections = [sec.strip() for sec in re.split(r"\n---\n", text) if sec.strip()]
    formulas: list[dict[str, Any]] = []

    # Mappa tipo→categoria (copiata da knowledge_graph.py)
    TIPO_CATEGORIES = {
        "Inizio Giornata": "Standard",
        "Di Giornata": "Turnisti",
        "Fine Giornata": "Standard",
        "Subroutine": "Subroutine",
        "Subroutine – Alert": "Alert",
    }

    for sec in sections:
        lines = sec.splitlines()
        heading = next((ln for ln in lines if ln.startswith("## [")), None)
        m = None
        is_h3 = False
        if heading:
            m = _HEADING_RE.match(heading)
        if not m:
            # Prova formato H3 con anchor HTML
            heading = next((ln for ln in lines if ln.startswith("### <a name=")), None)
            if heading:
                m = _H3_ANCHOR_RE.match(heading)
                is_h3 = True
        if not m:
            continue

        fid = int(m.group(1))
        if is_h3:
            name = m.group(2).strip()
            tipo_line = next((ln for ln in lines if ln.startswith("**Tipo:**")), "")
            tipo = tipo_line.replace("**Tipo:**", "").strip().rstrip("*/ ")
            categoria = TIPO_CATEGORIES.get(tipo, "Personalizzato")
        else:
            name = m.group(2).strip()
            tipo = m.group(3).strip()
            categoria = m.group(4).strip()
            tipo_line = next((ln for ln in lines if ln.startswith("**Tipo:**")), "")

        scopo_idx = next((i for i, ln in enumerate(lines) if ln.startswith("**Scopo:**")), -1)
        scopo = ""
        if scopo_idx >= 0:
            scopo_lines = []
            for ln in lines[scopo_idx + 1 :]:
                if ln.startswith("**Formula:**") or ln.startswith("```"):
                    break
                if ln.strip() and not ln.startswith("## ") and not ln.startswith("### "):
                    scopo_lines.append(ln.strip())
            scopo = _normalize_text(" ".join(scopo_lines))

        code = _extract_code_block(sec)
        if not code:
            continue

        numeric_refs = sorted({int(x) for x in FIELD_REFS.findall(code) if 1 <= int(x) <= 9999})
        calls_r = sorted({int(x) for x in CALL_R.findall(code)})
        calls_p = sorted({int(x) for x in CALL_P.findall(code)})
        vxx = sorted(set("V" + x for x in VXX_REF.findall(code)))
        return_codes = sorted(set(re.findall(r"\b(VF|VU|V02|V04|V05|V06|V07|V10|V11)\b", code)))

        formulas.append(
            {
                "id": fid,
                "name": name,
                "tipo": tipo,
                "categoria": categoria,
                "scopo": scopo,
                "code": code,
                "numeric_refs": numeric_refs,
                "calls_r": calls_r,
                "calls_p": calls_p,
                "vxx": vxx,
                "return_codes": return_codes,
                "source_heading": heading,
                "tipo_line": tipo_line,
            }
        )

    formulas.sort(key=lambda x: x["id"])
    return formulas


def load_catalog(path: Path = CATALOGO_PATH) -> list[dict[str, Any]]:
    """Carica e parse il catalogo dal file markdown."""
    return parse_catalog_text(path.read_text(encoding="utf-8"))


def save_catalog_json(path: Path = CATALOGO_JSON_PATH, source_path: Path = CATALOGO_PATH) -> list[dict[str, Any]]:
    """Salva una versione JSON del catalogo e ritorna i record estratti."""
    catalog = load_catalog(source_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    return catalog
