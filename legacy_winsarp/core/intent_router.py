"""
intent_router.py
Router intelligente che usa l'LLM per comprendere la richiesta utente
e indirizzarla al componente giusto della pipeline WinSarp.

Obiettivi:
1. Comprendere deep la richiesta (non solo keyword matching)
2. Decidere se: cercare nel catalogo / generare nuova formula / chiedere chiarimenti
3. Se cercare: fare RAG retrieval contestuale
4. Se generare: usare l'LLM potente con contesto completo
5. Se ambiguo: generare domande di chiarimento mirate

Flusso:
  Richiesta utente
    ↓
  1. Intent Router (LLM) — classifica in: retrieval | generation | clarification
    ↓
  2a. Retrieval → RAG engine (cerca formula esistente)
  2b. Generation → LLM potente (CoT + SpecificaFormula)
  2c. Clarification → domande mirate
    ↓
  3. Validazione + certificazione finale
"""

import json
import logging
import re

from core.ai.utils import call_llm
from legacy_winsarp.core.winsarp.glossary import expand_query, FIELD_DESCRIPTIONS

_logger = logging.getLogger(__name__)


# ============================================================
# PROMPT DI CLASSIFICAZIONE INTELLIGENTE
# ============================================================

ROUTER_PROMPT = """Sei un analista WinSarp esperto. Il tuo compito è ANALIZZARE la richiesta
dell'utente e CLASSIFICARLA nel modo più appropriato tra queste opzioni:

1. "retrieval" — L'utente chiede una formula WinSarp che già esiste nel catalogo.
   Segnali: menziona numeri formula (es. "formula 200", "R120"), chiede "mostra", "cerca",
   "dammi la formula", "cosa fa la formula" oppure descrive un caso standard ben noto
   (es. riconoscimento turno, arrotondamento, calcolo presenza).

2. "generation" — L'utente chiede di CREARE una nuova formula WinSarp che NON esiste
   nel catalogo. Segnali: "crea", "genera", "scrivi", "costruisci", "fai una formula che",
   descrive logiche personalizzate con condizioni multiple, soglie, calcoli specifici.

3. "clarification" — La richiesta è troppo vaga o ambigua per essere classificata.
   Segnali: richieste generiche senza campi, senza operazioni specifiche, senza contesto.

OUTPUT: Rispondi ESCLUSIVAMENTE con un JSON valido in questo formato:
{{
  "action": "retrieval" | "generation" | "clarification",
  "confidence": 0.0-1.0,
  "campi_coinvolti": [lista numeri campi WinSarp menzionati],
  "formula_riferimento": numero formula se menzionata (null se non),
  "descrizione_richiesta": "breve descrizione di cosa vuole l'utente",
  "parole_chiave": ["parole", "chiave", "estratte"],
  "motivazione": "perché hai scelto questa classificazione"
}}

REGOLE:
- "retrieval" se l'utente menziona un numero formula o descrive un caso standard
- "generation" se descrive logiche nuove, condizioni personalizzate, calcoli specifici
- Se non sei sicuro al 100%, usa confidence < 1.0
- campi_coinvolti: estrai SEMPRE tutti i numeri che sembrano campi WinSarp
- formula_riferimento: se l'utente dice "formula 130" o "R130", metti 130

Richiesta: {user_request}

Rispondi SOLO con il JSON.
"""


# ============================================================
# PROMPT DI GENERAZIONE FORMULE (migliorato)
# ============================================================

