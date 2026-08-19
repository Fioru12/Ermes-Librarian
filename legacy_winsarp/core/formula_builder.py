"""
core/formula_builder.py
WinSarp formula builder with intent-first routing.
"""
import logging
import re
from pathlib import Path
from typing import Any

from legacy_winsarp.core.winsarp.catalog import load_catalog
from legacy_winsarp.core.knowledge_graph import KnowledgeGraph
from core.ai.providers.registry import get_registry

_logger = logging.getLogger(__name__)

# ── Italian stem for inflection support ──────────────────────────────
def _italian_stem(word: str) -> str:
    if len(word) <= 4:
        return word
    if word[-1] in 'aeioAEIO':
        return word[:-1]
    return word

def _token_matches(token: str, word: str) -> bool:
    tl = token.lower()
    wl = word.lower()
    if len(tl) < 4:
        return False
    if re.search(rf'\b{re.escape(tl)}\b', wl):
        return True
    w_stem = _italian_stem(wl)
    t_stem = _italian_stem(tl)
    if len(t_stem) >= 4 and len(w_stem) >= 4:
        if w_stem.startswith(t_stem) or t_stem.startswith(w_stem):
            return True
    return w_stem == t_stem

# ── Glossary-based query expansion ──────────────────────────────────
_TECH_WHITELIST = {"AUTS", "RIPO", "CHIA", "MATT", "POME", "NOTT", "VF", "VU", "IG", "DG", "FG", "SA", "SB", "SN", "SF", "SFN"}

def _expand_query_with_glossary(query: str) -> str:
    try:
        from legacy_winsarp.core.winsarp.glossary import SYNONYM_MAP
    except ImportError:
        return query
    text_lower = query.lower()
    seen = set(t.lower() for t in query.split())
    expanded = list(query.split())
    for synonym, canonical in SYNONYM_MAP.items():
        if len(synonym) <= 3 and synonym.upper() not in _TECH_WHITELIST:
            continue
        if synonym in text_lower and canonical.lower() not in seen:
            expanded.append(canonical)
            seen.add(canonical.lower())
    return ' '.join(expanded)

# ── Intent → family mapping ─────────────────────────────────────────
_INTENT_FAMILY: dict[str, str] = {
    "reset_puro": "azzeramenti",
    "set_field": "assegnazioni",
    "azzeramento_giornata": "azzeramenti",
    "riconoscimento_turno": "turni",
    "calcolo_presenza": "presenze",
    "arrotondamento": "arrotondamenti",
    "pausa_pranzo": "assenze",
    "straordinario_diurno": "straordinario",
    "straordinario_notturno": "straordinario",
    "straordinario_festivo": "straordinario",
    "straordinario_settimanale": "straordinario",
    "maggiorazioni_turnisti": "maggiorazioni",
    "finale_giornata": "flussi_fg",
    "flusso_fg": "flussi_fg",
    "avispa": "flussi_fg",
    "gugest_a": "gugest",
    "gugest_b": "gugest",
    "fg_b": "flussi_fg",
    "primo_giro": "gugest",
    "secondo_giro": "gugest",
    "ritocco_sa_sb": "straordinario",
    "warning_ore": "alert",
    "gestione_auts": "autorizzazioni",
    "gestione_assenze": "assenze",
    "arrotondamento_impiegati": "arrotondamenti",
    "riconoscimento_causale": "causali",
    "festivita": "festivita",
    "arrotondamento_quarti": "arrotondamenti",
    "k_accumulo": "accumulo",
    "catena_formule": "catena",
    "condizionale_generico": "condizioni",
    "durata_intervallo": "calcolo",
    "riferimento_formula": "riferimento",
    "riferimento_causale": "causali",
}

_TIPO_FAMILY: dict[str, str] = {
    "Inizio Giornata": "inizio_giornata",
    "Di Giornata": "di_giornata",
    "Fine Giornata": "fine_giornata",
    "Subroutine": "subroutine",
}

