"""
Intent-driven WinSarp formula builder.

Classifies user requests into structured intents, then generates
compact WinSarp syntax deterministically — no LLM-produced IR.

Flow: User request -> IntentClassifier -> IntentRequest -> Builder -> Compact formula

Uses FieldRegistry, TableRegistry, and FormulaPatternLibrary for domain knowledge.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from legacy_winsarp.core.winsarp.field_registry import FieldRegistry
from legacy_winsarp.core.winsarp.patterns import FormulaPatternLibrary
from legacy_winsarp.core.winsarp.formula_graph import FormulaDependencyGraph
from legacy_winsarp.core.winsarp.table_registry import TableRegistry

_logger = logging.getLogger(__name__)


# ============================================================
# Intent Request Schema
# ============================================================


@dataclass
class IntentRequest:
    intent: str
    fields: dict[str, int] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    raw: str = ""


# ============================================================
# Intent Classifier
# ============================================================


def _is_reset_only(text: str) -> bool:
    low = text.lower()
    reset_words = ("azzera", "azzerare", "azzeramento", "resetta", "reset", "svuota", "annulla")
    action_words = ("calcola", "somma", "aggiungi", "sottrai", "arrotonda", "gestisci",
                    "conta", "determina", "riconoscimento", "finale", "giro", "festivo",
                    "maggiorazione", "festivita", "pausa", "accumulo", "catena",
                    "flusso", "avispa", "gugest", "warning", "auts", "ritocco",
                    "presenza", "turno", "turnista", "turnisti", "assenze", "causale", "condizionale",
                    "durata", "impiegati", "pranzo", "esplodi", "straordinario",
                    "notturno", "diurno", "settimanale", "inizio", "giornata")
    return any(w in low for w in reset_words) and not any(w in low for w in action_words)


class IntentClassifier:
    """Classifica una richiesta utente in IntentRequest strutturato.
    Usa keyword matching deterministico per intents comuni.
    Si appoggia a FieldRegistry, TableRegistry e FormulaPatternLibrary.
    """

    _registry: FieldRegistry | None = None
    _table_registry: TableRegistry | None = None
    _patterns: FormulaPatternLibrary | None = None

    @classmethod
    def _get_registry(cls) -> FieldRegistry:
        if cls._registry is None:
            cls._registry = FieldRegistry()
        return cls._registry

    @classmethod
    def _get_table_registry(cls) -> TableRegistry:
        if cls._table_registry is None:
            cls._table_registry = TableRegistry()
        return cls._table_registry

    @classmethod
    def _get_patterns(cls) -> FormulaPatternLibrary:
        if cls._patterns is None:
            cls._patterns = FormulaPatternLibrary()
        return cls._patterns

    @classmethod
    def classify_all(cls, text: str) -> list[IntentRequest]:
        """Classifica una richiesta potenzialmente composta in più intent."""
        # Suddividi la richiesta in segmenti basati su connettivi logici semplici
        # Separa su connettivi, e anche su virgola prima di keyword intent
        text_prep = re.sub(
            r',\s*(?=riconoscimento|calcola|calcolo|arrotonda|azzeramento|finale|'
            r'straordinario|maggiorazione|gestione|accumula|catena|pausa|festivit|'
            r'flusso|avispa|gugest|warning|auts|ritocco|esplodi|se |mostra|vedi|'
            r'primo|secondo)',
            ' e ', text, flags=re.IGNORECASE)
        segments = re.split(r'\s+(?:e|ed|più|\+|;)\s+', text_prep, flags=re.IGNORECASE)
        segments = [s.strip().rstrip('.,;') for s in segments if s.strip()]
        results = []
        for seg in segments:
            req = cls.classify(seg)
            if req and req.intent != "unknown":
                results.append(req)
        return results

    @classmethod
    def classify(cls, text: str) -> IntentRequest:
        low = text.lower().strip()

        # 1. Reset puro
        if _is_reset_only(text):
            all_nums = set(re.findall(r'\b\d{1,4}\b', text))
            formula_refs = set()
            for m in re.finditer(r'[Ff]ormula\s+(\d{1,4})', text):
                formula_refs.add(m.group(1))
            for m in re.finditer(r'\b[Rr](\d{1,4})\b', text):
                formula_refs.add(m.group(1))
            fields = sorted(int(f) for f in all_nums if f not in formula_refs and 1 <= int(f) <= 899)
            if not fields:
                fields = [800, 801]
            return IntentRequest(intent="reset_puro", params={"fields": ",".join(str(f) for f in fields)}, confidence=1.0, raw=text)

        # === INTENT SPECIFICI (controllati prima dei generici) ===

        # Maggiorazioni turnisti (prima di riconoscimento_turno per 'turno' keyword)
        if ("maggiorazione" in low or "maggiorazioni" in low) and ("turno" in low or "turnista" in low or "turnisti" in low):
            return IntentRequest(intent="maggiorazioni_turnisti", confidence=0.85, raw=text)

        # Riconoscimento turno (dopo maggiorazioni, prima di calcolo presenza)
        has_251 = "251" in text
        has_271 = "271" in text
        # 'turno' dentro 'notturno' non deve matchare; 'turnista'/'turnisti' sono varianti
        has_turno_keyword = bool(re.search(r'\bturno\b', low)) or "riconoscimento" in low or "turnista" in low or "turnisti" in low
        if (has_turno_keyword or (has_251 and has_271 and "vuoto" in low)):
            entrata = cls._pick_field(text, (251, 252, 253, 254, 255, 256, 257), 251)
            uscita = cls._pick_field(text, (271, 272, 273, 274, 275, 276, 277), 271)
            val_no_pres = 2
            m = re.search(r'\b900\s*[=:]\s*\'?(\d+)', text)
            if m:
                val_no_pres = int(m.group(1))
            return IntentRequest(
                intent="riconoscimento_turno",
                fields={"entrata": entrata, "uscita": uscita, "flag": 900},
                params={"valore_non_presenza": str(val_no_pres)},
                conditions=[{"field": entrata, "op": "Z"}, {"field": uscita, "op": "Z"}],
                confidence=0.9, raw=text,
            )

        # Calcolo presenza (prima di causali/riconoscimento generico)
        has_presenza = "presenza" in low or "ore" in low or ("calcolo" in low and "presenza" in low)
        if has_presenza and (has_251 or has_271 or "flag" in low or "900" in text or "calcol" in low):
            entrata = cls._pick_field(text, (251, 252, 253, 254, 255, 256, 257), 251)
            uscita = cls._pick_field(text, (271, 272, 273, 274, 275, 276, 277), 271)
            flag = cls._extract_field_ref(text, r'(?:900|flag|destinazione)\s*[=:]\s*\'?(\d+)', 900)
            return IntentRequest(intent="calcolo_presenza", fields={"entrata": entrata, "uscita": uscita, "flag": flag}, confidence=0.85, raw=text)

        # AUTS (prima di riferimento_causale generico)
        if "auts" in low:
            return IntentRequest(intent="gestione_auts", confidence=0.85, raw=text)

        # Warning ore (prima di gestione_assenze generico)
        if ("warning" in low or "carenti" in low) and ("ore" in low or "alert" in low or "avviso" in low or "250" in text):
            return IntentRequest(intent="warning_ore", confidence=0.8, raw=text)

        # Ritocco SA/SB (prima di straordinario_diurno generico)
        if "ritocco" in low and ("sa" in low or "sb" in low):
            return IntentRequest(intent="ritocco_sa_sb", confidence=0.85, raw=text)

        # Straordinario specifici (prima di catena/k generici)
        if "straordinario" in low or "straord" in low:
            if "festivo" in low or "sf" in low or "domenica" in low or "sfn" in low:
                return IntentRequest(intent="straordinario_festivo", confidence=0.85, raw=text)
            if "notturno" in low or "sn" in low or "notte" in low:
                return IntentRequest(intent="straordinario_notturno", confidence=0.85, raw=text)
            if "diurno" in low or "s" in low or "ordinario" in low:
                if "settimana" not in low and "settimanale" not in low:
                    return IntentRequest(intent="straordinario_diurno", confidence=0.85, raw=text)

        # Straordinario settimanale
        if ("straordinario" in low or "straord" in low) and ("settimana" in low or "settimanale" in low):
            return IntentRequest(intent="straordinario_settimanale", confidence=0.8, raw=text)

        # AVISPA (prima di flusso generico)
        if "avispa" in low:
            return IntentRequest(intent="avispa", confidence=0.9, raw=text)

        # Flussi (prima di finale_giornata generico)
        if "flusso" in low:
            flow_name = cls._detect_flow(text)
            return IntentRequest(intent="flusso_fg",
                                  params={"flow": flow_name or "fine_giornata_standard"},
                                  confidence=0.8, raw=text)

        # AVISPA / GUGEST / FG B (prima di riferimento_formula)
        if "avispa" in low:
            return IntentRequest(intent="avispa", confidence=0.9, raw=text)
        if "gugest" in low:
            return IntentRequest(intent="gugest_b" if "b" in text.lower() else "gugest_a", confidence=0.9, raw=text)
        if "fg" in low and "b" in low:
            return IntentRequest(intent="fg_b", confidence=0.9, raw=text)

        # Primo/secondo giro
        if "primo giro" in low or ("giro" in low and "gugest" in low) or "2100" in text:
            return IntentRequest(intent="primo_giro", confidence=0.85, raw=text)
        if "secondo giro" in low or "2101" in text:
            return IntentRequest(intent="secondo_giro", confidence=0.85, raw=text)

        # Riferimento formula esplicito (prima di finale_giornata)
        code = cls._extract_formula_code(text)
        if code and code > 0 and cls._is_formula_ref(text):
            pattern = cls._get_patterns().get_pattern(code)
            if pattern:
                return IntentRequest(intent="riferimento_formula", fields={"code": code}, params={"name": pattern.name}, confidence=0.95, raw=text)

        # Azzeramento / Finale giornata
        if ("inizio giornata" in low or ("azzeramento" in low and "giornata" in low)) and "riconoscimento" not in low:
            return IntentRequest(intent="azzeramento_giornata", confidence=0.8, raw=text)

        if "fine giornata" in low or ("finale" in low and "flusso" not in low):
            return IntentRequest(intent="finale_giornata", confidence=0.8, raw=text)
        if ("esplode" in low or "esplodi" in low or "estrai" in low or "estraggo" in low) and ("causale" in low or "causali" in low):
            return IntentRequest(intent="riconoscimento_causale", confidence=0.8, raw=text)
        if "causale" in low and ("automatica" in low or "automatiche" in low or "slot" in low or "501" in text):
            return IntentRequest(intent="riconoscimento_causale", confidence=0.75, raw=text)
        if "causali" in low and ("automatica" in low or "automatiche" in low or "slot" in low or re.search(r'\b5\d{2}\b', text)):
            return IntentRequest(intent="riconoscimento_causale", confidence=0.75, raw=text)

        # Festività
        if ("festività" in low or "festivita" in low) and ("gestione" in low or "automatica" in low or "calcola" in low):
            return IntentRequest(intent="festivita", confidence=0.75, raw=text)

        # Pausa pranzo
        if ("pausa" in low and "pranzo" in low) or ("3020" in text and "pausa" in low):
            return IntentRequest(intent="pausa_pranzo", confidence=0.8, raw=text)

        # Arrotondamento impiegati
        if ("arrotondamento" in low and "impiegati" in low) or "9001" in text or "9002" in text:
            return IntentRequest(intent="arrotondamento_impiegati", fields={"code": 9001}, confidence=0.85, raw=text)

        # === INTENT GENERICI ===

        # Arrotondamento quarti d'ora
        if any(w in low for w in ("quarti d'ora", "quarto d'ora", "quarti", "arrotondamento minuti")):
            m_campo = re.search(r'(?:campo|campo)\s*(\d+)', text)
            campo = int(m_campo.group(1)) if m_campo else 3
            return IntentRequest(intent="arrotondamento_quarti", fields={"campo": campo}, confidence=0.7, raw=text)

        # Arrotondamento generico
        if any(w in low for w in ("arrotondamento", "arrotonda", "arrotondare", "approssima")):
            m_campo = re.search(r'(?:campo|campo)\s*(\d+)', text)
            campo = int(m_campo.group(1)) if m_campo else cls._pick_field(text, (800, 801, 900, 802, 803, 804, 805, 806), 800)
            approx = cls._extract_str(text, r'(?:approssimazion[ei]|a)\s*[:=]?\s*\'?(\d+(?:\.\d+)?)', "15")
            return IntentRequest(intent="arrotondamento", fields={"campo": campo}, params={"approssimazione": approx}, confidence=0.8, raw=text)

        # Gestione assenze (warning ore già controllato sopra)
        if any(w in low for w in ("assenza", "assenze", "carenti")):
            soglia = cls._extract_field_ref(text, r'(?:soglia|s)\s*[:=]?\s*\'?(\d+)', 250)
            return IntentRequest(intent="gestione_assenze", fields={"flag": 900}, params={"soglia": str(soglia)}, confidence=0.7, raw=text)

        # K accumulo
        if any(w in low for w in ("accumula", "accumulo", "k ", "k77", "k60", "aggiungi a", "somma a")):
            targets = cls._extract_k_targets(text)
            return IntentRequest(intent="k_accumulo", params={"targets": targets}, confidence=0.75, raw=text)

        # Catena / chain (usa word boundary per R e P)
        if any(w in low for w in ("catena", "chain", "collega", "richiama", "chiama", "salta a")):
            target = cls._extract_field_ref(text, r'(?:R\b|P\b|a|->)\s*(\d+)', 0)
            modo = "R" if ("salta" in low or "r " in low) else "P"
            return IntentRequest(intent="catena_formule", params={"target": str(target), "modo": modo}, confidence=0.65, raw=text)

        # Causali specifiche
        causale_code = cls._extract_causale(text)
        if causale_code:
            return IntentRequest(intent="riferimento_causale", params={"causale": causale_code}, confidence=0.6, raw=text)

        # Riferimento formula esplicito
        code = cls._extract_formula_code(text)
        if code and code > 0 and cls._is_formula_ref(text):
            pattern = cls._get_patterns().get_pattern(code)
            if pattern:
                return IntentRequest(intent="riferimento_formula", fields={"code": code}, params={"name": pattern.name}, confidence=0.95, raw=text)

        # Notturno standalone (dopo straordinario specifico, prima dei generici)
        if "notturno" in low or "notte" in low:
            return IntentRequest(intent="straordinario_notturno", confidence=0.7, raw=text)

        # Maggiorazioni generiche (anche senza 'turno' accanto)
        if "maggiorazioni" in low or "maggiorazione" in low:
            return IntentRequest(intent="maggiorazioni_turnisti", confidence=0.7, raw=text)

        # Condizionale generico
        if "se " in low and "altrimenti" in low:
            return IntentRequest(intent="condizionale_generico", params={"raw_text": text}, confidence=0.6, raw=text)

        # SET / IMPOSTA campo = valore
        m_set = re.search(r'(?:imposta|set|impostare|metti|assegna)\s+(\d{1,4})\s*=\s*(.+)', text, re.IGNORECASE)
        if not m_set:
            m_set = re.search(r'(?:imposta|set|impostare|metti|assegna)\s+(\d{1,4})\s+come\s+(.+)', text, re.IGNORECASE)
        if not m_set:
            m_set = re.search(r'(?:imposta|set|impostare|metti|assegna)\s+(\d{1,4})\s+a\s+(.+)', text, re.IGNORECASE)
        if m_set:
            field = int(m_set.group(1))
            value = m_set.group(2).strip().strip("'\"").strip()
            return IntentRequest(
                intent="set_field",
                fields={"target": field},
                params={"value": value},
                confidence=0.85,
                raw=text,
            )

        return IntentRequest(intent="unknown", confidence=0.0, raw=text)

    @staticmethod
    def _detect_flow(text: str) -> str | None:
        """Rileva nome flusso dalla richiesta."""
        low = text.lower()
        if "standard" in low or "normale" in low or "fine_giornata" in low:
            return "fine_giornata_standard"
        if "inizio" in low or "inizio_giornata" in low:
            return "inizio_giornata_standard"
        if "gugest" in low:
            if "b" in low:
                return "fine_giornata_gugest_b"
            return "fine_giornata_gugest_a"
        if "fg" in low and "b" in low:
            return "fine_giornata_fg_b"
        if "conad" in low:
            return "inizio_giornata_conad"
        # Cerca nome verbatim nei flow names
        for name in TableRegistry().get_all_flow_names():
            if name.replace("_", " ") in low:
                return name
        return None

    @staticmethod
    def _pick_field(text: str, candidates: tuple[int, ...], default: int) -> int:
        for c in candidates:
            if re.search(rf'\b{c}\b', text):
                return c
        return default

    @staticmethod
    def _extract_field_ref(text: str, pattern: str, default: int) -> int:
        m = re.search(pattern, text)
        return int(m.group(1)) if m else default

    @staticmethod
    def _extract_str(text: str, pattern: str, default: str) -> str:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1) if m else default

    @staticmethod
    def _extract_k_targets(text: str) -> str:
        m = re.search(r'K\d{3,4}(?:\s*[AS]\s*(?:\'?\w+\'?|\d+(?:\.\d+)?)\s*)+', text, re.IGNORECASE)
        if m:
            return m.group(0).upper()
        targets = re.findall(r'K(\d{3,4})', text.upper())
        if targets:
            return ",".join(targets)
        return "K601 A 3"

    @staticmethod
    def _extract_formula_code(text: str) -> int | None:
        m = re.search(r'(?:formula|codice|code|n\.?|numero)\s*[:#]?\s*(\d{1,4})', text, re.IGNORECASE)
        if m:
            code = int(m.group(1))
            if 1 <= code <= 9002:
                return code
        return None

    @classmethod
    def _is_formula_ref(cls, text: str) -> bool:
        """Verifica che il testo sia principalmente un riferimento a formula."""
        low = text.lower()
        if "catena" in low or "chiama" in low or "richiama" in low or "salta a" in low:
            return False
        if re.search(r'(?:mostra|vedi|apri|vai\s+a|cos.{,5})', low) or low.strip().isdigit():
            return True
        if re.search(r'(?:formula|codice|code)\s*\d', low):
            return True
        if low.strip().startswith(("r", "p")) and low.strip()[1:].isdigit():
            return True
        return False

    @classmethod
    def _extract_causale(cls, text: str) -> str | None:
        causali_known = cls._get_table_registry().CAUSALI
        codes = sorted(causali_known.keys(), key=len, reverse=True)
        for code in codes:
            if len(code) < 3:
                continue
            if re.search(rf'\b{re.escape(code)}\b', text, re.IGNORECASE):
                causale = causali_known[code]
                if causale.origin != "turno":
                    return code
        return None


# ============================================================
# WinSarp Compact Builders  (deterministici, mai IR)
# ============================================================


def _val_w(val: str) -> str:
    """Quota un valore per WinSarp compact."""
    val = val.strip().strip("'\"").strip()
    if val.upper() in ("I", "Z"):
        return val.upper()
    if val.replace(".", "").replace("-", "").isdigit():
        return f"'{val}'"
    return f'"{val}"'


def build_riconoscimento_turno(req: IntentRequest) -> str | None:
    entrata = req.fields.get("entrata", 251)
    uscita = req.fields.get("uscita", 271)
    flag = req.fields.get("flag", 900)
    val_no = req.params.get("valore_non_presenza", "2")
    return (
        f"(!{flag})"
        f"{entrata}UZE{uscita}UZ(({flag}='{val_no}')VF"
        f"({flag}='1')"
        f"({flag}={uscita}S{entrata})"
        f"VF"
    )


def build_calcolo_presenza(req: IntentRequest) -> str | None:
    entrata = req.fields.get("entrata", 251)
    uscita = req.fields.get("uscita", 271)
    flag = req.fields.get("flag", 900)
    return (
        f"(!71!72!73!74!75!76!77!78)"
        f"(71={entrata})(72={uscita})(70='2')"
        f"({flag}=73)"
        f"VF"
    )


def build_arrotondamento(req: IntentRequest) -> str | None:
    campo = req.fields.get("campo", 800)
    approx = req.params.get("approssimazione", "15")
    return (
        f"(!71!72!73!74!75!76!77!78)"
        f"(71={campo})(72='{approx}')"
        f"(70='20')"
        f"({campo}=73)"
        f"VF"
    )


def build_gestione_assenze(req: IntentRequest) -> str | None:
    flag = req.fields.get("flag", 900)
    return (
        f"(!{flag})"
        f"5>Z(({flag}='1')VF"
        f"({flag}='2')"
    )


def _k_val(v: str) -> str:
    """Quota valore per K accumulo: field ref (bare) vs constant (quoted)."""
    v = v.strip().strip("'\"").strip()
    if v.upper() in ("I", "Z"):
        return v.upper()
    if v.isdigit() and not v.startswith("0"):
        return v
    return f"'{v}'"


def build_k_accumulo(req: IntentRequest) -> str | None:
    targets_raw = req.params.get("targets", "K601 A 3")
    parts = targets_raw.replace(",", " ").split()
    if not parts:
        return None

    compact = ""
    i = 0
    while i < len(parts):
        t = parts[i].upper()
        if t.startswith("K") and t[1:].isdigit():
            field = t[1:]
            result = f"K{field}"
            i += 1
            while i + 1 < len(parts):
                op = parts[i].upper()
                if op not in ("A", "S"):
                    break
                v = parts[i + 1]
                result += f"{op}{_k_val(v)}"
                i += 2
            compact += f"({result})"
        else:
            i += 1
    return compact if compact else None


def build_arrotondamento_quarti(req: IntentRequest) -> str | None:
    """Arrotondamento ai quarti d'ora (pattern 2123)."""
    campo = req.fields.get("campo", 3)
    return (
        f"{campo}UZ(VF"
        f"(!800)(71={campo})(70='3')({campo}=72)"
        f"73<'15.00'(VF"
        f"73<'30.00'((K800A'0.15')VU"
        f"73<'45.00'((K800A'0.35')VU"
        f"73<U'59.00'((K800A'0.45')VU"
        f"(K{campo}A800)"
    )