GENERATION_PROMPT = """Sei un ingegnere WinSarp senior specializzato nella CREAZIONE di formule
WinSarp complesse e funzionanti. La tua missione è:

1. COMPRENDERE a fondo cosa vuole l'utente
2. CERCARE nel catalogo formule esistenti se esiste già qualcosa di simile
3. SE ESISTE: indica di usare quella formula (con le opportune modifiche)
4. SE NON ESISTE: progetta e genera una formula WinSarp nuova e funzionante
5. SPIEGARE sempre cosa fa la formula e perché è stata progettata così

CONTESTO DAL CATALOGO:
{template_section}

RICHIESTA UTENTE:
"{user_request}"

--- SPECIFICA FORMULA JSON ---
Genera ESCLUSIVAMENTE il JSON con questa struttura:
{{
  "scopo_formula": "descrizione chiara dello scopo",
  "fase_esecuzione": "IG"|"DG"|"FG"|"SUB",
  "logica_passo_passo": "spiegazione dettagliata passo passo della logica",
  "campi_input": [numeri campi letti],
  "campi_output": [numeri campi scritti],
  "campi_state_flag": [campi flag tipo 900],
  "causali_richieste": ["sigla1", "sigla2"],
  "flag_attivazione": "I"|"Z"|null,
  "soglie_condizionali": [numeri soglia],
  "validita_temporale": null,
  "valori_output": {{"campo": "valore"}},
  "condizioni_azioni": [
    {{"condizione": "70 > 170", "azioni": {{"99": "'50'"}}}},
    {{"condizione": "70 > 400", "azioni": {{"85": "'NOTT'"}}}},
    {{"condizione": null, "azioni": {{}}}}
  ],
  "spiegazione_linguaggio_naturale": "spiegazione chiara per l'utente",
  "note_implementazione": "note tecniche per l'implementatore"
}}

REGOLE CRUCIALI:
- condizioni_azioni: usa QUESTO campo per TUTTE le condizioni (IF/THEN/ELSE)
- Ogni condizione ha 'condizione' (stringa con operatore WinSarp o null per else) e 'azioni' (dict)
- 'condizione' DEVE includere SEMPRE il numero del campo (es. '70 > 170', NON '> 170')
- valori in 'azioni': costanti tra apici singoli. Nel JSON vanno doppiamente quotati
- campi protetti da NON scrivere: 70, 900, 1-5, 58, 100, 111, 112, 141, 142
- Cerca SEMPRE prima nel catalogo se esiste una formula simile
- Se trovi una formula esistente, citala come punto di partenza

Rispondi SOLO con il JSON valido.
"""


# ============================================================
# PROMPT DI RICERCA NEL CATALOGO (RAG potenziato)
# ============================================================

RETRIEVAL_PROMPT = """Sei un esperto del catalogo formule WinSarp. Il tuo compito è:
1. Analizzare la richiesta dell'utente
2. Identificare QUALI formule del catalogo sono rilevanti
3. Estrarre il codice esatto di quelle formule
4. Spiegare perché sono state scelte

FORMULE DISPONIBILI NEL CATALOGO:
{formule_disponibili}

RICHIESTA: "{user_request}"

Rispondi SOLO con JSON:
{{
  "formule_trovate": [
    {{
      "id": numero_formula,
      "nome": "nome formula",
      "pertinenza": 0.0-1.0,
      "motivo": "perché questa formula è pertinente",
      "modifiche_necessarie": "cambiamenti da fare se serve"
    }}
  ],
  "miglior_formula": {{
    "id": numero,
    "codice": "codice WinSarp esatto dalla formula",
    "spiegazione": "spiegazione in italiano"
  }},
  "serve_generazione": true|false,
  "motivazione": "spiegazione della scelta"
}}
"""


# ============================================================
# ROUTER INTELLIGENTE
# ============================================================