# ── FormulaBuilder ──────────────────────────────────────────────────
class FormulaBuilder:
    """Builds WinSarp formulas with intent-first routing."""

    def __init__(self, kg: KnowledgeGraph, retriever=None):
        self.kg = kg
        self.catalog = load_catalog()
        self.builder = WinSarpBuilder()
        self._retriever = retriever
        self._cot_enabled = True

    @staticmethod
    def _intent_to_family(intent: str) -> str:
        return _INTENT_FAMILY.get(intent, "generico")

    @staticmethod
    def _tipo_to_family(tipo: str) -> str:
        return _TIPO_FAMILY.get(tipo, "generico")

    @staticmethod
    def _normalize_ir(code: str) -> str:
        return re.sub(r'\s+', '', code.strip())

    def _extract_glossary_context(self, query: str) -> str:
        try:
            from legacy_winsarp.core.winsarp.glossary import CONCEPT_TO_FIELD, SYNONYM_MAP
            query_lower = query.lower()
            relevant_concepts = []
            for concept, data in CONCEPT_TO_FIELD.items():
                if concept in query_lower:
                    fields = data.get('fields', [])
                    desc = data.get('description', '')
                    relevant_concepts.append(f"- {concept.capitalize()}: usa campi {fields} ({desc})")
            for syn, canonical in SYNONYM_MAP.items():
                if syn in query_lower and canonical in CONCEPT_TO_FIELD:
                    data = CONCEPT_TO_FIELD[canonical]
                    fields = data.get('fields', [])
                    desc = data.get('description', '')
                    item = f"- {canonical.capitalize()} (da '{syn}'): usa campi {fields} ({desc})"
                    if item not in relevant_concepts:
                        relevant_concepts.append(item)
            if relevant_concepts:
                unique_concepts = list(dict.fromkeys(relevant_concepts))
                return "Variabili WinSarp rilevanti per la tua richiesta:\n" + "\n".join(unique_concepts) + "\n\n"
        except ImportError:
            pass
        return ""

    def _build_light_prompt(self, query: str, catalog_results: list[dict]) -> str:
        prompt = "Genera una formula WinSarp per la seguente richiesta.\n\n"
        glossary_context = self._extract_glossary_context(query)
        if glossary_context:
            prompt += glossary_context
        if catalog_results:
            prompt += "Esempi di formule dal catalogo simili alla richiesta (usa come riferimento per la sintassi):\n"
            for res in catalog_results[:3]:
                name = res.get('name', 'Formula')
                code = res.get('code', '')
                if code:
                    prompt += f"- {name}: {code}\n"
            prompt += "\n"
        prompt += f"Richiesta utente: {query}\n"
        prompt += "Formula generata:"
        return prompt

    def _call_llm_safe(self, prompt: str) -> str:
        try:
            registry = get_registry()
            response = registry.call_llm(
                prompt=prompt,
                system_prompt="Sei un esperto di sintassi per formule WinSarp. Rispondi SEMPRE E SOLO con il codice della formula generata. Non includere spiegazioni, non usare formattazione markdown (niente ```). Solo testo della formula.",
            )
            return response.strip()
        except Exception as e:
            _logger.error("LLM call failed: %s", e)
            return ""

    def _generate_via_llm(self, query: str, catalog_results: list[dict] | None = None) -> dict:
        catalog_results = catalog_results or []
        prompt = self._build_light_prompt(query, catalog_results)
        code = self._call_llm_safe(prompt)
        if code:
            code = self._normalize_ir(code)
            return {"success": True, "formula": code, "source": "generated"}
        return {"success": False, "formula": "", "source": "generated", "error": "LLM not available or failed"}

    def generate(self, query: str, top_n: int = 3, compact: bool = False, **kwargs) -> dict:
        _log = _logger
        query_stripped = query.strip()
        if not query_stripped:
            return {"success": False, "formula": "", "error": "Richiesta vuota",
                    "intent": "unknown", "family": None, "confidence": 0.0}

        # ── Layer 0: Reset puro ──────────────────────────────────────
        reset_match = re.search(
            r'(?:azzera(?:re)?|resetta(?:re)?|reset)\s+(?:i\s+)?(?:campi|campo)?\s*(\d+)(?:\s+(?:e|ed|&)\s+(\d+))?',
            query_stripped.lower(),
        )
        if reset_match:
            fields = [int(f) for f in reset_match.groups() if f]
            formula = "(" + "".join([f"!{f}" for f in fields]) + ")"
            _log.info("Reset rapido per campi: %s", fields)
            return {
                "success": True, "formula": formula,
                "source": "direct_reset", "name": "Reset rapido",
                "scopo": f"Azzeramento campi {', '.join(str(f) for f in fields)}",
                "error": None, "intent": "reset_puro",
                "family": "azzeramenti", "confidence": 1.0,
                "campi_coinvolti": fields,
            }

        # ── Layer 1: Intent classification ───────────────────────────
        intents: list[Any] = []
        try:
            from legacy_winsarp.core.intent_builder import IntentClassifier, build_from_intent, build_from_intents
            intents = IntentClassifier.classify_all(query_stripped)
        except Exception as e:
            _log.warning("Intent classification failed: %s", e)

        # Pick highest-confidence intent >= 0.7
        best_intent = None
        best_confidence = 0.0
        for req in intents:
            if req.confidence >= 0.7 and req.confidence > best_confidence:
                best_intent = req
                best_confidence = req.confidence

        if best_intent and best_intent.intent != "unknown":
            try:
                result = (build_from_intent(best_intent) if len(intents) <= 1
                          else build_from_intents(intents))
                if result and result.get("formula"):
                    formula = self._normalize_ir(result["formula"])
                    _log.info("Intent '%s' -> formula (conf=%.2f)", best_intent.intent, best_confidence)
                    return {
                        "success": True, "formula": formula,
                        "source": "intent_builder",
                        "intent": best_intent.intent,
                        "intents": [r.intent for r in intents],
                        "family": self._intent_to_family(best_intent.intent),
                        "confidence": best_confidence,
                        "campi_coinvolti": list(best_intent.fields.values()) if best_intent.fields else [],
                        "certified": result.get("certified", False),
                        "certification": result.get("certification", ""),
                        "error": None,
                    }
            except Exception as e:
                _log.warning("Intent builder failed for '%s': %s", best_intent.intent, e)

        # ── Layer 2: Explicit formula ID match ───────────────────────
        id_m = re.search(r'\b(\d{1,4})\b', query_stripped)
        if id_m:
            fid = int(id_m.group(1))
            for entry in self.catalog:
                if entry['id'] == fid:
                    code = self._normalize_ir(entry['code'])
                    return {
                        "success": True, "formula": code,
                        "source": "catalog", "formula_id": fid,
                        "name": entry.get('name', ''),
                        "scopo": entry.get('scopo', ''),
                        "tipo": entry.get('tipo', ''),
                        "intent": "riferimento_formula",
                        "family": self._tipo_to_family(entry.get('tipo', '')),
                        "confidence": 0.95, "error": None,
                    }

        # ── Layer 3: Catalog scoring fallback ────────────────────────
        expanded = _expand_query_with_glossary(query_stripped)
        q_lower = expanded.lower()
        q_tokens = [t for t in re.findall(r"[a-z0-9]+", q_lower) if len(t) > 1]

        query_fields = set()
        for m in re.finditer(r'\b(\d{3,4})\b', query_stripped):
            try:
                query_fields.add(int(m.group(1)))
            except ValueError:
                pass

        scored = []
        for entry in self.catalog:
            score = 0
            name_l = entry.get('name', '').lower()
            scopo_l = entry.get('scopo', '').lower()
            entry_fields = set(entry.get('numeric_refs', []))

            if q_lower and q_lower in name_l:
                score += 8
            if q_lower and q_lower in scopo_l:
                score += 4

            name_tokens = re.findall(r"[a-z0-9]+", name_l)
            scopo_tokens = re.findall(r"[a-z0-9]+", scopo_l)

            name_hits = sum(1 for t in q_tokens if any(_token_matches(t, w) for w in name_tokens))
            scopo_hits = sum(1 for t in q_tokens if any(_token_matches(t, w) for w in scopo_tokens))

            score += name_hits * 4 + scopo_hits * 2

            name_token_set = {t for t in q_tokens if any(_token_matches(t, w) for w in name_tokens)}
            scopo_token_set = {t for t in q_tokens if any(_token_matches(t, w) for w in scopo_tokens)}
            if name_token_set and scopo_token_set:
                score += 3

            # Penalty: query mentions fields not present in formula
            if query_fields and entry_fields:
                missing = query_fields - entry_fields
                if missing:
                    score -= 10 * len(missing)

            if score > 0:
                entry_full = dict(entry)
                entry_full['_score'] = score
                entry_full['_name_hits'] = name_hits
                entry_full['_scopo_hits'] = scopo_hits
                scored.append(entry_full)

        if not scored:
            return {
                "success": False, "formula": "",
                "source": None, "error": "Richiesta non riconosciuta",
                "intent": "unknown", "family": None, "confidence": 0.0,
                "alternatives_rejected": [{"reason": "Nessuna formula candidata nel catalogo"}],
            }

        scored.sort(key=lambda x: -x['_score'])
        best = scored[0]
        second = scored[1] if len(scored) > 1 else None
        gap = best['_score'] - (second['_score'] if second else 0)
        threshold = 25

        # Abstention: score insufficient or gap too narrow
        if best['_score'] < threshold or (second and gap < 5):
            alternatives = [{"name": s.get('name', ''), "score": s['_score'],
                             "reason": f"score {s['_score']}"} for s in scored[:3]]
            return {
                "success": False, "formula": "",
                "source": None, "error": "Caso ambiguo: nessuna formula con confidenza sufficiente",
                "intent": "ambiguous", "family": None,
                "confidence": round(best['_score'] / 50.0, 2),
                "best_candidate": best.get('name', ''),
                "best_score": best['_score'],
                "alternatives_rejected": alternatives,
            }

        code = self._normalize_ir(best['code'])
        return {
            "success": True, "formula": code,
            "source": "catalog", "formula_id": best['id'],
            "name": best.get('name', ''),
            "scopo": best.get('scopo', ''),
            "tipo": best.get('tipo', ''),
            "intent": "catalog_match",
            "family": self._tipo_to_family(best.get('tipo', '')),
            "confidence": round(best['_score'] / 50.0, 2),
            "campi_coinvolti": best.get('numeric_refs', []),
            "error": None,
        }

    def set_cot_enabled(self, enabled: bool):
        self._cot_enabled = enabled

    def build_prompt(self, query: str) -> str:
        parts = [
            "Sei un esperto di sintassi per formule WinSarp.",
            "Genera una formula WinSarp per la seguente richiesta.",
            "",
            "Regole sintattiche:",
            "- Usa IF ... THEN ... ELSE ... ENDIF per condizioni",
            "- RESET N per azzerare un campo: produce ( N = Z )",
            "- SET N = valore per assegnare: produce ( N = valore )",
            "- R N per richiamare formula: produce RN",
            "- VF per fine formula",
            "- K N A val per accumulo: produce ( K N A val )",
            "",
        ]

        query_lower = query.lower()
        query_fields = []
        try:
            query_fields = [int(m.group()) for m in re.finditer(r"\d{3,4}", query)]
        except ValueError:
            pass
        graph_lines: list[str] = []
        for f in query_fields:
            info = self.kg.find_by_field(f)
            if info:
                names = [n.get('name', '') for n in info[:3] if n.get('name')]
                graph_lines.append(f"- Campo {f}: utilizzato in {', '.join(names)}")
                graph_lines.append(f"  Aggancia a: {', '.join(names)}")
        if graph_lines:
            parts.append("CONTESTO GRAFO:")
            parts.extend(graph_lines)
            parts.append("")

        try:
            import json
            tmpl_path = Path(__file__).resolve().parent / "templates" / "master_patterns.json"
            if tmpl_path.exists():
                with open(tmpl_path, encoding="utf-8") as f:
                    patterns = json.load(f)
                matched_templates: list[str] = []
                for key, val in patterns.items():
                    key_lower = key.replace("_", " ")
                    key_words = set(key_lower.split())
                    query_words = set(query_lower.split())
                    if key_words & query_words:
                        template = val.get("template", "")
                        if template:
                            matched_templates.append(template)
                if matched_templates:
                    parts.append("TEMPLATE GUIDATO:")
                    for tmpl in matched_templates[:2]:
                        parts.append(tmpl)
                    parts.append("")
        except Exception:
            pass

        parts.append(f"Richiesta: {query}")
        parts.append("Formula:")
        return "\n".join(parts)

    def _classify_intent_via_llm(self, req) -> Any:
        from legacy_winsarp.core.intent_builder import IntentRequest
        return IntentRequest(intent="set_field", confidence=0.5, raw=str(req))

    def _extract_steps(self, raw: str) -> list[str]:
        steps: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("[formula]") or line.startswith("[/formula]"):
                continue
            if line.startswith("[spiegazione]"):
                break
            if line.startswith("#"):
                steps.append(line)
                continue
            line = re.sub(r"\s*#.*$", "", line).strip()
            if line:
                steps.append(line)
        return steps

    def _fix_dangling_endif(self, steps: list[str]) -> list[str]:
        result: list[str] = []
        depth = 0
        for s in steps:
            stripped = s.strip()
            if stripped.startswith("IF "):
                depth += 1
                result.append(s)
            elif stripped == "ENDIF":
                if depth > 0:
                    depth -= 1
                    result.append(s)
            elif stripped == "ELSE":
                if depth > 0:
                    result.append(s)
            elif depth > 0 or stripped in ("VF", "VU"):
                result.append(s)
            elif any(stripped.startswith(cmd) for cmd in ("SET ", "RESET ", "R ", "P ", "K ", "CAMPO70 ")):
                result.append(s)
        return result

    def _validate_steps(self, steps: list[str]) -> str | None:
        depth = 0
        valid_commands = {"IF", "SET", "RESET", "R", "P", "K", "CAMPO70", "VF", "VU", "ENDIF", "ELSE"}
        for s in steps:
            stripped = s.strip()
            if not stripped:
                continue
            if stripped.startswith("IF "):
                if "THEN" not in stripped:
                    return f"IF senza THEN: {stripped}"
                depth += 1
            elif stripped == "ENDIF":
                if depth == 0:
                    return "ENDIF senza IF"
                depth -= 1
            elif stripped == "ELSE":
                if depth == 0:
                    return "ELSE senza IF"
            elif stripped in ("VF", "VU"):
                pass
            else:
                cmd = stripped.split()[0] if stripped.split() else ""
                if cmd not in {c for c in valid_commands}:
                    return f"Comando sconosciuto: {cmd}"
        if depth > 0:
            return f"Mancano {depth} ENDIF"
        return None

    @staticmethod
    def _expand_inline_if(line: str) -> list[str]:
        stripped = line.strip()
        if not stripped.startswith("IF ") or " THEN " not in stripped:
            return [line]
        parts = stripped.split()
        then_idx = -1
        depth = 0
        for i, p in enumerate(parts):
            if p == "(":
                depth += 1
            elif p == ")":
                depth -= 1
            elif p == "THEN" and depth == 0:
                then_idx = i
                break
        if then_idx < 0:
            return [line]
        cond = " ".join(parts[1:then_idx])
        if cond.startswith("(") and cond.endswith(")"):
            cond = cond[1:-1].strip()
        after = parts[then_idx + 1:]
        result: list[str] = [f"IF {cond} THEN"]
        buf: list[str] = []
        for token in after:
            if token in ("ELSE", "ENDIF"):
                if buf:
                    step = " ".join(buf)
                    if step.startswith("IF ") and " THEN " in step:
                        result.extend(FormulaBuilder._expand_inline_if(step))
                        result.append("ENDIF")
                    else:
                        result.append(step)
                    buf = []
                if token == "ELSE":
                    result.append("ELSE")
                else:
                    result.append("ENDIF")
            else:
                buf.append(token)
        if buf:
            step = " ".join(buf)
            if step.startswith("IF ") and " THEN " in step:
                result.extend(FormulaBuilder._expand_inline_if(step))
                result.append("ENDIF")
            else:
                result.append(step)
        return result

    @staticmethod
    def _try_convert_raw_formula_to_steps(raw: str) -> list[str]:
        if not raw or not raw.strip():
            return []
        lines = raw.strip().splitlines()
        steps: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            uline = line.upper()
            if uline in ("VF", "VU"):
                steps.append(uline)
                i += 1
                continue
            m = re.match(r"\(?\s*!\s*(\d+)\s*\)?", line)
            if m:
                steps.append(f"RESET {m.group(1)}")
                i += 1
                continue
            m = re.match(r"\(?\s*(\d+)\s*=\s*('[^']*'|\"[^\"]*\"|\S+)\s*\)?", line)
            if m and not line.strip().startswith("IF"):
                field = m.group(1)
                val = m.group(2)
                if val.upper() != "Z":
                    steps.append(f"SET {field} = {val}")
                else:
                    steps.append(f"RESET {field}")
                i += 1
                continue
            m = re.match(r"^R\s+(\d+)", line, re.IGNORECASE)
            if m:
                steps.append(line)
                i += 1
                continue
            m = re.match(r"^P\s+(\d+)", line, re.IGNORECASE)
            if m:
                steps.append(line)
                i += 1
                continue
            m = re.match(r"\(?\s*K\s*(\d+(?:\s+A\s+\d+(?:\.\d+)?)*)\s*\)?", line, re.IGNORECASE)
            if m:
                steps.append(f"K {m.group(1)}")
                i += 1
                continue
            m = re.match(r"\(?\s*K\s*(\d+)[A]\s*(\d+(?:\.\d+)?)\s*\)?", line, re.IGNORECASE)
            if m:
                steps.append(f"K {m.group(1)} A {m.group(2)}")
                i += 1
                continue
            m = re.match(r"SET\s+(\d+)\s*=\s*(.+)", line, re.IGNORECASE)
            if m:
                steps.append(line)
                i += 1
                continue
            m = re.match(r"RESET\s+(\d+)", line, re.IGNORECASE)
            if m:
                steps.append(line)
                i += 1
                continue
            m = re.match(r"(\d+)\s*U\s*(\S+)\s*\(\((.+)\)\s*\)?\s*$", line)
            if m:
                cond_field = m.group(1)
                cond_val = m.group(2)
                body = m.group(3)
                steps.append(f"IF {cond_field} = {cond_val} THEN")
                inner_steps = FormulaBuilder._try_convert_raw_formula_to_steps(body)
                steps.extend(inner_steps)
                steps.append("ENDIF")
                i += 1
                continue
            if not line.startswith("IF "):
                steps.append(line)
            i += 1
        return steps

    @staticmethod
    def _expand_or_conditions(steps: list[str]) -> list[str]:
        result: list[str] = []
        i = 0
        while i < len(steps):
            s = steps[i]
            if s.startswith("IF ") and "OR" in s:
                has_else = any(steps[j:j+1] == ["ELSE"] for j in range(i, len(steps)) if steps[j] != "ENDIF")
                if has_else:
                    cond_part = s.replace("IF ", "", 1).replace(" THEN", "", 1)
                    or_parts = [p.strip() for p in re.split(r"\s+OR\s+", cond_part, flags=re.IGNORECASE)]
                    result.append(f"IF {or_parts[0]} THEN")
                    then_body: list[str] = []
                    else_body: list[str] = []
                    in_else = False
                    j = i + 1
                    while j < len(steps) and steps[j] != "ENDIF":
                        if steps[j] == "ELSE":
                            in_else = True
                        elif in_else:
                            else_body.append(steps[j])
                        else:
                            then_body.append(steps[j])
                        j += 1
                    for part in or_parts[1:]:
                        result.append(f"IF {part} THEN")
                        result.extend(then_body)
                        result.append("ENDIF")
                    if else_body:
                        result.append("ELSE")
                        result.extend(else_body)
                    result.append("ENDIF")
                    i = j + 1 if j < len(steps) else len(steps)
                    continue
            result.append(s)
            i += 1
        return result