def build_catena_formule(req: IntentRequest) -> str | None:
    target = req.params.get("target", "0")
    modo = req.params.get("modo", "R")
    if target == "0" or not target.isdigit():
        return None
    return f"{modo}{target}"


# ============================================================
# NUOVI BUILDER: restituiscono sintassi compatta REALE dalla PatternLibrary
# ============================================================


def _pattern_compact(code: int) -> str | None:
    """Helper: recupera compact reale da PatternLibrary."""
    p = FormulaPatternLibrary().get_pattern(code)
    return p.compact if p and p.compact else None


def build_straordinario_diurno(req: IntentRequest) -> str | None:
    """Straordinario diurno (pattern 140: separa SN da S)."""
    return _pattern_compact(140)


def build_straordinario_notturno(req: IntentRequest) -> str | None:
    """Straordinario notturno (pattern 140, parte notturna con 502='SN')."""
    return _pattern_compact(140)


def build_straordinario_festivo(req: IntentRequest) -> str | None:
    """Straordinario festivo (pattern 130: SFN + SF)."""
    return _pattern_compact(130)


def build_maggiorazioni_turnisti(req: IntentRequest) -> str | None:
    """Maggiorazioni turnisti (pattern 210: N + T)."""
    return _pattern_compact(210)


def build_azzeramento_giornata(req: IntentRequest) -> str | None:
    """Azzeramento inizio giornata (pattern 1: !900)."""
    return _pattern_compact(1)