class IntentRouter:
    """Router intelligente che usa l'LLM per capire la richiesta e indirizzarla.

    Sostituisce il keyword matching rigido con comprensione semantica reale.
    Usa l'LLM (OpenRouter se configurato) per classificare la richiesta.
    """

    def __init__(self, model_id: str | None = None, retriever=None):
        self.model_id = model_id
        self._retriever = retriever

    def classify(self, user_request: str) -> dict:
        """Classifica la richiesta usando l'LLM.

        Returns:
            Dict con action, confidence, campi_coinvolti, etc.
        """
        prompt = ROUTER_PROMPT.replace("{user_request}", user_request)

        try:
            raw = call_llm(
                prompt=prompt,
                model_id=self.model_id,
                temp=0.0,
                json_mode=False,
                timeout=30,
            )
            result = self._parse_json(raw)
            if result and "action" in result:
                _logger.info(
                    "Router: %s (conf=%.2f) — %s",
                    result["action"], result.get("confidence", 0),
                    result.get("motivazione", "")[:80],
                )
                return result
        except Exception as e:
            _logger.warning("Router classify fallito, fallback keyword: %s", e)

        # Fallback: keyword matching semplice
        return self._keyword_fallback(user_request)

    def _keyword_fallback(self, text: str) -> dict:
        """Fallback keyword-based quando l'LLM non è disponibile."""
        low = text.lower()

        # Reset puro
        reset_words = ("azzera", "resetta", "azzeramento")
        action_words = ("calcola", "riconoscimento", "straordinario", "somma")
        has_reset = any(w in low for w in reset_words)
        has_action = any(w in low for w in action_words)
        if has_reset and not has_action:
            fields = [int(f) for f in re.findall(r'\b\d{1,4}\b', text) if 1 <= int(f) <= 999]
            return {
                "action": "retrieval",
                "confidence": 0.6,
                "campi_coinvolti": fields or [800, 801],
                "formula_riferimento": None,
                "descrizione_richiesta": "Reset campi",
                "parole_chiave": ["reset"],
                "motivazione": "Fallback: reset puro rilevato da keyword",
            }

        # Numeri formula
        m = re.search(r'(?:formula|R)\s*(\d{2,4})', text, re.IGNORECASE)
        if m:
            return {
                "action": "retrieval",
                "confidence": 0.7,
                "campi_coinvolti": [],
                "formula_riferimento": int(m.group(1)),
                "descrizione_richiesta": f"Richiesta formula #{m.group(1)}",
                "parole_chiave": [f"formula {m.group(1)}"],
                "motivazione": "Fallback: riferimento formula numerico",
            }

        # Crea/genera
        if any(w in low for w in ("crea", "genera", "costruisci", "fai una formula")):
            fields = [int(f) for f in re.findall(r'\b\d{1,4}\b', text) if 1 <= int(f) <= 999]
            return {
                "action": "generation",
                "confidence": 0.5,
                "campi_coinvolti": fields,
                "formula_riferimento": None,
                "descrizione_richiesta": "Generazione richiesta",
                "parole_chiave": ["crea", "genera"],
                "motivazione": "Fallback: richiesta creazione rilevata",
            }

        return {
            "action": "clarification",
            "confidence": 0.3,
            "campi_coinvolti": [],
            "formula_riferimento": None,
            "descrizione_richiesta": "Richiesta non classificata",
            "parole_chiave": [],
            "motivazione": "Fallback: richiesta ambigua, nessuna keyword riconosciuta",
        }

    @staticmethod
    def _formula_to_dict(f: object) -> dict:
        """Estrae i campi da FormulaEntry o dict in modo uniforme."""
        if hasattr(f, "codice"):
            return {
                "id": str(f.codice),
                "name": getattr(f, "descrizione", "") or "",
                "scopo": getattr(f, "scopo", "") or "",
                "code": getattr(f, "formula", "") or "",
            }
        if isinstance(f, dict):
            return {
                "id": str(f.get("id", f.get("codice", "?"))),
                "name": f.get("name", f.get("descrizione", "Sconosciuta")),
                "scopo": f.get("scopo", "") or "",
                "code": f.get("code", f.get("formula", "")) or "",
            }
        return {"id": "?", "name": "Sconosciuta", "scopo": "", "code": ""}

    def retrieve_from_catalog(self, user_request: str, formule_disponibili: list) -> dict:
        """Cerca nel catalogo usando il WorkbookRetriever (keyword matching veloce).

        Args:
            user_request: Richiesta utente
            formule_disponibili: Lista di FormulaEntry o dict con id/name/scopo/code

        Returns:
            Dict con formule_trovate, miglior_formula, serve_generazione
        """
        if not formule_disponibili:
            return {
                "formule_trovate": [],
                "miglior_formula": None,
                "serve_generazione": True,
                "motivazione": "Nessuna formula disponibile nel catalogo",
            }

        # Usa il retriever per keyword matching veloce (no LLM)
        if self._retriever is not None:
            try:
                results = self._retriever.search(user_request, top_k=3)
                if results:
                    formule_trovate = []
                    miglior_formula = None
                    for entry, score in results:
                        fdict = self._formula_to_dict(entry)
                        formule_trovate.append({
                            "id": fdict["id"],
                            "nome": fdict["name"],
                            "pertinenza": score,
                            "motivo": f"Match semantico (score={score:.2f})",
                        })
                        if miglior_formula is None:
                            miglior_formula = {
                                "id": fdict["id"],
                                "codice": entry.formula,
                                "spiegazione": entry.scopo[:500],
                            }
                    return {
                        "formule_trovate": formule_trovate,
                        "miglior_formula": miglior_formula,
                        "serve_generazione": False,
                        "motivazione": f"Trovate {len(formule_trovate)} formule per keyword matching",
                    }
            except Exception as e:
                _logger.warning("Retriever search fallito: %s", e)

        # Fallback: cerca per numero formula (da user_request)
        m = re.search(r'\b(\d{2,4})\b', user_request)
        if m:
            fid = int(m.group(1))
            for f_raw in formule_disponibili:
                f = self._formula_to_dict(f_raw)
                if f["id"] == str(fid):
                    return {
                        "formule_trovate": [{"id": fid, "pertinenza": 1.0, "motivo": "Match esatto ID"}],
                        "miglior_formula": {"id": fid, "codice": f["code"], "spiegazione": f["scopo"]},
                        "serve_generazione": False,
                        "motivazione": "Match esatto per ID formula",
                    }

        return {
            "formule_trovate": [],
            "miglior_formula": None,
            "serve_generazione": True,
            "motivazione": "Nessuna formula corrispondente nel catalogo",
        }

    def generate_formula(self, user_request: str, template_section: str = "") -> dict:
        """Genera una SpecificaFormula JSON usando l'LLM potente."""
        prompt = GENERATION_PROMPT.replace("{user_request}", user_request)
        prompt = prompt.replace("{template_section}", template_section)

        last_error = "Errore generazione sconosciuto"
        try:
            raw = call_llm(
                prompt=prompt,
                model_id=self.model_id,
                temp=0.1,
                json_mode=False,
                timeout=120,
            )
            result = self._parse_json(raw)
            if result and "scopo_formula" in result:
                return result
        except Exception as exc:
            _logger.error("Generation fallita: %s", exc)
            last_error = str(exc)

        return {
            "scopo_formula": "Errore generazione",
            "error": last_error,
            "condizioni_azioni": [],
        }

    def generate_clarification(self, user_request: str) -> list[dict]:
        """Genera domande di chiarimento mirate basate sulla richiesta."""
        low = user_request.lower()
        questions = []

        # Analisi euristica di cosa manca
        has_fields = bool(re.findall(r'\b\d{2,4}\b', user_request))
        has_operation = any(w in low for w in [
            "imposta", "set", "azzera", "calcola", "somma", "arrotonda",
            "riconoscimento", "determina", "gestisci", "crea", "genera",
        ])
        has_conditional = any(w in low for w in ["se ", "if ", "condizione", "altrimenti"])
        has_formula_ref = bool(re.search(r'(?:formula|R)\s*\d+', low))

        if not has_operation and not has_fields and not has_formula_ref:
            questions.append({
                "domanda": "Cosa vuoi ottenere? Descrivi l'operazione (es. azzeramento, calcolo ore, riconoscimento turno, arrotondamento)",
                "tipo": "operazione",
                "suggerimenti": ["riconoscimento turno 251/271", "calcolo ore presenza in 800",
                               "arrotondamento campo 3 ai quarti", "straordinario notturno con causale SN"],
            })

        if has_operation and not has_fields and not has_formula_ref:
            questions.append({
                "domanda": "Su quali campi WinSarp vuoi applicare questa operazione? (es. 251=entrata, 271=uscita, 800=appoggio, 900=flag)",
                "tipo": "campi",
                "suggerimenti": ["251 e 271 per entrata/uscita", "800 per risultato", "900 per flag turno"],
            })

        if has_operation and has_fields and not has_conditional:
            questions.append({
                "domanda": "Ci sono condizioni? (es. 'se campo vuoto', 'se maggiore di soglia', 'altrimenti...')",
                "tipo": "condizioni",
                "suggerimenti": ["se 251 vuoto allora flag=2", "se 800 > 170 allora bonus=50", "altrimenti 900=0"],
            })

        if not questions:
            questions.append({
                "domanda": "Cosa deve fare la formula? Descrivi: quali campi, che operazioni, e se ci sono condizioni.",
                "tipo": "generale",
                "suggerimenti": [],
            })

        return questions

    # ---- Utility ----

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        """Parsing JSON robusto con supporto markdown fence."""
        if not raw:
            return None
        raw = raw.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
            return None


