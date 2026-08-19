"""
chain_of_thought.py
Decompositore Chain-of-Thought per formule WinSarp complesse.

Invece di chiedere all'LLM "scrivi questa formula complessa", la pipeline forza
l'LLM a fare passaggi logici intermedi per ridurre il carico cognitivo.

Flusso:
  Step 1: Identifica campi coinvolti e registri usati
  Step 2: Identifica condizioni logiche (IF/THEN/ELSE, vuoto/non-vuoto, confronti)
  Step 3: Costruisci logica intermedia (IR) per ogni pezzo separatamente
  Step 4: Unisci i pezzi e genera la formula finale compatta

Risultato: formule complesse molto più affidabili e facili da debuggare,
perché ogni passaggio è verificabile singolarmente.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from core.ai.utils import call_llm

_logger = logging.getLogger(__name__)


# ============================================================
# DATACLASS DI OUTPUT PER OGNI STEP
# ============================================================


@dataclass
class CoTStep1_Fields:
    """Risultato Step 1: campi e registri coinvolti."""
    campi_input: list[int] = field(default_factory=list)      # campi letti (es. 251, 271)
    campi_output: list[int] = field(default_factory=list)     # campi scritti (es. 800, 900)
    registri_k: list[str] = field(default_factory=list)       # K accumulo (es. K601, K602)
    flussi_chiamati: list[int] = field(default_factory=list)  # R/P chiamate (es. 120, 2109)
    variabili_appoggio: list[int] = field(default_factory=list)  # 800-899
    spiegazione: str = ""


@dataclass
class CoTStep2_Conditions:
    """Risultato Step 2: condizioni logiche estratte."""
    condizioni: list[dict[str, Any]] = field(default_factory=list)
    # Ogni condizione è un dict con: field, op, value, logical_op (AND/OR)
    # Esempio: {"field": 251, "op": "=", "value": "Z", "logical_op": "AND"}
    condizioni_testuali: list[str] = field(default_factory=list)
    spiegazione: str = ""


@dataclass
class CoTStep3_IR_Piece:
    """Un singolo pezzo di logica IR."""
    label: str                                      # es. "Riconoscimento turno", "Calcolo presenza"
    ir_steps: list[str] = field(default_factory=list)  # Step IR per questo pezzo
    condizioni_applicabili: list[int] = field(default_factory=list)  # Indici condizioni da Step2
    ordine: int = 0                                 # Ordine di esecuzione
    spiegazione: str = ""


@dataclass
class CoTStep4_Final:
    """Risultato Step 4: formula finale completa."""
    ir_steps_completi: list[str] = field(default_factory=list)  # IR completo ordinato
    formula_compact: str = ""                                    # Formula compatta finale
    spiegazione: str = ""


# ============================================================
# PROMPT PER OGNI STEP
# ============================================================


PROMPT_STEP1 = """Sei un analista di formule WinSarp. Il tuo compito è IDENTIFICARE I CAMPI
coinvolti in una richiesta utente di una formula WinSarp.

Analizza la richiesta e produci UN JSON con questa struttura:
{{
  "campi_input": [lista di numeri di campo LETTI/consultati dalla formula],
  "campi_output": [lista di numeri di campo SCRITTI/modificati dalla formula],
  "registri_k": ["lista stringhe Kxxx coinvolti, es. K601, K602"],
  "flussi_chiamati": [lista numeri formula chiamati via R/P],
  "variabili_appoggio": [lista campi 800-899 usati come temporanei],
  "spiegazione": "breve spiegazione testo di cosa fa la formula e quali campi coinvolge"
}}

REGOLE CAMPIONARIO:
- 251-257 = entrate intervalli (mattina, pomeriggio, sera, notte)
- 271-277 = uscite intervalli
- 800-899 = campi di appoggio / calcolo
- 900 = flag presenza/riconoscimento turno
- 50-58 = causali e parametri turno
- 1-6 = totalizzatori (3=ore presenza, 4=ore straordinario...)
- K601-K616 = accumuli progressivi
- 71-78 = campi temporanei per CAMPO70
- 70 = funzione built-in CAMPO70

Richiesta utente: "{user_request}"

Rispondi SOLO con il JSON, nient'altro.
"""


PROMPT_STEP2 = """Sei un analista di condizioni logiche WinSarp. Il tuo compito è ESTRARRE
le CONDIZIONI LOGICHE da una richiesta utente.