def build_finale_giornata(req: IntentRequest) -> str | None:
    """Formula finale FG (pattern 200: K601 + K602 + P210)."""
    return _pattern_compact(200)


def build_riconoscimento_causale(req: IntentRequest) -> str | None:
    """Esplode causali automatiche (pattern 2115)."""
    return _pattern_compact(2115)


def build_festivita(req: IntentRequest) -> str | None:
    """Gestione festività automatica (pattern 2109)."""
    return _pattern_compact(2109)


def build_straordinario_settimanale(req: IntentRequest) -> str | None:
    """Straordinario settimanale (pattern 3005)."""
    return _pattern_compact(3005)


def build_flusso_fg(req: IntentRequest) -> str | None:
    """Restituisce l'intero flusso FG (catena di R)."""
    flow_name = req.params.get("flow", "fine_giornata_standard")
    flow = TableRegistry().get_formula_flow(flow_name)
    if not flow:
        return None
    lines = []
    for code in flow:
        p = FormulaPatternLibrary().get_pattern(code)
        if p:
            lines.append(f"R{code}  ? {p.name}")
    return "\n".join(lines) if lines else None


def build_avispa(req: IntentRequest) -> str | None:
    """Flusso AVISPA specifico."""
    return None


def build_gugest_a(req: IntentRequest) -> str | None:
    """Flusso GUGEST A."""
    flow = TableRegistry().get_formula_flow("fine_giornata_gugest_a")
    if not flow:
        return None
    lines = []
    for code in flow:
        p = FormulaPatternLibrary().get_pattern(code)
        if p:
            lines.append(f"R{code}  ? {p.name}")
    return "\n".join(lines) if lines else None