# ── WinSarpBuilder ──────────────────────────────────────────────────
class WinSarpBuilder:
    """Builds WinSarp compact formula strings from IR steps."""

    @staticmethod
    def escape_string_val(val: str) -> str:
        val = val.strip()
        if val in ("I", "Z", "{N}", "[N"):
            return val
        if val.startswith('"') and val.endswith('"'):
            return val
        if val.startswith("'") and val.endswith("'"):
            return val
        try:
            float(val)
            return val
        except ValueError:
            return f'"{val}"'

    @staticmethod
    def _build_set(stmt: str) -> list[str]:
        m = re.match(r"SET\s+(\d+)\s*=\s*(.+)", stmt.strip(), re.IGNORECASE)
        if not m:
            return [f"( {stmt} )"]
        field = m.group(1)
        val = m.group(2).strip()
        return [f"( {field} = {WinSarpBuilder.escape_string_val(val)} )"]

    @staticmethod
    def _build_reset(stmt: str) -> list[str]:
        m = re.match(r"RESET\s+(\d+)", stmt.strip(), re.IGNORECASE)
        if not m:
            return [f"( {stmt} )"]
        return [f"( {m.group(1)} = Z )"]

    @staticmethod
    def _build_r(stmt: str) -> list[str]:
        m = re.match(r"R\s+(\d+)", stmt.strip(), re.IGNORECASE)
        if m:
            return [f"R{m.group(1)}"]
        return [stmt.strip()]

    @staticmethod
    def _build_p(stmt: str) -> list[str]:
        m = re.match(r"P\s+(\d+)", stmt.strip(), re.IGNORECASE)
        if m:
            return [f"P{m.group(1)}"]
        return [stmt.strip()]

    @staticmethod
    def _build_k(stmt: str) -> list[str]:
        s = stmt.strip()
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"F\((\d+)\)", r"\1", s)
        s = s.replace("K", "( K", 1) if s.startswith("K") else f"( K{s}"
        return [f"{s} )"]

    @staticmethod
    def _build_campo70(stmt: str) -> list[str]:
        m = re.match(r"CAMPO70\s+(\d+)", stmt.strip(), re.IGNORECASE)
        if m:
            return [f"( 70 = {m.group(1)} )"]
        return [f"( {stmt} )"]

    @staticmethod
    def _build_expr(expr: str) -> str:
        e = expr.strip()
        if not e:
            return ""
        if e in ("I", "Z"):
            return e
        if (e.startswith('"') and e.endswith('"')) or (e.startswith("'") and e.endswith("'")):
            return e
        if e.startswith("{") or e.startswith("["):
            return e
        try:
            float(e)
            return e
        except ValueError:
            pass
        m = re.match(r"^F\((\d+)\)$", e)
        if m:
            return m.group(1)
        m = re.match(r"^SUM\((.+)\)$", e, re.IGNORECASE)
        if m:
            args = [a.strip() for a in m.group(1).split(",")]
            return "A".join(args)
        m = re.match(r"^AVERAGE\((.+)\)$", e, re.IGNORECASE)
        if m:
            args = [a.strip() for a in m.group(1).split(",")]
            return "A".join(args) + f"S{len(args)}"
        if re.match(r"^-?\d+\.?\d*$", e):
            return e
        if re.match(r"^\d+[AS]\d+", e):
            return f'"{e}"'
        result = e
        result = re.sub(r"\bAND\b", "E", result)
        result = re.sub(r"\bOR\b", "O", result)
        result = re.sub(r"F\((\d+)\)", r"\1", result)
        result = result.replace(" + ", "A").replace(" - ", "S").replace(" / ", "S")
        result = re.sub(r"(\d+)\s*\+\s*(\d+)", r"\1A\2", result)
        result = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1S\2", result)
        result = re.sub(r"(\d+)\s*/\s*(\d+)", r"\1S\2", result)
        result = re.sub(r"(\d+)\s*\*\s*(\d+)", r"\1*\2", result)
        return result

    @staticmethod
    def _parse_cond(cond: str) -> str:
        c = cond.strip()
        if c.startswith("(") and c.endswith(")"):
            inner = c[1:-1].strip()
            if "(" not in inner and ")" not in inner:
                c = inner
        c = re.sub(r"\s+", " ", c)
        c = c.replace(" = ", " U ")
        c = re.sub(r"\bAND\b", "E", c, flags=re.IGNORECASE)
        c = re.sub(r"\bOR\b", "O", c, flags=re.IGNORECASE)
        c = re.sub(r"\bTHEN\b", "", c, flags=re.IGNORECASE)
        c = re.sub(r"\bIF\b", "", c, flags=re.IGNORECASE)
        c = re.sub(r"F\((\d+)\)", r"\1", c)
        c = re.sub(r">\s*0", "> Z", c)
        c = re.sub(r"^IF\s+", "", c).strip()
        c = re.sub(r"\s+THEN$", "", c).strip()
        def _quote_val(m: re.Match) -> str:
            val = m.group(1)
            if val in ("I", "Z"):
                return f"U {val}"
            if val.startswith(("{", "[")):
                return f"U {val}"
            if re.match(r"^-?\d+\.?\d*$", val):
                return f"U {val}"
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                return f"U {val}"
            return f'U "{val}"'
        c = re.sub(r"U\s+(\S+)", _quote_val, c)
        return c

    @staticmethod
    def _needs_parens(expr: str) -> bool:
        e = expr.strip()
        if e in ("I", "Z"):
            return False
        if e.startswith("{") or e.startswith("["):
            return False
        if (e.startswith('"') and e.endswith('"')) or (e.startswith("'") and e.endswith("'")):
            return False
        try:
            float(e)
            return False
        except ValueError:
            pass
        if re.match(r"^-?\d+\.?\d*$", e):
            return False
        return bool(re.search(r"[+\-*/AS]", e))

    @staticmethod
    def _expand_functions(target: str, expr: str) -> list[str]:
        m_min = re.match(r"MIN\((\d+),\s*([^)]+)\)", expr, re.IGNORECASE)
        if m_min:
            f = m_min.group(1)
            v = m_min.group(2).strip()
            return [f"{f} >U {v}", f"{target} = {f}"]
        m_max = re.match(r"MAX\((\d+),\s*([^)]+)\)", expr, re.IGNORECASE)
        if m_max:
            f = m_max.group(1)
            v = m_max.group(2).strip()
            return [f"{f} <U {v}", f"{target} = {f}"]
        m_sum = re.match(r"SUM\((.+)\)", expr, re.IGNORECASE)
        if m_sum:
            args = [a.strip() for a in m_sum.group(1).split(",")]
            return ["A".join(args)]
        m_avg = re.match(r"AVERAGE\((.+)\)", expr, re.IGNORECASE)
        if m_avg:
            args = [a.strip() for a in m_avg.group(1).split(",")]
            return ["A".join(args) + f"S{len(args)}"]
        m_round = re.match(r"ROUND\((.+)\)", expr, re.IGNORECASE)
        if m_round:
            return [m_round.group(1)]
        return []

    @staticmethod
    def _build_if(steps: list[str], idx: int) -> tuple[list[str], int]:
        cond_line = steps[idx]
        cond = cond_line.replace("IF ", "", 1).replace(" THEN", "", 1).strip()
        cond = WinSarpBuilder._parse_cond(cond)
        lines = [f"{cond} (("]
        idx += 1
        else_found = False
        else_lines = []
        then_has_body = False
        while idx < len(steps):
            s = steps[idx]
            if s == "ENDIF":
                if not then_has_body and not else_found:
                    lines.append("VF")
                elif else_found and not then_has_body:
                    lines.append("VF")
                if else_found:
                    lines.append(")(")
                    if not else_lines:
                        lines.append("VF")
                    else:
                        lines.extend(else_lines)
                lines.append("))")
                return (lines, idx + 1)
            if s == "ELSE":
                else_found = True
                idx += 1
                continue
            if s.startswith("IF "):
                sub_lines, idx = WinSarpBuilder._build_if(steps, idx)
                lines.extend(sub_lines)
                then_has_body = True
                continue
            if else_found:
                else_lines.extend(WinSarpBuilder._build(s))
            else:
                lines.extend(WinSarpBuilder._build(s))
                then_has_body = True
            idx += 1
        return (lines, idx)

    @staticmethod
    def _build(step: str) -> list[str]:
        s = step.strip()
        if not s:
            return []
        if s.upper() == "VF" or s.upper() == "VU":
            return [s]
        if re.match(r"^SET\s", s, re.IGNORECASE):
            return WinSarpBuilder._build_set(s)
        if re.match(r"^RESET\s", s, re.IGNORECASE):
            return WinSarpBuilder._build_reset(s)
        if re.match(r"^R\s+\d+", s, re.IGNORECASE):
            return WinSarpBuilder._build_r(s)
        if re.match(r"^P\s+\d+", s, re.IGNORECASE):
            return WinSarpBuilder._build_p(s)
        if re.match(r"^K\s", s, re.IGNORECASE):
            return WinSarpBuilder._build_k(s)
        if re.match(r"^CAMPO70\s", s, re.IGNORECASE):
            return WinSarpBuilder._build_campo70(s)
        return [s]

    @staticmethod
    def build(steps: list[str]) -> str:
        result: list[str] = []
        idx = 0
        while idx < len(steps):
            s = steps[idx].strip()
            if not s:
                idx += 1
                continue
            if s.startswith("IF ") or s.startswith("IF("):
                lines, idx = WinSarpBuilder._build_if(steps, idx)
                result.extend(lines)
            else:
                result.extend(WinSarpBuilder._build(s))
                idx += 1
        return ";".join(result) + (";" if result else "")

    @staticmethod
    def build_compact(ir_steps: list[str]) -> str:
        return WinSarpBuilder.build(ir_steps)

    @staticmethod
    def validate_compact(formula: str) -> str:
        if not formula or not formula.strip():
            return "Formula vuota"
        if "V_START" in formula:
            return "Etichetta V_START non valida"
        upper = formula.upper()
        if "IF " in upper or " THEN" in upper:
            return "Keyword IR non compilate (IF/THEN presenti)"
        return ""

    @staticmethod
    def preprocess_elseif(steps: list[str]) -> list[str]:
        result: list[str] = []
        i = 0
        while i < len(steps):
            s = steps[i].strip()
            if re.match(r"^ELSE\s+IF\s", s, re.IGNORECASE):
                elseif_blocks: list[list[str]] = []
                while i < len(steps) and re.match(r"^ELSE\s+IF\s", steps[i].strip(), re.IGNORECASE):
                    cond = re.sub(r"^ELSE\s+IF\s+", "", steps[i], flags=re.IGNORECASE)
                    cond = re.sub(r"\s+THEN$", "", cond, flags=re.IGNORECASE).strip()
                    i += 1
                    block_body: list[str] = []
                    while i < len(steps):
                        s2 = steps[i].strip()
                        if re.match(r"^ELSE\s+IF\s", s2, re.IGNORECASE):
                            break
                        if s2.upper() == "ENDIF":
                            break
                        block_body.append(steps[i])
                        i += 1
                    elseif_blocks.append([f"IF {cond} THEN"] + block_body)
                endif_count = 0
                for idx_b, block in enumerate(elseif_blocks):
                    result.append("ELSE")
                    result.extend(block)
                    endif_count += 1
                for _ in range(endif_count):
                    result.append("ENDIF")
                if i < len(steps) and steps[i].strip().upper() == "ENDIF":
                    pass
                continue
            else:
                result.append(steps[i])
                i += 1
        return result