Analizza la richiesta e produci UN JSON con questa struttura:
{{
  "condizioni": [
    {{
      "field": <numero campo>,
      "op": "<operatore: = | > | < | >= | <= | # | !=>",
      "value": "<valore di confronto: Z per zero/vuoto, I per vero, numero, stringa>",
      "logical_op": "AND"  (default, lascia AND se singola)
    }}
  ],
  "condizioni_testuali": [
    "descrizione testo di ogni condizione in italiano"
  ],
  "spiegazione": "spiegazione delle condizioni trovate"
}}

REGOLE:
- "vuoto" / "vuota" / "Z" -> op: "=", value: "Z"
- "non vuoto" / "non vuota" / "presente" -> op: "#", value: "Z"
- "maggiore di" / "supera" -> op: ">"
- "minore di" -> op: "<"
- "uguale a" -> op: "="
- "diverso da" -> op: "#"
- Condizioni multiple: separa con "AND" o "OR" in logical_op
- Se la richiesta ha "se/altrimenti" (if/else), estrai entrambe le condizioni
- Se non ci sono condizioni esplicite, condizioni_testuali = ["sempre vero"]

Richiesta utente: "{user_request}"

Campi già identificati: {fields_json}

Rispondi SOLO con il JSON, nient'altro.
"""


PROMPT_STEP3 = """Sei un programmatore WinSarp specializzato nella GENERAZIONE di step IR
per formule WinSarp. Il tuo compito è COSTRUIRE OGNI PEZZO DI LOGICA
separatamente, producendo step IR per ogni blocco funzionale.

INPUT:
- Richiesta: {user_request}
- Campi coinvolti: {fields_json}
- Condizioni logiche: {conditions_json}

Per ogni blocco logico che identifichi, produci UN JSON con questa struttura:
{{
  "pezzi": [
    {{
      "label": "nome del blocco logico",
      "ir_steps": [
        "SET 800 = '100'",
        "IF 251 = Z THEN",
        "  RESET 900",
        "  VF",
        "ENDIF",
        ...
      ],
      "ordine": <numero sequenziale>,
      "spiegazione": "cosa fa questo pezzo"
    }}
  ]
}}

COMANDI IR DISPONIBILI (uno per riga, mai compatti):
- SET N = valore       (assegnazione)
- RESET N              (azzeramento)
- IF cond THEN         (inizio condizionale)
- ELSE                 (ramo alternativo)
- ENDIF                (fine condizionale)
- R N                  (salto a formula N)
- P N                  (chiamata subroutine)
- VF                   (fine formula)
- VU                   (salta ultimo periodo)
- K N A/S val          (accumulo/sottrazione)
- CAMPO70 N            (funzione built-in)
- GOTO Vxx             (salto a label)
- MARK Vxx             (marca label)
- COMMENT ...          (commento)
- {N}                  (dereferenza campo)
- FIELD N              (riferimento campo)

REGOLE FONDAMENTALI:
- USA SOLO NUMERI per i campi (800, 900, 50, 55, 3, 4...)
- MAI variabili tipo N.
- Flag: I = VERO, Z = FALSO — MAI quotare I e Z.
- Numeri: '100' con apici singoli. Stringhe: "MATT" doppi apici.
- Ogni IF/THEN/ELSE/ENDIF su riga separata.
- NON mischiare E e O nella stessa condizione.
- MAI ELSE IF — usa ELSE + IF annidato.
- VF sempre alla fine del blocco se terminale.
- Per campi 71-78 devi sempre RESETTARLI prima di usarli con CAMPO70.

CAMPI IMPORTANTI:
- 251-257 = entrate (mattina=251, pomeriggio=252, sera=253...)
- 271-277 = uscite
- 800-899 = appoggio
- 900 = flag turno
- 71-78 = temporanei CAMPO70 (vanno resettati)
- 70 = funzione built-in

Rispondi SOLO con il JSON, nient'altro.
"""


PROMPT_STEP4 = """Sei un integratore di formule WinSarp. Il tuo compito è UNIRE i pezzi
di logica IR in una formula completa, e poi convertirla in SINTASSI COMPATTA WinSarp.

INPUT:
- Richiesta utente: {user_request}
- Campi: {fields_json}
- Condizioni: {conditions_json}
- Pezzi IR: {pieces_json}

FASE 1: Unisci gli step IR nell'ordine corretto
FASE 2: Converti in sintassi compatta WinSarp

Produci UN JSON:
{{
  "ir_steps_completi": [
    "step1",
    "step2",
    ...
  ],
  "formula_compact": "sintassi compatta WinSarp su UNA RIGA",
  "spiegazione": "spiegazione della formula finale"
}}