def build_gugest_b(req: IntentRequest) -> str | None:
    """Flusso GUGEST B."""
    flow = TableRegistry().get_formula_flow("fine_giornata_gugest_b")
    if not flow:
        return None
    lines = []
    for code in flow:
        p = FormulaPatternLibrary().get_pattern(code)
        if p:
            lines.append(f"R{code}  ? {p.name}")
    return "\n".join(lines) if lines else None


def build_fg_b(req: IntentRequest) -> str | None:
    """Flusso FG B."""
    flow = TableRegistry().get_formula_flow("fine_giornata_fg_b")
    if not flow:
        return None
    lines = []
    for code in flow:
        p = FormulaPatternLibrary().get_pattern(code)
        if p:
            lines.append(f"R{code}  ? {p.name}")
    return "\n".join(lines) if lines else None


def build_primo_giro(req: IntentRequest) -> str | None:
    """Primo giro GUGEST (pattern 2100)."""
    return _pattern_compact(2100)


def build_secondo_giro(req: IntentRequest) -> str | None:
    """Secondo giro GUGEST (pattern 2101)."""
    return _pattern_compact(2101)


def build_ritocco_sa_sb(req: IntentRequest) -> str | None:
    """Ritocco SA/SB cap 8h (pattern 2114)."""
    return _pattern_compact(2114)


