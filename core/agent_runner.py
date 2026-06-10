"""
core/agent_runner.py
Agente multi-step per analisi approfondita delle formule WinSarp.

L'agente riceve una domanda, decide quali strumenti usare, raccoglie
informazioni dal grafo della conoscenza e compone una risposta ragionata.

Non sostituisce il RAG — è una modalità aggiuntiva per analisi complesse.
"""
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

# Assicura che la root del progetto sia nel path
_proj_root = str(Path(__file__).resolve().parent.parent)
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from core.knowledge_graph import KnowledgeGraph
from core.rag_engine import _ollama_url

_logger = logging.getLogger(__name__)

SYS = "WinSarp"  # abbreviazione

TOOL_HELP = {
    "search_formulae": "Cerca formule per nome/tipo/scopo. input: testo (es. fine giornata)",
    "read_formula": "Legge una formula completa. input: id (es. 100)",
    "find_by_field": "Trova formule che usano un campo. input: numero campo (es. 561)",
    "follow_calls": "Formule chiamate da una data formula. input: id",
    "follow_callers": "Formule che chiamano una data formula. input: id",
    "find_by_comparison": "Formule con confronto (campo=valore). input: campo,op,val (es. 564,=,4)",
    "find_by_key_sum": "Formule con pattern KfieldSfield. input: key,sum (es. 21,4)",
    "analizza_campo": "Analisi completa su un campo. input: numero campo",
    "validate_chain": "Verifica coerenza catena chiamate. input: id partenza",
    "compare_formulas": "Confronta due formule. input: id1,id2 (es. 130,140)",
}

TOOL_DESCRIPTIONS = {k: v.split(". input:")[0] for k, v in TOOL_HELP.items()}

SYSTEM_PROMPT = """Sei un analista WinSarp. Hai un grafo con {total} formule.

CATALOGO FORMULE:
{toc}

STRUMENTI (usa SEMPRE per dati reali):
""" + "\n".join(f"{i}. {k}({v})" for i, (k, v) in enumerate(TOOL_HELP.items(), 1)) + """

REGOLE:
- Non inventare MAI dati. Usa SEMPRE strumenti per raccogliere informazioni.
- Cita numeri formula precisi. Rispondi in italiano strutturato.
- Se un importo non torna, usa follow_calls/validate_chain per verificare."""

TOOL_DESCRIPTIONS = {
    "search_formulae": "Cerca formule per nome o descrizione. input: testo di ricerca.",
    "read_formula": "Legge una formula completa. input: id formula (es. 100).",
    "find_by_field": "Trova tutte le formule che usano un campo. input: numero campo (es. 561).",
    "follow_calls": "Mostra le formule chiamate da una data formula. input: id formula.",
    "follow_callers": "Mostra le formule che chiamano una data formula. input: id formula.",
    "find_by_comparison": "Trova formule che confrontano un campo con un valore. input: campo,operatore,valore (es. 561,=,4 oppure 504,=,SFN). operatore puo' essere = # > <.",
    "find_by_key_sum": "Trova formule con pattern KfieldSfield. input: key,sum (es. 21,4).",
    "analizza_campo": "Analisi completa su un campo: reset, K, confronti, riferimenti. input: numero campo (es. 561).",
    "validate_chain": "Segue la catena di chiamate da una formula e verifica coerenza campi. input: id formula di partenza (es. 100).",
    "compare_formulas": "Confronta due formule. input: id1,id2 (es. 130,140).",
}