class ValidationIssue:
    """Represents a validation issue (error or warning)."""
    def __init__(self, severity: str, message: str, line: int = 0):
        self.severity = severity
        self.message = message
        self.line = line

    def __str__(self) -> str:
        parts = []
        if self.severity == "error":
            parts.append("ERRORE")
        elif self.severity == "warning":
            parts.append("WARNING")
        else:
            parts.append(self.severity.upper())
        parts.append(self.message)
        if self.line:
            parts.append(f"(riga {self.line})")
        return " ".join(parts)


class FormulaValidator:
    """Validates WinSarp compact formulas."""
    def __init__(self, retriever=None):
        self._retriever = retriever

    def validate(self, formula: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not formula or not formula.strip():
            return issues
        if "'I'" in formula or '"I"' in formula:
            issues.append(ValidationIssue("error", "I quotato"))
        if "'Z'" in formula or '"Z"' in formula:
            issues.append(ValidationIssue("error", "Z quotato"))
        m = re.search(r'R(\d{5,})', formula)
        if m:
            issues.append(ValidationIssue("warning", f"R {m.group(1)} inesistente"))
        m = re.search(r'(\d{4,})', formula)
        if m:
            field = int(m.group(1))
            if field > 5000:
                issues.append(ValidationIssue("warning", f"Campo {field} oltre range noto"))
        return issues

    def validate_compact(self, formula: str) -> dict:
        issues = self.validate(formula)
        errors = [i for i in issues if i.severity == "error"]
        return {"valid": len(errors) == 0, "issues": issues}


class DialogueContext:
    """Gestisce il contesto del dialogo multi-turno per la generazione di formule."""

    def __init__(self, original_request: str, questions_asked: list[str]):
        self.original_request = original_request
        self.questions_asked = questions_asked
        self.answers_given = []
        self.current_question_index = 0
        if questions_asked:
            self.turns = [{"role": "assistant", "content": questions_asked[0]}]
        else:
            self.turns = []

    @classmethod
    def from_clarification(cls, original: str, questions: list[dict]) -> "DialogueContext":
        q_list = [q["domanda"] for q in questions if "domanda" in q]
        return cls(original, q_list)

    def add_answer(self, answer: str):
        self.answers_given.append(answer)
        self.turns.append({"role": "user", "content": answer})
        self.current_question_index += 1

    def all_answered(self) -> bool:
        return self.current_question_index >= len(self.questions_asked)

    def build_enriched_request(self) -> str:
        parts = [f"Richiesta originale: {self.original_request}"]
        for q, a in zip(self.questions_asked, self.answers_given):
            parts.append(f"{q}: {a}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "original_request": self.original_request,
            "questions_asked": self.questions_asked,
            "answers_given": self.answers_given,
            "current_question_index": self.current_question_index,
            "turns": self.turns
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DialogueContext":
        ctx = cls(d["original_request"], d["questions_asked"])
        ctx.answers_given = d["answers_given"]
        ctx.current_question_index = d["current_question_index"]
        ctx.turns = d["turns"]
        return ctx