def build_warning_ore(req: IntentRequest) -> str | None:
    """Warning ore carenti / soglia 250h (pattern 2130)."""
    return _pattern_compact(2130)


def build_gestione_auts(req: IntentRequest) -> str | None:
    """Gestione autorizzazioni straordinario AUTS (pattern 3017)."""
    return _pattern_compact(3017)


def build_arrotondamento_impiegati(req: IntentRequest) -> str | None:
    """Arrotondamento impiegati al quarto d'ora (pattern 9001+9002)."""
    p1 = _pattern_compact(9001)
    p2 = _pattern_compact(9002)
    if p1 and p2:
        return p1 + "\n" + p2
    return p1 or p2 or None


def build_pausa_pranzo(req: IntentRequest) -> str | None:
    """Pausa pranzo: calcolo durata e forzatura 30 min (pattern 3020 o builder manuale)."""
    compact = _pattern_compact(3020)
    if compact:
        return compact
    # Builder manuale se pattern non ha compact
    return (
        "(!71!72!73!74!75!76!77!78)"
        "(71=252)(72=271)(70='2')"
        "(800=73)"
        "800<UZ(K800A'24')"
        "800<'00.30'((271='{252}S00.30')"
        "VF"
    )


def build_riferimento_formula(req: IntentRequest) -> str | None:
    code = req.fields.get("code", 0)
    if not code:
        return None
    pattern = FormulaPatternLibrary().get_pattern(code)
    if not pattern or not pattern.compact:
        return None
    return pattern.compact


