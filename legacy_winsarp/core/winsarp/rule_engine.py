"""
rule_engine.py
Genera formule WinSarp da regole condizionali in linguaggio naturale.
Usa PARSER DETERMINISTICO (regex/pattern matching) invece di LLM.

Supporta due modalità:
  1. Regole su intervallo (pausa pranzo, durata minima/massima) — legacy
  2. Pattern formula completi (IG reset, turn recognition, FG split, ecc.) — nuova
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional

from legacy_winsarp.core.winsarp.formula_patterns import (
    PATTERNS,
    CHAINS,
    FormulaPattern,
    match_patterns,
    match_chain,
    fill_template,
    get_pattern,
)

_logger = logging.getLogger(__name__)

# ============================================================
# 1. DETECTION: che tipo di richiesta è?
# ============================================================

_RULE_KEYWORDS = ("se ", "allora", "altrimenti", "condizione",
                  "fino a ", "minuti", "minuto", "togli", "aggiungi",
                  "non va ", "va ", "conteggiato", "conteggia",
                  "da ignorare", "non conteggiare", "soglia",
                  "da togliere", "sottrarre", "detrarre")

_FORMULA_KEYWORDS = {
    "ig":           ["inizio giornata", "avvio", "azzeramento", "resetta"],
    "fg":           ["fine giornata", "chiusura", "finale", "fg"],
    "turno":        ["riconoscimento turno", "classificazione", "mattino", "pomeriggio", "notte",
                     "turnista", "determina turno"],
    "festivo":      ["festivo", "domenica", "sabato", "festività", "non goduta", "patrono"],
    "straordinario":["straordinario", "straord", "diurno", "notturno", "sa ", " sb", "sn ", "sf ",
                     "supplementare"],
    "maggiorazione":["maggiorazione", "premio turno", "indennità"],
    "causali":      ["causale", "esplodi", "slot", "501", "sa", "sb", "sn", "sf"],
    "assenze":      ["assenza", "assenze", "carenti", "mancanza"],
    "warning":      ["warning", "alert", "limite 250", "ore annuali"],
    "pausa":        ["pausa pranzo", "mensa", "pausa"],
    "conad":        ["conad", "gubbio", "arrotondamento entrate", "arrotondamento uscite"],
    "gugest":       ["gugest", "primo giro", "secondo giro", "settimanale"],
    "dirigenti":    ["dirigente", "dirigenti", "quadro", "quadri"],
    "chiamata":     ["chiamata", "a chiamata", "on call"],
    "arrotondamento":["arrotonda", "quarti d'ora", "arrotondamento"],
    "impiegati":    ["impiegato", "impiegati"],
}


def _is_rule_request(text: str) -> bool:
    """True se la richiesta contiene keyword di una regola condizionale."""
    low = text.lower()
    return any(kw in low for kw in _RULE_KEYWORDS)


def _is_formula_request(text: str) -> bool:
    """True se la richiesta riguarda una formula WinSarp generica."""
    low = text.lower()
    if _is_rule_request(text):
        return False
    for category, keywords in _FORMULA_KEYWORDS.items():
        if any(kw in low for kw in keywords):
            return True
    matched = match_patterns(text, top_k=1, min_score=3.0)
    return len(matched) > 0


def _classify_request(text: str) -> str:
    """Classifica il tipo di richiesta: rule / pattern / chain / unknown."""
    low = text.lower()
    if _is_rule_request(text):
        return "rule"
    # Match pattern specifici (min_score piu' alto per evitare falsi positivi)
    patterns = match_patterns(text, top_k=1, min_score=3.0)
    if patterns:
        return "pattern"
    # Match catene
    chains = match_chain(text, min_score=3)
    if chains:
        return "chain"
    # Match per categorie generiche
    for category, keywords in _FORMULA_KEYWORDS.items():
        if any(kw in low for kw in keywords):
            return category
    return "unknown"


# ============================================================
# 2. CAMPI — mappa da nomi a numeri
# ============================================================

CAMPI = {
    "uscita1": "271", "uscita 1": "271", "uscita_1": "271",
    "entrata1": "251", "entrata 1": "251", "entrata_1": "251",
    "entrata2": "252", "entrata 2": "252", "entrata_2": "252",
    "uscita2": "272", "uscita 2": "272", "uscita_2": "272",
    "entrata3": "253", "entrata 3": "253",
    "uscita3": "273", "uscita 3": "273",
    "straordinario": "4", "ore straordinarie": "4",
    "ordinario": "3", "ore ordinarie": "3",
    "previste": "1", "ore previste": "1",
    "notturne": "21", "ore notturne": "21",
    "lavorate": "3", "ore lavorate": "3",
    "assenza": "5", "assenze": "5",
    "n": "21", "maggiorazione notturna": "21",
    "sa": "907", "sb": "915", "sn": "909", "sf": "914",
}

CAMPO_ROLES: Dict[str, str] = {
    "1": "Ore previsionali",
    "3": "Ore ordinarie calcolate",
    "4": "Ore straordinarie calcolate",
    "5": "Ore assenza",
    "21": "Fascia notturna",
    "50": "Giorno settimana",
    "55": "Flag festivo",
    "58": "Tipo turno",
    "900": "Flag anti-loop / turno",
    "907": "Straordinario diurno SA",
    "909": "Straordinario notturno SN",
    "914": "Straordinario festivo SF",
    "915": "Straordinario seconda fascia SB",
}


# ============================================================
# 3. LEGACY: parsing regole su intervallo (pausa pranzo)
# ============================================================

def _n(val: str) -> float:
    """Converte '00.15' o '15' in float 15.0."""
    v = val.replace("'", "").strip()
    if "." in v:
        parts = v.split(".")
        return float(parts[0]) * 60 + float(parts[1])
    return float(v)


def _parse_soglia(text: str) -> dict | None:
    """Cerca pattern: 'fino a N minuti non va conteggiato' oppure 'se tra N e M vanno tolti K minuti'."""
    text_low = text.lower()
    m_soglia = re.search(r"(?:fino\s*a|meno\s*di|inferiore\s*a|sotto\s*i)\s*(\d+)\s*minut", text_low)
    if not m_soglia:
        m_soglia = re.search(r"(\d+)\s*minut[oi]?\s*da\s*ignorare", text_low)
    if not m_soglia:
        m_soglia = re.search(r"durata\s*<\s*(\d+)\s*minut", text_low)

    soglia_min = None
    if m_soglia:
        soglia_min = int(m_soglia.group(1))

    m_togli = re.search(r"(?:tra|da)\s*(\d+)\s*(?:minut[oi])?\s*(?:a|e)\s*(\d+)\s*(?:minut[oi])?[,\s]*(?:va(?:nno)?\s*)?(?:t[oi]?ogli[ere]?|tolt[oi]|sottra[oi]|sottrarre|detrarre|di\s*pi[ù'])\s+(\d+)\s*(?:minut[oi])?", text_low)
    if not m_togli:
        m_togli = re.search(r"da\s*(\d+)\s*(?:minut[oi])?\s*a\s*(\d+)\s*minut", text_low)

    soglia_max = None
    da_togliere = None
    if m_togli:
        soglia_max = int(m_togli.group(2))
        if len(m_togli.groups()) >= 3 and m_togli.group(3):
            da_togliere = int(m_togli.group(3))
        else:
            da_togliere = soglia_max

    if soglia_min is not None or soglia_max is not None:
        return {"soglia_min": soglia_min, "soglia_max": soglia_max, "da_togliere": da_togliere}
    return None


def _parse_intervallo(text: str) -> dict | None:
    """Cerca pattern: 'intervallo tra X e Y', 'uscita 1 e entrata 2'."""
    text_low = text.lower()
    m_campi = re.search(r"(?:intervallo\s*)?tra\s*(?:l['\']?\s*)?"
                        r"(?P<c1>[\w\s]+?)\s*e\s*(?:l['\']?\s*)?(?P<c2>[\w\s]+?)"
                        r"(?:\s*|$)", text_low, re.IGNORECASE)
    if m_campi:
        c1_name = m_campi.group("c1").strip().lower().replace("l'", "").strip()
        c2_name = m_campi.group("c2").strip().lower().replace("l'", "").strip()
        c1 = CAMPI.get(c1_name)
        c2 = CAMPI.get(c2_name)
        if c1 and c2:
            return {"entrata": c2, "uscita": c1}

    if "pausa pranzo" in text_low or "pausa" in text_low:
        return {"entrata": "252", "uscita": "271"}
    if "uscita 1" in text_low or "uscita1" in text_low:
        if "entrata 2" in text_low or "entrata2" in text_low or "seconda entrata" in text_low:
            return {"entrata": "252", "uscita": "271"}
    if "uscita" in text_low and "entrata" in text_low:
        return {"entrata": "252", "uscita": "271"}
    if "durata" in text_low or "intervallo" in text_low:
        return {"entrata": "252", "uscita": "271"}
    return None


def _parse_rule(text: str) -> dict | None:
    """Parser per regole su intervallo."""
    intervallo = _parse_intervallo(text)
    soglia = _parse_soglia(text)

    if not soglia and not intervallo:
        return None

    cond = {}
    if intervallo:
        cond["entrata"] = intervallo.get("entrata", "252")
        cond["uscita"] = intervallo.get("uscita", "271")
    else:
        cond["entrata"] = "252"
        cond["uscita"] = "271"

    if soglia:
        cond["soglia_min"] = soglia.get("soglia_min")
        cond["soglia_max"] = soglia.get("soglia_max")
        cond["da_togliere"] = soglia.get("da_togliere")
    else:
        cond["soglia_min"] = 0
        cond["soglia_max"] = None
        cond["da_togliere"] = None

    return cond


def _generate_rule_formula(parsed: dict) -> str:
    """Genera formula WinSarp compatta da regola su intervallo."""
    entrata = parsed["entrata"]
    uscita = parsed["uscita"]
    durata = f"{uscita}S{entrata}"
    soglia_min = parsed.get("soglia_min")
    soglia_max = parsed.get("soglia_max")
    da_togliere = parsed.get("da_togliere")

    parts = []
    parts.append(f"(800={durata})")
    parts.append("800<Z((K800A'24.00'))")

    if soglia_min is not None and soglia_min > 0:
        min_str = f"'00.{soglia_min:02d}'"
        parts.append(f"800<U{min_str}((!{entrata}!{uscita})VF)")

    if soglia_max is not None and da_togliere is not None:
        max_str = f"'00.{soglia_max:02d}'"
        togli_str = f"'00.{da_togliere:02d}'"
        if soglia_min is not None:
            parts.append(f"800>{min_str}E800<U{max_str}(({entrata}={uscita}A{togli_str})VF)")
        else:
            parts.append(f"800<U{max_str}(({entrata}={uscita}A{togli_str})VF)")

    parts.append("VF")
    return ";".join(parts)


# ============================================================
# 4. PATTERN-BASED GENERATION (nuovo)
# ============================================================

def _extract_params(text: str, pattern: FormulaPattern) -> Dict[str, str]:
    """Estrae parametri da una richiesta utente per un dato pattern.

    Usa regex per trovare valori specifici nella richiesta.
    """
    params: Dict[str, str] = {}
    low = text.lower()

    # Parametri temporali generici: hh.mm
    time_matches = re.findall(r"(\d{1,2})[\.:](\d{2})", text)
    time_values = [f"{h}.{m}" for h, m in time_matches]

    time_idx = 0
    for slot, meta in pattern.parameters.items():
        if meta["type"] == "time":
            # Cerca 'dalle X alle Y' o 'tra X e Y'
            time_range = re.search(r"(?:dalle?\s*)?(\d{1,2}[\.:]\d{2})\s*(?:alle?\s*|a\s*|[-–])\s*(\d{1,2}[\.:]\d{2})", text)
            if time_range:
                if "start" in slot:
                    params[slot] = time_range.group(1).replace(":", ".")
                elif "end" in slot:
                    params[slot] = time_range.group(2).replace(":", ".")
            elif time_idx < len(time_values):
                params[slot] = time_values[time_idx].replace(":", ".")
                time_idx += 1
            else:
                params[slot] = meta["default"]

        elif meta["type"] == "duration":
            dur_match = re.search(r"(\d{1,2})[\.:](\d{2})\s*(?:minut[oi]|ore|or[ae])?", text)
            if dur_match:
                params[slot] = f"{dur_match.group(1)}.{dur_match.group(2)}"
            else:
                params[slot] = meta["default"]

        elif meta["type"] == "bool":
            params[slot] = meta["default"]

        elif meta["type"] == "string":
            # Cerca etichette come MATT/POME/NOTT
            label_match = re.search(r"\b(MATT|POME|NOTT|RIPO|OPE|CHIA)\b", text, re.IGNORECASE)
            if label_match and slot.endswith("_label"):
                # Associa al turno corretto in base al contesto
                if "mattino" in slot and "mattino" in low:
                    params[slot] = label_match.group(1).upper()
                elif "pomeriggio" in slot and ("pomeriggio" in low or "pome" in low):
                    params[slot] = label_match.group(1).upper()
                elif "notte" in slot and ("notte" in low or "nott" in low):
                    params[slot] = label_match.group(1).upper()
                else:
                    params[slot] = meta["default"]
            else:
                params[slot] = meta["default"]

        else:
            params[slot] = meta["default"]

    return params


def _generate_pattern_formula(pattern: FormulaPattern, params: Dict[str, str]) -> dict:
    """Genera IR steps da un pattern e converte in WinSarp compatto."""
    from legacy_winsarp.core.formula_builder import WinSarpBuilder

    # Riempi il template con i parametri
    ir_steps = fill_template(pattern, params)

    # Converti in compatto
    builder = WinSarpBuilder()
    formula = builder.build_compact(ir_steps)

    return {
        "formula": formula,
        "ir_steps": ir_steps,
        "pattern_id": pattern.id,
        "phase": pattern.phase,
    }


def _generate_chain_formula(chain_id: str, params: Dict[str, str]) -> dict:
    """Genera una catena completa di formule."""
    chain = CHAINS.get(chain_id)
    if not chain:
        return {"success": False, "error": f"Chain {chain_id} not found"}

    all_formulas = []
    for pid in chain.patterns:
        pat = get_pattern(pid)
        if pat:
            result = _generate_pattern_formula(pat, params)
            all_formulas.append(result)

    return {
        "success": True,
        "chain": chain_id,
        "formulas": all_formulas,
        "formula_count": len(all_formulas),
    }


# ============================================================
# 5. MAIN ENTRY POINT
# ============================================================

def generate(user_request: str, model: str = "", timeout: int = 30) -> dict:
    """Genera formula WinSarp da richiesta utente usando parser deterministico.

    Supporta:
    - Regole su intervallo (pausa pranzo, soglie durata)
    - Pattern formula (IG reset, FG split, causali, ecc.)
    - Catene complete
    """
    start = time.time()
    low = user_request.lower()

    # --- Step 1: classifica la richiesta ---
    req_type = _classify_request(user_request)
    _logger.info("RuleEngine: request '%s' classified as '%s'", user_request[:60], req_type)

    # --- Step 2: regola su intervallo ---
    if req_type == "rule":
        parsed = _parse_rule(user_request)
        if parsed:
            formula = _generate_rule_formula(parsed)
            elapsed = time.time() - start
            return {
                "formula": formula,
                "source": "rule_engine_deterministic",
                "success": True,
                "error": None,
                "raw": parsed,
                "explanation": f"Rule-based formula generated in {elapsed:.0f}s via deterministic parser",
            }
        return {"success": False, "source": "parse_failed",
                "error": "Cannot understand the rule. Use: 'se intervallo tra X e Y, fino a N min ignora, se tra N e M togli K'"}

    # --- Step 3: pattern formula ---
    matched = match_patterns(user_request, top_k=1, min_score=3.0)
    if matched:
        pattern = matched[0]
        params = _extract_params(user_request, pattern)
        result = _generate_pattern_formula(pattern, params)
        elapsed = time.time() - start
        result["success"] = True
        result["source"] = "rule_engine_pattern"
        result["explanation"] = f"Pattern '{pattern.id}' generated in {elapsed:.0f}s"
        result["raw"] = {"pattern_id": pattern.id, "params": params}
        return result

    # --- Step 4: catena formula ---
    chains = match_chain(user_request, min_score=3)
    if chains:
        chain = chains[0]
        params = {}
        result = _generate_chain_formula(chain.id, params)
        elapsed = time.time() - start
        result["source"] = "rule_engine_chain"
        result["explanation"] = f"Chain '{chain.id}' generated in {elapsed:.0f}s"
        return result

    return {"success": False, "source": "not_matched",
            "error": "Cannot match any formula pattern. Describe what the formula should do (e.g., 'azzeramento inizio giornata', 'riconoscimento turno mattino', 'gestione straordinario festivo')."}


def generate_pattern(pattern_id: str, params: Optional[Dict[str, str]] = None) -> dict:
    """Genera una formula da un pattern specifico."""
    pattern = get_pattern(pattern_id)
    if not pattern:
        return {"success": False, "error": f"Pattern '{pattern_id}' not found"}
    params = params or {}
    result = _generate_pattern_formula(pattern, params)
    result["success"] = True
    result["source"] = "rule_engine_direct_pattern"
    return result


def generate_chain(chain_id: str) -> dict:
    """Genera una catena completa di formule."""
    return _generate_chain_formula(chain_id, {})


def list_patterns(phase: Optional[str] = None, tag: Optional[str] = None) -> List[dict]:
    """Elenca i pattern disponibili, opzionalmente filtrati."""
    patterns = list(PATTERNS.values())
    if phase:
        patterns = [p for p in patterns if p.phase == phase]
    if tag:
        patterns = [p for p in patterns if tag in p.tags]
    return [
        {
            "id": p.id,
            "name": p.name,
            "phase": p.phase,
            "description": p.description,
            "tags": list(p.tags),
            "parameters": list(p.parameters.keys()),
        }
        for p in patterns
    ]