# ============================================================
# QUEST FACTORY — arricchisce il contesto per l'LLM
# ============================================================


class QueryEnricher:
    """Arricchisce la richiesta utente con contesto dal dominio WinSarp.

    Usa il business_glossary per espandere i concetti di business
    in riferimenti tecnici WinSarp (campi, formule, causali).
    """

    PATTERN_EXAMPLES = """
PATTERN WINSARP COMUNI:
1. Riconoscimento turno: (!900)251UZE271UZ((900='2')VF(900='1')(900=271S251)VF
   Se entrata E uscita vuote -> flag=2 (non presente). Altrimenti flag=1 e calcola ore.

2. Calcolo presenza CAMPO70: (!71!72!73!74!75!76!77!78)(71=251)(72=271)(70='2')(campo=73)
   Carica 71=entrata, 72=uscita, CAMPO70 2 fa differenza in 73, copia in campo.

3. Arrotondamento quarti: campoUZ(VF(!800)(71=campo)(70='3')(campo=72)73<'15.00'(VF...
   Se campo zero -> VF. Altrimenti arrotonda ai quarti d'ora.

4. Condizionale IF/THEN/ELSE: condizione ((azioni_vere)VF;azioni_false
   condizione U valor((azioni_se_vero)VF;azioni_se_falso

5. Catena/P chiamate: P2109 per festività, P2122 per intervallo, P2123 per arrotondamento
"""

    def enrich(self, user_request: str) -> str:
        """Arricchisce la richiesta con contesto del dominio usando il glossario."""
        context_parts = [self.PATTERN_EXAMPLES]

        # Usa il glossario per espandere la query
        glossary = expand_query(user_request)

        if glossary["context_text"]:
            context_parts.append("\n" + glossary["context_text"])

        # Se ci sono campi numerici raw, aggiungi descrizioni dal glossario
        mentioned_fields = set()
        for num in re.findall(r'\b(\d{2,4})\b', user_request):
            n = int(num)
            if n in FIELD_DESCRIPTIONS:
                mentioned_fields.add(n)
        for k in re.findall(r'(K\d{3,4})\b', user_request, re.IGNORECASE):
            mentioned_fields.add(k)

        if mentioned_fields:
            context_parts.append("\nCAMPI RICONOSCIUTI NELLA RICHIESTA:")
            for f in sorted(mentioned_fields, key=lambda x: str(x)):
                desc = FIELD_DESCRIPTIONS.get(f, "")
                if desc:
                    context_parts.append(f"  {f}: {desc}")

        return "\n".join(context_parts)