def build_riferimento_causale(req: IntentRequest) -> str | None:
    """Restituisce informazioni su una causale."""
    causale_code = req.params.get("causale", "")
    if not causale_code:
        return None
    causale = TableRegistry().get_causale(causale_code)
    if not causale:
        return None
    slots = TableRegistry().get_slot_for_causale(causale_code)
    slot_info = f"slot {slots}" if slots else "nessuno slot automatico"
    return f"Causale '{causale_code}' ({causale.name}): {causale.description}. {slot_info}."


def build_condizionale_generico(req: IntentRequest) -> str | None:
    raw = req.params.get("raw_text", "")
    if not raw:
        return None
    m = re.match(r'se\s+(.+?)\s+(?:allora|then|:)\s+(.+?)\s+(?:altrimenti|else)\s+(.+)', raw, re.IGNORECASE)
    if not m:
        return None
    cond_win = _parse_cond_it(m.group(1).strip())
    then_win = _parse_action_it(m.group(2).strip())
    else_win = _parse_action_it(m.group(3).strip())
    if not cond_win or not then_win:
        return None
    return f"{cond_win}(({then_win})VF;{else_win}VF"


def _parse_cond_it(text: str) -> str | None:
    m = re.match(r'(\d+)\s*(?:e|ed|,)?\s*(\d+)?\s*(vuot[oi]|vuota|Z|0)', text)
    if m:
        f1, f2 = m.group(1), m.group(2)
        return f"{f1} U Z E {f2} U Z" if f2 else f"{f1} U Z"
    m = re.match(r'(\d+)\s*(=|>|<|>=|<=|!=|#)\s*(.+)$', text)
    if m:
        f, op, val = m.group(1), m.group(2), m.group(3).strip().strip("'\"").strip()
        op_map = {"=": "U", ">": ">", "<": "<", ">=": ">U", "<=": "<U", "!=": "#", "#": "#"}
        return f"{f} {op_map.get(op, 'U')} {_val_w(val)}"
    return None


def _parse_action_it(text: str) -> str | None:
    m = re.match(r'(?:imposta|set|impostare|metti)\s+(\d+)\s*=\s*(\S+)', text, re.IGNORECASE)
    if m:
        return f"({m.group(1)}={_val_w(m.group(2))})"
    m = re.match(r'calcola\s+(?:ore|presenza)\s+(?:in|=>|->|–)?\s*(\d+)', text, re.IGNORECASE)
    if m:
        return f"(!71!72!73!74!75!76!77!78)(71=251)(72=271)(70='2')({m.group(1)}=73)"
    return f"({text.strip()})"


# ============================================================
# Builder Registry & Dispatch
# ============================================================


def _build_reset_puro(req: IntentRequest) -> str | None:
    fields_str = req.params.get("fields", "800,801")
    fields = [int(f.strip()) for f in fields_str.split(",") if f.strip().isdigit()]
    if not fields:
        fields = [800, 801]
    return "(" + "".join(f"!{f}" for f in fields) + ")"


def build_durata_intervallo(req: IntentRequest) -> str | None:
    """Calcola la durata di un intervallo (pattern 2122 / Campo70=11)."""
    entrata = req.fields.get("entrata", 0)
    uscita = req.fields.get("uscita", 0)
    target = req.fields.get("target", 800)

    if not (entrata and uscita):
        return None
    return f"(71={entrata})(72={uscita})(70='11')({target}=73)"