REGOLE SINTASSI COMPATTA:
- Assegnazioni: (800 = '250')
- Reset multipli: (!800!801!802)
- IF/THEN: condizione ((azione1)(azione2)VF; else_body
- IF/THEN senza ELSE: condizione (azione)
- Accumulo: (K601 A '3')
- R/P: R120  o  P2109
- VF: VF
- CAMPO70: (70='2')
- Campi di appoggio: (800 = 73)
- Operatori condizione: U (=), # (!=), >, <, >U (>=), <U (<=)
- E logico: spaziato (55 U I E 50 U '2')
- O logico: spaziato (55 U I O 50 U '7')
- I flag nudi: I, Z (MAI quotati)
- Stringhe: "MATT", "POME"
- Numeri: '15', '100'
- Label: V02, V04, V10, V11

REGOLE STRUTTURALI:
- I reset dei campi temporanei (71-78) vanno all'inizio
- La formula deve essere autosufficiente o chiamare P per subroutine
- VF in fondo se non R/P finale
- VU per saltare pezzi non necessari

Rispondi SOLO con il JSON, nient'altro.
"""


# ============================================================
# CHAIN-OF-THOUGHT ENGINE
# ============================================================


class ChainOfThoughtEngine:
    """Esegue la decomposizione 4-step per formule WinSarp complesse.

    Ogni step è una chiamata LLM separata con un prompt specializzato.
    Il risultato di ogni step viene passato come contesto allo step successivo.
    """

    def __init__(self, model_id: str | None = None):
        self.model_id = model_id
        self._debug_steps: list[dict] = []

    # ---- Step 1: Identifica campi ----

    def step1_identify_fields(self, user_request: str) -> CoTStep1_Fields:
        """Step 1: identifica campi coinvolti nella richiesta."""
        prompt = PROMPT_STEP1.replace("{user_request}", user_request)

        try:
            raw = call_llm(prompt, model_id=self.model_id, temp=0.0, json_mode=False)
            data = self._safe_parse_json(raw)
            if not data:
                return self._step1_fallback(user_request)

            result = CoTStep1_Fields(
                campi_input=[int(f) for f in data.get("campi_input", []) if str(f).isdigit()],
                campi_output=[int(f) for f in data.get("campi_output", []) if str(f).isdigit()],
                registri_k=[str(r) for r in data.get("registri_k", [])],
                flussi_chiamati=[int(f) for f in data.get("flussi_chiamati", []) if str(f).isdigit()],
                variabili_appoggio=[int(f) for f in data.get("variabili_appoggio", []) if str(f).isdigit()],
                spiegazione=data.get("spiegazione", ""),
            )
            self._debug_steps.append({"step": 1, "prompt": prompt, "result": data})
            return result

        except Exception as e:
            _logger.warning("CoT step1 fallito: %s", e)
            return self._step1_fallback(user_request)

    def _step1_fallback(self, user_request: str) -> CoTStep1_Fields:
        """Fallback: estrazione campi via regex quando l'LLM fallisce."""
        campi = sorted(set(int(f) for f in re.findall(r'\b\d{2,4}\b', user_request) if 1 <= int(f) <= 999))
        return CoTStep1_Fields(
            campi_input=campi,
            spiegazione=f"Fallback regex: campi trovati = {campi}",
        )

    # ---- Step 2: Identifica condizioni ----

    def step2_identify_conditions(self, user_request: str, fields: CoTStep1_Fields) -> CoTStep2_Conditions:
        """Step 2: identifica condizioni logiche."""
        fields_json = json.dumps({
            "campi_input": fields.campi_input,
            "campi_output": fields.campi_output,
            "registri_k": fields.registri_k,
        }, indent=2)

        prompt = PROMPT_STEP2.replace("{user_request}", user_request).replace("{fields_json}", fields_json)

        try:
            raw = call_llm(prompt, model_id=self.model_id, temp=0.0, json_mode=False)
            data = self._safe_parse_json(raw)
            if not data:
                return CoTStep2_Conditions(spiegazione="Nessuna condizione identificata (fallback)")

            condizioni = data.get("condizioni", [])
            condizioni_testuali = data.get("condizioni_testuali", [])
            if not condizioni and not condizioni_testuali:
                condizioni_testuali = ["sempre vero"]

            result = CoTStep2_Conditions(
                condizioni=condizioni,
                condizioni_testuali=condizioni_testuali,
                spiegazione=data.get("spiegazione", ""),
            )
            self._debug_steps.append({"step": 2, "prompt": prompt, "result": data})
            return result

        except Exception as e:
            _logger.warning("CoT step2 fallito: %s", e)
            return CoTStep2_Conditions(spiegazione=f"Errore: {e}")

    # ---- Step 3: Costruisci IR per pezzo ----

    def step3_build_pieces(
        self,
        user_request: str,
        fields: CoTStep1_Fields,
        conditions: CoTStep2_Conditions,
    ) -> list[CoTStep3_IR_Piece]:
        """Step 3: costruisce logica IR per ogni pezzo separatamente."""
        fields_json = json.dumps({
            "campi_input": fields.campi_input,
            "campi_output": fields.campi_output,
            "registri_k": fields.registri_k,
            "flussi_chiamati": fields.flussi_chiamati,
            "variabili_appoggio": fields.variabili_appoggio,
        }, indent=2)

        conditions_json = json.dumps({
            "condizioni": conditions.condizioni,
            "condizioni_testuali": conditions.condizioni_testuali,
        }, indent=2)

        prompt = PROMPT_STEP3.replace("{user_request}", user_request)
        prompt = prompt.replace("{fields_json}", fields_json)
        prompt = prompt.replace("{conditions_json}", conditions_json)

        try:
            raw = call_llm(prompt, model_id=self.model_id, temp=0.1, json_mode=False)
            data = self._safe_parse_json(raw)
            if not data or "pezzi" not in data:
                return self._step3_fallback(fields, conditions)

            pezzi = []
            for idx, p in enumerate(data.get("pezzi", [])):
                pezzi.append(CoTStep3_IR_Piece(
                    label=p.get("label", f"Pezzo {idx+1}"),
                    ir_steps=p.get("ir_steps", []),
                    condizioni_applicabili=[int(c) for c in p.get("condizioni_applicabili", [])],
                    ordine=p.get("ordine", idx + 1),
                    spiegazione=p.get("spiegazione", ""),
                ))

            pezzi.sort(key=lambda x: x.ordine)
            self._debug_steps.append({"step": 3, "prompt": prompt, "result": data})
            return pezzi

        except Exception as e:
            _logger.warning("CoT step3 fallito: %s", e)
            return self._step3_fallback(fields, conditions)

    def _step3_fallback(self, fields: CoTStep1_Fields, conditions: CoTStep2_Conditions) -> list[CoTStep3_IR_Piece]:
        """Fallback: genera un singolo pezzo generico."""
        steps = ["COMMENT Formula generata automaticamente via CoT"]
        for c in fields.campi_output:
            steps.append(f"RESET {c}")
        for cond in conditions.condizioni:
            op = cond.get("op", "=")
            val = cond.get("value", "Z")
            field = cond.get("field", 0)
            if field:
                steps.append(f"IF {field} {op} {val} THEN")
                steps.append(f"  SET {field} = '1'")
                steps.append("ENDIF")
        steps.append("VF")
        return [CoTStep3_IR_Piece(
            label="Formula generica (fallback)",
            ir_steps=steps,
            ordine=1,
            spiegazione=f"Fallback: {len(fields.campi_output)} campi output, {len(conditions.condizioni)} condizioni",
        )]

    # ---- Step 4: Assembla formula finale ----

    def step4_assemble(
        self,
        user_request: str,
        fields: CoTStep1_Fields,
        conditions: CoTStep2_Conditions,
        pieces: list[CoTStep3_IR_Piece],
    ) -> CoTStep4_Final:
        """Step 4: unisce i pezzi e genera formula compatta finale."""
        pieces_json = json.dumps([
            {
                "label": p.label,
                "ir_steps": p.ir_steps,
                "ordine": p.ordine,
                "spiegazione": p.spiegazione,
            }
            for p in pieces
        ], indent=2)

        fields_json = json.dumps({
            "campi_input": fields.campi_input,
            "campi_output": fields.campi_output,
            "registri_k": fields.registri_k,
            "flussi_chiamati": fields.flussi_chiamati,
        }, indent=2)

        conditions_json = json.dumps({
            "condizioni": conditions.condizioni,
            "condizioni_testuali": conditions.condizioni_testuali,
        }, indent=2)

        prompt = PROMPT_STEP4.replace("{user_request}", user_request)
        prompt = prompt.replace("{fields_json}", fields_json)
        prompt = prompt.replace("{conditions_json}", conditions_json)
        prompt = prompt.replace("{pieces_json}", pieces_json)

        try:
            raw = call_llm(prompt, model_id=self.model_id, temp=0.1, json_mode=False)
            data = self._safe_parse_json(raw)
            if not data:
                return self._step4_fallback(pieces)

            ir_steps = data.get("ir_steps_completi", [])
            formula_compact = data.get("formula_compact", "")

            # Se l'LLM non ha prodotto la formula compatta, generala dagli IR
            if not formula_compact and ir_steps:
                formula_compact = self._ir_to_compact(ir_steps)

            # Genera spiegazione
            spiegazione = data.get("spiegazione", "")
            if not spiegazione:
                spiegazione = (
                    f"Formula composta da {len(pieces)} blocchi logici:\n"
                    + "\n".join(f"  {i+1}. {p.label}: {p.spiegazione}" for i, p in enumerate(pieces))
                )

            result = CoTStep4_Final(
                ir_steps_completi=ir_steps,
                formula_compact=formula_compact,
                spiegazione=spiegazione,
            )
            self._debug_steps.append({"step": 4, "prompt": prompt, "result": data})
            return result

        except Exception as e:
            _logger.warning("CoT step4 fallito: %s", e)
            return self._step4_fallback(pieces)

    def _step4_fallback(self, pieces: list[CoTStep3_IR_Piece]) -> CoTStep4_Final:
        """Fallback: concatena IR steps in ordine e genera compact."""
        all_steps = []
        for p in sorted(pieces, key=lambda x: x.ordine):
            all_steps.extend(p.ir_steps)

        if not all_steps:
            all_steps = ["COMMENT Nessuna logica generata", "VF"]

        compact = self._ir_to_compact(all_steps)
        return CoTStep4_Final(
            ir_steps_completi=all_steps,
            formula_compact=compact,
            spiegazione=f"Formula fallback da {len(pieces)} pezzi concatenati",
        )

    # ---- IR -> Compact converter (inline, usa regex semplici) ----

    def _ir_to_compact(self, ir_steps: list[str]) -> str:
        """Converte IR steps in sintassi compatta WinSarp usando pattern semplici.

        Questa è una versione leggera che non richiede il full WinSarpBuilder
        per generare comunque output valido nei casi base.
        """
        from legacy_winsarp.core.formula_builder import WinSarpBuilder
        builder = WinSarpBuilder()
        try:
            compact = builder.build_compact(ir_steps)
            return compact
        except Exception as e:
            _logger.warning("WinSarpBuilder fallito in CoT fallback: %s", e)
            # Mini-converter di emergenza
            return self._mini_compact(ir_steps)

    @staticmethod
    def _mini_compact(ir_steps: list[str]) -> str:
        """Mini-converter di emergenza IR -> compact (solo casi semplici)."""
        lines = []
        for s in ir_steps:
            s = s.strip()
            if not s:
                continue
            if s.startswith("SET "):
                rest = s[4:].strip()
                if "=" in rest:
                    field, value = rest.split("=", 1)
                    value = value.strip().strip("'\"").strip()
                    if value.upper() in ("I", "Z"):
                        lines.append(f"({field.strip()}={value})")
                    elif value.replace(".", "").isdigit():
                        lines.append(f"({field.strip()}='{value}')")
                    else:
                        lines.append(f"({field.strip()}=\"{value}\")")
            elif s.startswith("RESET "):
                f = s[6:].strip()
                lines.append(f"(!{f})")
            elif s.startswith("R "):
                lines.append(f"R{s[2:].strip()}")
            elif s.startswith("P "):
                lines.append(f"P{s[2:].strip()}")
            elif s.startswith("K "):
                parts = s[2:].strip().split()
                if len(parts) >= 3:
                    lines.append(f"(K{parts[0]} {parts[1]} '{parts[2]}')")
            elif s.startswith("CAMPO70 "):
                lines.append(f"(70='{s[8:].strip()}')")
            elif s.startswith("IF ") and s.endswith(" THEN"):
                cond = _cond_to_compact(s[3:-5].strip())
                lines.append(cond)
            elif s == "ENDIF" or s == "ELSE":
                continue
            elif s in ("VF", "RETURN"):
                lines.append("VF")
            elif s == "VU":
                lines.append("VU")
            elif s.startswith("COMMENT") or s.startswith("#"):
                comment = s.split(maxsplit=1)[-1] if " " in s else s
                lines.append(f"? {comment}")
        return "\n".join(lines)

    # ---- Esecuzione pipeline completa ----

    def run_pipeline(self, user_request: str) -> CoTStep4_Final:
        """Esegue la pipeline CoT completa (4 step)."""
        self._debug_steps = []
        _logger.info("CoT pipeline: step 1/4 (identifica campi)")
        fields = self.step1_identify_fields(user_request)

        _logger.info("CoT pipeline: step 2/4 (identifica condizioni)")
        conditions = self.step2_identify_conditions(user_request, fields)

        _logger.info("CoT pipeline: step 3/4 (costruisci pezzi IR)")
        pieces = self.step3_build_pieces(user_request, fields, conditions)

        _logger.info("CoT pipeline: step 4/4 (assembla formula finale)")
        final = self.step4_assemble(user_request, fields, conditions, pieces)

        return final

    def get_pipeline_summary(self) -> dict:
        """Ritorna riepilogo della pipeline per debugging."""
        return {
            "steps": len(self._debug_steps),
            "step_names": [s.get("step", "?") for s in self._debug_steps],
            "formula_len": len(self._debug_steps[-1].get("result", {}).get("formula_compact", ""))
            if self._debug_steps else 0,
        }

    def get_debug_log(self) -> list[dict]:
        return self._debug_steps

    # ---- Utility ----

    @staticmethod
    def _safe_parse_json(raw: str) -> dict | None:
        """Parsing JSON robusto che gestisce markdown fence."""
        if not raw:
            return None
        # Rimuovi eventuali blocchi markdown ```json ... ```
        raw = raw.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Prova a estrarre primo { ... } valido
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            _logger.warning("Safe parse JSON fallito: %s...", raw[:100])
            return None


def _cond_to_compact(cond: str) -> str:
    """Converte condizione IR in operatore WinSarp compatto."""
    for op in ["!=", "#", ">=", ">U", "<=", "<U", ">", "<", "="]:
        pattern = r'\s*' + re.escape(op) + r'\s*'
        if re.search(pattern, cond):
            parts = re.split(pattern, cond, maxsplit=1)
            if len(parts) == 2:
                left, right = parts[0].strip(), parts[1].strip()
                op_map = {"=": "U", "#": "#", "!=": "#",
                          ">": ">", "<": "<",
                          ">=": ">U", ">U": ">U",
                          "<=": "<U", "<U": "<U"}
                op_ws = op_map.get(op, "U")
                right_ws = right
                if right.upper() in ("I", "Z"):
                    right_ws = right.upper()
                elif right.replace(".", "").replace("-", "").isdigit():
                    right_ws = f"'{right}'"
                else:
                    right_ws = f'"{right}"'
                if right_ws in ("0", "'0'", "Z"):
                    right_ws = "Z"
                return f"{left} {op_ws} {right_ws}"
    return cond


# ============================================================
# FUNZIONE PRINCIPALE per integrazione col FormulaBuilder
# ============================================================


def generate_with_cot(user_request: str, model_id: str | None = None) -> dict:
    """Genera formula WinSarp complessa con Chain-of-Thought.

    Args:
        user_request: Richiesta utente in linguaggio naturale
        model_id: ID modello LLM (None = default configurazione)

    Returns:
        Dict con:
        - formula: formula compatta WinSarp generata
        - ir_steps: IR steps intermedi
        - spiegazione: spiegazione della formula
        - success: True se generata con successo
        - error: messaggio errore se fallita
        - debug: log dei 4 step CoT
    """
    engine = ChainOfThoughtEngine(model_id=model_id)
    try:
        final = engine.run_pipeline(user_request)

        if not final.formula_compact and not final.ir_steps_completi:
            return {
                "formula": "",
                "ir_steps": [],
                "spiegazione": "Nessuna formula generata dalla pipeline CoT",
                "success": False,
                "error": "Pipeline CoT non ha prodotto output",
                "debug": engine.get_debug_log(),
            }

        return {
            "formula": final.formula_compact,
            "ir_steps": final.ir_steps_completi,
            "spiegazione": final.spiegazione,
            "success": True,
            "error": None,
            "debug": engine.get_debug_log(),
        }

    except Exception as e:
        _logger.error("CoT pipeline fallita: %s", e, exc_info=True)
        return {
            "formula": "",
            "ir_steps": [],
            "spiegazione": f"Errore pipeline CoT: {e}",
            "success": False,
            "error": str(e),
            "debug": getattr(engine, "_debug_steps", []),
        }