# ============================================================
# FUNZIONE PRINCIPALE
# ============================================================


def _search_documentazione(user_request: str) -> str:
    """Cerca nella documentazione WinSarp (PDF manuale + formule) per
    arricchire il contesto quando il router ha confidenza bassa.

    Restituisce un testo di contesto aggiuntivo, o stringa vuota se
    la ricerca non trova nulla di pertinente.
    """
    from config import cfg
    try:
        from legacy_winsarp.core.rag_engine import get_index
        index = get_index("WinSarp", cfg.DEFAULT_MODEL_ID, cfg.DOCS_DIR, cfg.CHROMA_DIR, cfg.HASH_FILE)
        if index is None:
            return ""
        retriever = index.as_retriever(similarity_top_k=3)
        nodes = retriever.retrieve(user_request)
        if not nodes:
            return ""
        # Filtra solo chunk con score sufficiente
        soglia = cfg.SCORE_THRESHOLD_LOW
        utili = [n for n in nodes if n.score is not None and n.score >= soglia]
        if not utili:
            # Se nessuno supera la soglia, prendi i migliori 2 comunque
            utili = nodes[:2]
        parti = []
        for n in utili:
            testo = n.node.text.strip() if hasattr(n.node, 'text') else str(n.node)
            if len(testo) > 500:
                testo = testo[:500] + "..."
            parti.append(f"[Score {n.score:.2f}] {testo}")
        if parti:
            _logger.info("Documentazione trovata: %d chunk pertinenti", len(parti))
            return "\n\n".join(parti)
    except Exception as e:
        _logger.debug("Ricerca documentazione fallita: %s", e)
    return ""