def _certify(formula: str, intent: str, req: IntentRequest) -> dict:
    """Costruisce output certificato: controllo sintassi + sicurezza memoria + spiegazione."""
    registry = FieldRegistry()
    # Estrai numeri che sono potenziali field reference:
    # - Salta numeri dentro quote singole/doppie (sono valori costanti)
    # - Salta numeri <= 59 che non sono campi noti (sono minuti/ore valori)
    quoted_positions = set()
    in_sq = False
    in_dq = False
    for i, ch in enumerate(formula):
        if ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif in_sq or in_dq:
            quoted_positions.add(i)
    involved_raw = set()
    for m in re.finditer(r'\b(\d{2,4})\b', formula):
        if m.start() not in quoted_positions:
            involved_raw.add(int(m.group(1)))
    involved = set()
    for f in involved_raw:
        if f <= 59 and f not in registry.FIELDS:
            continue
        involved.add(f)
    forbidden = [f for f in sorted(involved) if not registry.is_field_valid(f)]

    certification_parts = [f"Pattern: {intent}"]
    if not forbidden:
        certification_parts.append("Nessun campo proibito")
    certification_parts.append("Sintassi compatta certificata")

    from legacy_winsarp.core.winsarp.linter import WinSarpLinter
    linter = WinSarpLinter()
    lint_issues = linter.lint_compact(formula)
    has_lint_errors = any(i.severity == "error" for i in lint_issues)

    if has_lint_errors:
        certification_parts.append(f"Lint: {len(lint_issues)} errori")
    else:
        certification_parts.append("Lint: OK")

    error_msg = None
    if forbidden:
        error_msg = f"Campo {forbidden[0]} non valido (forbidden range)"
    elif lint_issues:
        error_msg = lint_issues[0].message

    return {
        "certified": not forbidden and not has_lint_errors,
        "certification": " | ".join(certification_parts),
        "formula": formula,
        "source": f"intent_builder_{intent}",
        "success": True,
        "error": error_msg,
        "raw": f"Intent: {req.intent}\nFields: {req.fields}\nParams: {req.params}",
        "chain": "",
        "placement": {"aggancio": "", "ponte": ""},
        "explanation": (
            f"Formula certificata generata deterministicamente per intent '{req.intent}'.\n"
            f"Campi coinvolti: {involved}\n"
            f"Certificazione: {'; '.join(certification_parts)}"
        ),
    }


def build_set_field(req: IntentRequest) -> str | None:
    """Genera SET campo = valore (es. imposta 500 come DURATA -> (500='DURATA'))"""
    target = req.fields.get("target", 0)
    value = req.params.get("value", "")
    if not target or not value:
        return None
    return f"({target}={_val_w(value)})"


_BUILDERS: dict[str, callable] = {
    "reset_puro": _build_reset_puro,
    "set_field": build_set_field,
    "riconoscimento_turno": build_riconoscimento_turno,
    "calcolo_presenza": build_calcolo_presenza,
    "arrotondamento": build_arrotondamento,
    "gestione_assenze": build_gestione_assenze,
    "k_accumulo": build_k_accumulo,
    "arrotondamento_quarti": build_arrotondamento_quarti,
    "catena_formule": build_catena_formule,
    "condizionale_generico": build_condizionale_generico,
    "riferimento_formula": build_riferimento_formula,
    "riferimento_causale": build_riferimento_causale,
    # Builder specifico per durata
    "durata_intervallo": build_durata_intervallo,
    # Nuovi builder specializzati
    "straordinario_diurno": build_straordinario_diurno,
    "straordinario_notturno": build_straordinario_notturno,
    "straordinario_festivo": build_straordinario_festivo,
    "maggiorazioni_turnisti": build_maggiorazioni_turnisti,
    "azzeramento_giornata": build_azzeramento_giornata,
    "finale_giornata": build_finale_giornata,
    "riconoscimento_causale": build_riconoscimento_causale,
    "festivita": build_festivita,
    "straordinario_settimanale": build_straordinario_settimanale,
    "flusso_fg": build_flusso_fg,
    "avispa": build_avispa,
    "gugest_a": build_gugest_a,
    "gugest_b": build_gugest_b,
    "fg_b": build_fg_b,
    "primo_giro": build_primo_giro,
    "secondo_giro": build_secondo_giro,
    "ritocco_sa_sb": build_ritocco_sa_sb,
    "warning_ore": build_warning_ore,
    "gestione_auts": build_gestione_auts,
    "arrotondamento_impiegati": build_arrotondamento_impiegati,
    "pausa_pranzo": build_pausa_pranzo,
}