class AgentRunner:
    """Esegue un'analisi multi-step usando il grafo della conoscenza."""

    def __init__(self, kg: KnowledgeGraph | None = None):
        self.kg = kg or KnowledgeGraph()
        self._history: list[dict] = []
        self._model = None

    def _build_prompt(self, user_query: str) -> str:
        """Costruisce il prompt completo per l'agente."""
        stats = self.kg.stats()
        toc_lines = []
        for n in self.kg.data["nodes"].values():
            tipo = n.get("tipo", "?")[:20]
            toc_lines.append(f"  #{n['id']:>4} - {n['name'][:50]:50s} [{tipo}]")
        toc = "\n".join(toc_lines)

        return SYSTEM_PROMPT.format(total=stats["totale_formule"], toc=toc) + (
            f"\n\nDOMANDA DELL'UTENTE:\n{user_query}\n\n"
            "Rispondi in italiano, strutturato e preciso. "
            "Se servono dati specifici, usa gli strumenti."
        )

    def _call_llm(self, prompt: str, model_id: str, max_tokens: int = 4096) -> str:
        """Chiamata LLM diretta via Ollama."""
        import httpx
        payload = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": max_tokens,
            },
        }
        url = _ollama_url() + "/api/generate"
        try:
            resp = httpx.post(url, json=payload, timeout=300)
            resp.raise_for_status()
            return resp.json()["response"]
        except Exception as e:
            _logger.error("Errore chiamata LLM: %s", e)
            return f"Errore nella chiamata LLM: {e}"

    def _catalog_summary(self) -> str:
        """Restituisce sintesi del catalogo per il prompt."""
        lines = []
        for n in self.kg.data["nodes"].values():
            tipo = (n.get("tipo") or "?")[:20]
            lines.append(f"#{n['id']:>4} {n['name'][:45]:45s} [{tipo}]")
        return "\n".join(lines)

    def analyze(self, query: str, model_id: str = "qwen3.5:4b") -> dict[str, Any]:
        """
        Analisi in due fasi:
        1. LLM pianifica fino a 6 strumenti, esegue tutto
        2. LLM compone risposta finale con i risultati
        """
        t0 = time.time()
        catalog = self._catalog_summary()
        tool_list = "\n".join(f"- {k}({v})" for k, v in TOOL_HELP.items())

        plan_prompt = (
            f"CATALOGO ({self.kg.stats()['totale_formule']} formule):\n{catalog}\n\n"
            f"STRUMENTI:\n{tool_list}\n\n"
            f"DOMANDA: {query}\n\n"
            "Istruzioni: scrivi 1-6 comandi, UNO per riga:\n"
            "strumento(input)\n\n"
            "Esempi:\n"
            "  Domanda: 'Quali formule girano a fine giornata?'\n"
            "  Piano: search_formulae(Fine Giornata)\n"
            "  ---\n"
            "  Domanda: 'Quali formule chiama la 100?'\n"
            "  Piano: follow_calls(100)\n"
            "  ---\n"
            "  Domanda: 'Differenza tra 130 e 140?'\n"
            "  Piano: compare_formulas(130,140)\n"
            "  ---\n"
            "  Domanda: 'Quali formule usano il campo 561?'\n"
            "  Piano: find_by_field(561)\n"
            "  ---\n"
            "  Domanda: 'Spiega la catena dalla 100'\n"
            "  Piano: validate_chain(100)\n"
            "  ---\n"
            "  Domanda: 'Cosa fanno le formule di inizio giornata?'\n"
            "  Piano: search_formulae(Inizio Giornata)\n"
            "  ---\n"
            "Regola: usa SEMPRE almeno uno strumento. Mai rispondere senza dati."
        )

        plan = self._call_llm(plan_prompt, model_id, max_tokens=1024)
        _logger.info("Piano: %s", plan[:200])

        # Se il piano e' solo testo (nessun comando valido), forza un comando basato sulla domanda
        all_steps = self._parse_and_execute_plan(plan)
        if not all_steps:
            forced_tool = self._guess_tool(query)
            if forced_tool:
                _logger.info("Forzo strumento: %s", forced_tool)
                all_steps = self._parse_and_execute_plan(f"{forced_tool[0]}({forced_tool[1]})")
            else:
                prompt = self._build_prompt(query)
                response = self._call_llm(prompt, model_id)
                return {"response": response, "steps": [], "time": round(time.time() - t0, 1)}

        all_steps = self._parse_and_execute_plan(plan)

        context_log = []
        for s in all_steps:
            preview = s["result_preview"]
            if isinstance(preview, str) and len(preview) > 600:
                preview = preview[:600] + "..."
            context_log.append(
                f"[Strumento] {s['tool']}({s['input']})\n"
                f"[Dati ottenuti] {preview}\n"
            )

        ctx = "".join(context_log)
        final_prompt = (
            f"CATALOGO FORMULE:\n{catalog}\n\n"
            f"DOMANDA UTENTE: {query}\n\n"
            f"{ctx}\n"
            "RISPOSTA (usa SOLO i dati sopra, in italiano strutturato):"
        )
        response = self._call_llm(final_prompt, model_id)

        return {"response": response, "steps": all_steps, "time": round(time.time() - t0, 1)}

    def _parse_and_execute_plan(self, plan: str) -> list[dict]:
        """Parsa ed esegue i comandi dal piano dell'agente.

        Supporta formati:
          - tool_name(input)
          - tool_name(input)  (in backtick)
          - tool_name = input
        """
        tool_names = "|".join(re.escape(k) for k in TOOL_DESCRIPTIONS)
        pattern = re.compile(
            rf'(?:`?({tool_names})\s*[=(]\s*["\']?([^"\')\s][^"\'\)]*)["\']?\s*\)?)',
            re.IGNORECASE,
        )

        steps = []
        seen = set()
        for m in pattern.finditer(plan):
            tool_name = m.group(1).lower()
            tool_input = m.group(2)
            key = (tool_name, tool_input)
            if key not in seen:
                seen.add(key)
                result = self._execute_tool(tool_name, tool_input)
                steps.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "result_preview": str(result)[:500] if result else "nessun risultato",
                })
        return steps

    def _guess_tool(self, query: str) -> tuple[str, str] | None:
        """Prova a indovinare lo strumento dalla domanda, se il LLM non genera comandi."""
        q = query.lower()
        ids = [int(w) for w in q.split() if w.isdigit() and len(w) <= 4]
        fields = [int(w) for w in q.split() if w.isdigit() and 100 <= int(w) < 10000]

        # Rileva richieste per tipo formula
        tipo_map = {
            "fine giornata": "Fine Giornata", "f.g": "Fine Giornata",
            "inizio giornata": "Inizio Giornata", "i.g": "Inizio Giornata",
            "di giornata": "Di Giornata", "d.g": "Di Giornata",
            "subroutine": "Subroutine",
        }
        for key, val in tipo_map.items():
            if key in q:
                return ("search_formulae", val)

        # Rileva richieste generiche su "cosa fanno", "quali sono", "formule che"
        parole_generiche = ["quali", "cosa fanno", "cosa fa", "che cosa", "tipo", "categoria",
                           "elenco", "liste", "mostra", "gira", "girano", "tutte"]
        if any(p in q for p in parole_generiche) and not ids:
            # Estrai contesto - prova a capire se parla di un tipo
            for key, val in tipo_map.items():
                if key in q or (key.replace(" ", "") in q.replace(" ", "")):
                    return ("search_formulae", val)
            # Se non capisce il tipo, cerca comunque
            return ("search_formulae", query)

        if "confront" in q or "differenz" in q:
            if len(ids) >= 2:
                return ("compare_formulas", f"{ids[0]},{ids[1]}")
        if "catena" in q or "valid" in q or "catena" in q:
            if ids:
                return ("validate_chain", str(ids[0]))
        if "chiam" in q or "chiamata" in q or "chiamano" in q or "chiama" in q:
            if ids:
                return ("follow_calls", str(ids[0]))
            # "quali formule chiama la 100?" - estrai ID dalla domanda
            for word in q.split():
                if word.isdigit():
                    return ("follow_calls", word)
        if "campo" in q or "reset" in q or "azzer" in q:
            if fields:
                return ("find_by_field", str(fields[0]))
            for w in q.split():
                if w.isdigit():
                    return ("find_by_field", w)
        if "cerca" in q or "trova" in q or "elenco" in q:
            return ("search_formulae", query)
        if ids:
            return ("follow_calls", str(ids[0]))
        return None

    def _parse_int(self, s: str) -> int | None:
        """Parsa un intero da stringa, gestendo spazi e valori vuoti."""
        s = s.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def _execute_tool(self, name: str, input_val: str) -> Any:
        """Esegue uno strumento del grafo della conoscenza."""
        try:
            if name == "search_formulae":
                return [{"id": n["id"], "name": n["name"], "tipo": n.get("tipo")}
                        for n in self.kg.search(input_val)]
            elif name == "read_formula":
                fid = self._parse_int(input_val)
                return self.kg.get_formula(fid) if fid else None
            elif name == "find_by_field":
                f = self._parse_int(input_val)
                if f is None:
                    return {"error": f"campo non valido: {input_val}"}
                return [{"id": n["id"], "name": n["name"], "reset": n.get("reset_fields"),
                         "k": n.get("k_fields"), "refs": n.get("numeric_refs")}
                        for n in self.kg.find_by_field(f)]
            elif name == "follow_calls":
                fid = self._parse_int(input_val)
                targets = self.kg.follow_calls(fid) if fid else []
                return [{"id": n["id"], "name": n["name"], "tipo": n.get("tipo"), "scopo": n.get("scopo")}
                        for n in targets]
            elif name == "follow_callers":
                fid = self._parse_int(input_val)
                callers = self.kg.follow_callers(fid) if fid else []
                return [{"id": n["id"], "name": n["name"], "tipo": n.get("tipo"), "scopo": n.get("scopo")}
                        for n in callers]
            elif name == "find_by_comparison":
                parts = [p.strip() for p in input_val.split(",")]
                field = self._parse_int(parts[0])
                if field is None:
                    return {"error": f"campo non valido: {parts[0]}"}
                op = parts[1] if len(parts) > 1 else None
                val = parts[2] if len(parts) > 2 else None
                return [{"id": n["id"], "name": n["name"], "cmp": n.get("comparisons", {}).get(str(field))}
                        for n in self.kg.find_by_comparison(field, op, val)]
            elif name == "find_by_key_sum":
                parts = [p.strip() for p in input_val.split(",")]
                key = self._parse_int(parts[0]) if parts[0] else None
                sval = self._parse_int(parts[1]) if len(parts) > 1 and parts[1] else None
                return [{"id": n["id"], "name": n["name"], "key_sum": n.get("key_sum")}
                        for n in self.kg.find_by_key_sum(key, sval)]
            elif name == "analizza_campo":
                f = self._parse_int(input_val)
                if f is None:
                    return {"error": f"campo non valido: {input_val}"}
                return {
                    "campo": f,
                    "reset_in": [n["id"] for n in self.kg.find_by_field(f) if f in n["reset_fields"]],
                    "confrontato_in": [{"id": n["id"], "cmp": n.get("comparisons", {}).get(str(f))}
                                       for n in self.kg.find_by_comparison(f)],
                    "riferimenti": [n["id"] for n in self.kg.find_by_field(f)],
                }
            elif name == "validate_chain":
                fid = self._parse_int(input_val)
                if fid is None:
                    return {"error": f"ID formula non valido: {input_val}"}
                result = self.kg.validate_chain(fid)
                if "error" in result:
                    return result["error"]
                return {
                    "start": result["start"],
                    "chain": result["chain"],
                    "steps": [{"id": s["id"], "name": s["name"],
                               "resets": s["resets"], "uses": s["uses"]}
                              for s in result["steps"]],
                    "issues": result["issues"],
                }
            elif name == "compare_formulas":
                parts = [p.strip() for p in input_val.split(",")]
                fid1 = self._parse_int(parts[0])
                fid2 = self._parse_int(parts[1]) if len(parts) > 1 else None
                if fid1 is None or fid2 is None:
                    return "Specifica due id: compare_formulas(130,140)"
                return self.kg.compare_formulas(fid1, fid2)
            else:
                return f"Strumento sconosciuto: {name}"
        except Exception as e:
            return f"Errore nell'esecuzione di {name}({input_val}): {e}"

    def direct_query(self, query: str, model_id: str = "qwen3.5:4b") -> dict[str, Any]:
        """
        Versione semplificata: LLM + contesto completo del grafo.
        L'agente ha tutto il catalogo in contesto e risponde direttamente.
        """
        t0 = time.time()
        prompt = self._build_prompt(query)
        response = self._call_llm(prompt, model_id)
        return {
            "response": response,
            "steps": [],
            "time": round(time.time() - t0, 1),
        }


def run(query: str, model_id: str = "qwen3.5:4b", use_agent: bool = False) -> dict[str, Any]:
    """Entry point per eseguire un'analisi."""
    kg = KnowledgeGraph()
    runner = AgentRunner(kg)
    if use_agent:
        return runner.analyze(query, model_id)
    else:
        return runner.direct_query(query, model_id)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "C:\\ProgettoRAG_DEV")
    import logging
    logging.basicConfig(level=logging.INFO)
    r = run("Qual e la differenza tra arrotondare il totale e arrotondare per intervallo?", use_agent=False)
    print(f"\nTempo: {r['time']}s")
    print(f"Risposta:\n{r['response']}")