def route_and_process(
    user_request: str,
    model_id: str | None = None,
    catalog_formulas: list[dict] | None = None,
    retriever=None,
) -> dict:
    """Funzione principale: router + processo.

    1. Classifica richiesta (LLM)
    2. retrieval → cerca nel catalogo
    3. generation → genera nuova formula
    4. clarification → domande

    Se la confidenza della classificazione è bassa (< 0.5), prova a
    cercare nella documentazione WinSarp (PDF manuale + formule) per
    arricchire il contesto.

    Args:
        user_request: Richiesta utente
        model_id: Modello LLM
        catalog_formulas: Lista formule catalogo per retrieval
        retriever: WorkbookRetriever opzionale

    Returns:
        Dict con risultato elaborato
    """
    router = IntentRouter(model_id=model_id, retriever=retriever)
    enricher = QueryEnricher()

    # Step 0: Espandi query con il glossario semantico
    glossary = expand_query(user_request)
    enriched_request = glossary.get("expanded_query", user_request)
    if glossary["context_text"]:
        _logger.info("Glossario: %d concetti, %d campi, %d formule, %d causali",
                      len(glossary["matched_concepts"]),
                      len(glossary["fields"]),
                      len(glossary["formulas"]),
                      len(glossary["causali"]))

    # Step 1: Classifica (usa la query arricchita dal glossario)
    classification = router.classify(enriched_request)
    action = classification.get("action", "clarification")
    confidence = classification.get("confidence", 0.0)

    _logger.info("Router: action=%s confidence=%.2f", action, confidence)

    # Step 1b: Se confidenza bassa, cerca nella documentazione per arricchire
    contesto_doc = ""
    if confidence < 0.5:
        _logger.info("Confidenza bassa (%.2f), cerco nella documentazione WinSarp...", confidence)
        contesto_doc = _search_documentazione(user_request)
        if contesto_doc:
            _logger.info("Documentazione trovata, arricchisco il contesto")
            # Riclassifica con contesto arricchito
            enriched_request = (
                f"{user_request}\n\nCONTESTO DA DOCUMENTAZIONE:\n{contesto_doc}"
            )
            classification2 = router.classify(enriched_request)
            action2 = classification2.get("action", action)
            confidence2 = classification2.get("confidence", 0.0)
            # Usa la nuova classificazione solo se migliora la confidenza
            if confidence2 > confidence + 0.1:
                _logger.info("Riclassificazione: action=%s confidence=%.2f", action2, confidence2)
                action = action2
                confidence = confidence2
                classification = classification2

    # Step 2: Arricchisci contesto
    context = enricher.enrich(user_request)
    if contesto_doc:
        context = f"{context}\n\nDOCUMENTAZIONE CORRELATA:\n{contesto_doc}"

    # Step 3: Esegui azione
    if action == "retrieval":
        result = router.retrieve_from_catalog(user_request, catalog_formulas or [])
        return {
            "action": "retrieval",
            "confidence": confidence,
            "formule_trovate": result.get("formule_trovate", []),
            "miglior_formula": result.get("miglior_formula"),
            "serve_generazione": result.get("serve_generazione", True),
            "motivazione": result.get("motivazione", ""),
            "user_request": user_request,
        }

    elif action == "generation":
        prompt_context = context
        if catalog_formulas:
            similar = router.retrieve_from_catalog(user_request, catalog_formulas)
            if similar.get("miglior_formula"):
                prompt_context += (
                    f"\n\nFORMULA SIMILE TROVATA IN CATALOGO:\n"
                    f"#{similar['miglior_formula']['id']}: {similar['miglior_formula']['codice']}\n"
                )

        spec = router.generate_formula(user_request, template_section=prompt_context)
        return {
            "action": "generation",
            "confidence": confidence,
            "specifica_formula": spec,
            "user_request": user_request,
            "context": prompt_context,
        }

    else:  # clarification
        questions = router.generate_clarification(user_request)
        return {
            "action": "clarification",
            "confidence": confidence,
            "domande": questions,
            "user_request": user_request,
        }