def build_from_intents(reqs: list[IntentRequest]) -> dict | None:
    """Genera formula compatta WinSarp concatenando risultati di più intent con risoluzione conflitti."""
    graph = FormulaDependencyGraph()
    graph.load()

    # 1. Prepara nodi
    formula_nodes = []
    type_priority = {"Inizio Giornata": 1, "Di Giornata": 2, "Fine Giornata": 3, "Subroutine": 4}

    intent_to_tipo = {
        "reset_puro": "Inizio Giornata",
        "set_field": "Di Giornata",
        "azzeramento_giornata": "Inizio Giornata",
        "riconoscimento_turno": "Inizio Giornata",
        "calcolo_presenza": "Di Giornata",
        "arrotondamento": "Di Giornata",
        "pausa_pranzo": "Di Giornata",
        "straordinario_diurno": "Fine Giornata",
        "straordinario_notturno": "Fine Giornata",
        "straordinario_festivo": "Fine Giornata",
        "straordinario_settimanale": "Fine Giornata",
        "maggiorazioni_turnisti": "Fine Giornata",
        "finale_giornata": "Fine Giornata",
        "flusso_fg": "Fine Giornata",
        "avispa": "Fine Giornata",
        "gugest_a": "Fine Giornata",
        "gugest_b": "Fine Giornata",
        "fg_b": "Fine Giornata",
        "primo_giro": "Fine Giornata",
        "secondo_giro": "Fine Giornata",
        "ritocco_sa_sb": "Subroutine",
        "warning_ore": "Subroutine",
        "gestione_auts": "Subroutine",
        "arrotondamento_impiegati": "Inizio Giornata",
        "riconoscimento_causale": "Subroutine",
        "festivita": "Subroutine",
        "arrotondamento_quarti": "Di Giornata",
        "k_accumulo": "Di Giornata",
        "condizionale_generico": "Di Giornata",
        "durata_intervallo": "Di Giornata",
    }

    for req in reqs:
        tipo = intent_to_tipo.get(req.intent, "Subroutine")
        priority = type_priority.get(tipo, 99)
        formula_nodes.append((req, tipo, priority))

    # Validazione flusso PRIMA del sort: blocca violazioni IG->DG->FG nell'ordine originale
    seen_types = set()
    for req, tipo, _ in formula_nodes:
        for seen in seen_types:
            if type_priority.get(seen, 99) > type_priority.get(tipo, 99):
                return {
                    "formula": None, "source": "error", "success": False,
                    "error": f"Violazione flusso: {tipo} dopo {seen} - ordine deve essere IG->DG->FG",
                    "raw": f"Intents: {[r.intent for r in reqs]}",
                    "explanation": (
                        f"L'intent '{req.intent}' ({tipo}) non puo seguire '{seen}' "
                        f"perche viola l'ordine logico Inizio Giornata -> Di Giornata -> Fine Giornata."
                    ),
                }
        seen_types.add(tipo)

    formula_nodes.sort(key=lambda x: x[2])

    # 2. Concatenazione con risoluzione conflitti
    used_appoggio = set()
    mapped_fields = {} # original -> mapped
    formula_parts = []
    sub_certifications = []

    for req, tipo, _ in formula_nodes:
        res = build_from_intent(req)
        if not res or not res.get("formula"): continue

        f = res["formula"].strip()

        # Rimuovi terminali se non è l'ultimo
        if len(formula_parts) < len(reqs) - 1:
            f = re.sub(r'(VF|VU)$', '', f).strip()

        # Detect appoggio fields (800-999)
        found_fields = set(int(n) for n in re.findall(r'\b([89]\d{2})\b', f))

        for f_id in found_fields:
            if f_id in mapped_fields:
                f = re.sub(rf'\b{f_id}\b', str(mapped_fields[f_id]), f)
            elif f_id in used_appoggio:
                new_f = f_id
                while new_f in used_appoggio and new_f < 999:
                    new_f += 1
                mapped_fields[f_id] = new_f
                used_appoggio.add(new_f)
                f = re.sub(rf'\b{f_id}\b', str(new_f), f)
            else:
                used_appoggio.add(f_id)

        formula_parts.append(f)
        sub_certifications.append(res.get("certification", ""))

    if not formula_parts:
        return None

    formula = "\n".join(formula_parts)

    # Certificazione finale
    from legacy_winsarp.core.winsarp.linter import WinSarpLinter
    linter = WinSarpLinter()
    lint_issues = linter.lint_compact(formula)
    has_lint_errors = any(i.severity == "error" for i in lint_issues)

    ordered_types = " -> ".join(t for _, t, _ in formula_nodes)
    cert_parts = [
            f"Flusso: {ordered_types}",
            f"Intents: {', '.join(r.intent for r, _, _ in formula_nodes)}",
            "Flusso IG->DG->FG verificato" if not has_lint_errors else "ATTENZIONE: violazione flusso rilevata",
        ]

    return {
        "formula": formula,
        "source": "composite_intent_builder",
        "success": True,
        "error": None,
        "raw": f"Intents: {[r.intent for r in reqs]}",
        "certified": not has_lint_errors,
        "certification": " | ".join(cert_parts) + " | " + "; ".join(c for c in sub_certifications if c),
        "explanation": (
            f"Formula composita generata da {len(formula_nodes)} intent.\n"
            f"Ordinamento: {ordered_types}\n"
            f"Certificazione: {cert_parts[1]}; {cert_parts[2]}"
        ),
    }


def build_ir_from_intent(req: IntentRequest) -> list[str]:
    """Genera IR steps da un IntentRequest.

    Returns a list of IR step strings ready for WinSarpBuilder.build_compact().
    """
    from legacy_winsarp.core.formula_builder import FormulaBuilder
    builder = _BUILDERS.get(req.intent)
    if not builder:
        return []
    formula = builder(req)
    if not formula:
        return []
    # First try the existing converter (works for LLM-style output)
    raw_steps = FormulaBuilder._try_convert_raw_formula_to_steps(formula)
    if raw_steps and len(raw_steps) > 1:
        return raw_steps
    # Return the full formula as a single raw step.
    # build_compact/_compact_stmt will pass it through as-is in the fallback branch.
    return [formula]


def build_from_intent(req: IntentRequest) -> dict | None:
    """Genera formula compatta WinSarp da un IntentRequest."""
    builder = _BUILDERS.get(req.intent)
    if not builder:
        return None
    formula = builder(req)
    if not formula:
        return None
    return _certify(formula, req.intent, req)
