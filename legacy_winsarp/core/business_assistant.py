import json
import logging
from pathlib import Path
from typing import Any



_logger = logging.getLogger(__name__)

# Schema per l'estrazione parametri
PARAM_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["straordinario", "premio", "ferie", "arrotondamento", "turno", "causale", "arrotondamento_entrata", "arrotondamento_uscita", "separazione_notturno", "festivo", "festivo_notturno", "maggiorezioni", "altro"]},
        "parameters": {
            "type": "object",
            "properties": {
                "percentuale": {"type": "string"},
                "fascia_oraria": {"type": "string"},
                "base_calcolo": {"type": "string"},
                "periodo": {"type": "string"},
                "tipo_ferie": {"type": "string"},
                "causale": {"type": "string"},
                "fascia_notturna": {"type": "string"},
                "maggiorazione": {"type": "string"},
                "turno_tipo": {"type": "string"},
                "campo_riferimento": {"type": "string"},
                "formula_riferimento": {"type": "string"},
            },
            "additionalProperties": True
        },
        "missing_required": {"type": "array", "items": {"type": "string"}},
        "needs_clarification": {"type": "boolean"},
        "clarification_question": {"type": "string"}
    },
    "required": ["intent", "parameters", "missing_required", "needs_clarification", "clarification_question"]
}

class BusinessAssistant:
    def __init__(self, model_id: str | None = None):
        self.doc_path = Path(__file__).parent.parent / "documenti" / "WinSarp"
        try:
            self.clarificazioni = (self.doc_path / "Clarificazioni.txt").read_text(encoding="utf-8")
        except FileNotFoundError:
            self.clarificazioni = ""

        self.model_id = model_id

    def _call_llm(self, prompt: str, model_id: str | None = None) -> str:
        """Chiama LLM tramite helper centralizzato."""
        from core.ai.utils import call_llm
        try:
            return call_llm(
                prompt=prompt,
                model_id=model_id or self.model_id or "qwen3.5:4b",
                temp=0.0,
                json_mode=False
            )
        except Exception as e:
            _logger.warning("LLM call failed in BusinessAssistant: %s", e)
            return "{}"

    def analyze_request(self, user_request: str) -> dict[str, Any]:
        """
        Analizza la richiesta utente usando LLM per estrarre intent e parametri.
        Ritorna dict con: intent, parameters, missing_required, needs_clarification, clarification_question.
        """
        system_prompt = (
            "Sei un analista esperto di formule WinSarp. "
            "Analizza la richiesta dell'utente e restituisci SOLO un JSON valido con questo schema:\n"
            f"{json.dumps(PARAM_SCHEMA, ensure_ascii=False, indent=2)}\n\n"
            "Regole:\n"
            "1. Identifica l'intent principale tra quelli nell'enum.\n"
            "2. Estrai tutti i parametri menzionati (anche con sinonimi: es 'percentuale' = 'maggiorazione').\n"
            "3. Se mancano parametri OBBLIGATORI per quell'intent, metti needs_clarification=true e scrivi una domanda chiara in italiano.\n"
            "4. I parametri opzionali vanno in parameters, quelli mancanti in missing_required.\n"
            "5. Se la richiesta è chiara e completa, needs_clarification=false e clarification_question=\"\".\n\n"
            "Esempi mapping parametri:\n"
            "- 'straordinario' -> percentuale, fascia_oraria (obbligatori), causale (opzionale)\n"
            "- 'premio' -> base_calcolo, periodo (obbligatori)\n"
            "- 'ferie' -> tipo_ferie (obbligatorio)\n"
            "- 'arrotondamento' -> campo_riferimento, formula_riferimento (opzionale)\n"
            "- 'turno' -> turno_tipo, fascia_oraria\n"
            "- 'causale' -> causale, campo_riferimento\n"
        )

        user_prompt = f"RICHIESTA UTENTE: {user_request}\n\nRispondi SOLO con JSON valido."

        try:
            response = self._call_llm(f"{system_prompt}\n\n{user_prompt}")
            parsed = json.loads(response)

            # Validazione minima
            required_keys = ["intent", "parameters", "missing_required", "needs_clarification", "clarification_question"]
            for k in required_keys:
                if k not in parsed:
                    parsed[k] = [] if k in ["missing_required"] else (False if k == "needs_clarification" else "" if k == "clarification_question" else {})

            return parsed
        except Exception as e:
            _logger.warning("LLM analysis failed, fallback to keyword: %s", e)
            return self._fallback_keyword_analysis(user_request)

    def _fallback_keyword_analysis(self, user_request: str) -> dict:
        """Fallback robusto se LLM fallisce."""
        requirements = {
            "straordinario": ["percentuale", "fascia_oraria"],
            "premio": ["base_calcolo", "periodo"],
            "ferie": ["tipo_ferie"],
        }

        for intent, reqs in requirements.items():
            if intent in user_request.lower():
                missing = [r for r in reqs if r not in user_request.lower()]
                if missing:
                    return {
                        "intent": intent,
                        "parameters": {},
                        "missing_required": missing,
                        "needs_clarification": True,
                        "clarification_question": f"Per generare correttamente la formula '{intent}', mi servono: {', '.join(missing)}. Puoi specificarli?"
                    }
                return {
                    "intent": intent,
                    "parameters": {},
                    "missing_required": [],
                    "needs_clarification": False,
                    "clarification_question": ""
                }

        return {
            "intent": "altro",
            "parameters": {},
            "missing_required": [],
            "needs_clarification": False,
            "clarification_question": ""
        }

    def check_needs_clarification(self, user_request: str) -> str | None:
        """
        Mantiene compatibilità con interfaccia esistente.
        Ritorna stringa di chiarimento se serve, altrimenti None.
        """
        analysis = self.analyze_request(user_request)
        if analysis.get("needs_clarification"):
            return analysis.get("clarification_question")
        return None
