"""
core/query_expander.py
Enterprise Query Expansion and Dynamic Synonym Disambiguation.
Expands business terminology, Italian labor/corporate acronyms, and customizable domain synonyms
to maximize recall in BM25/FTS5 and dense semantic search.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

# Glossario base di sinonimi e acronimi aziendali frequenti (italiano/inglese aziendale)
ENTERPRISE_SYNONYMS: dict[str, list[str]] = {
    "tfr": ["trattamento fine rapporto", "liquidazione"],
    "ccnl": ["contratto collettivo nazionale", "accordo nazionale lavoro"],
    "cedolino": ["busta paga", "prospetto paga", "retribuzione"],
    "busta paga": ["cedolino", "prospetto paga", "stipendio"],
    "malattia": ["certificato medico", "inps malattia", "visita fiscale", "prognosi"],
    "certificato medico": ["malattia", "inps", "assenza medica"],
    "smart working": ["lavoro agile", "lavoro da remoto", "telelavoro", "lavoro a distanza"],
    "lavoro agile": ["smart working", "telelavoro", "lavoro da remoto"],
    "ferie": ["piano ferie", "giorni di congedo", "riposo annuale"],
    "permessi": ["rol", "riduzione orario lavoro", "permessi retribuiti", "ex festivita"],
    "rol": ["riduzione orario lavoro", "permessi retribuiti"],
    "maternita": ["congedo parentale", "congedo maternita", "astensione obbligatoria"],
    "paternita": ["congedo paternita", "congedo parentale"],
    "straordinario": ["lavoro straordinario", "ore eccedenti", "maggiorazione"],
    "dimissioni": ["recesso contratto", "risoluzione rapporto", "preavviso dimissioni"],
    "preavviso": ["termini di preavviso", "indennita mancato preavviso"],
    "infortunio": ["inail", "infortunio sul lavoro", "denuncia infortunio"],
    "badge": ["marcatempo", "timbratura", "cartellino presenze", "rilevazione presenze"],
    "timbratura": ["badge", "marcatempo", "rilevazione presenze"],
    "rimborso spese": ["nota spese", "trasferta", "giustificativi spesa", "diaria"],
    "trasferta": ["rimborso spese", "missione", "indennita trasferta"],
    "vpn": ["accesso remoto", "connessione protetta", "rete aziendale"],
    "wifi": ["rete wireless", "connessione ospiti", "accesso internet"],
    "gdpr": ["privacy", "trattamento dati personali", "dpo", "informativa privacy"],
    "dpo": ["responsabile protezione dati", "data protection officer", "gdpr"],
    "sicurezza": ["dvr", "documento valutazione rischi", "rspp", "dispositivi protezione"],
    "dvr": ["documento valutazione rischi", "sicurezza sul lavoro", "testo unico 81"],
    "formazione": ["corsi obbligatori", "piano formativo", "crediti formativi"],
}

# Cache in memoria per i sinonimi custom
_cache_lock = threading.Lock()
_cached_custom_synonyms: dict[str, list[str]] = {}
_cached_mtime: float = -1.0
_cached_file: str = ""


def get_custom_synonyms_path(filepath: str | Path | None = None) -> str:
    """Restituisce il percorso canonico del file dei sinonimi personalizzati."""
    if filepath is not None:
        return os.path.abspath(str(filepath))
    try:
        from config import cfg

        return getattr(cfg, "SYNONYMS_FILE", os.path.abspath("config/synonyms.json"))
    except Exception:
        return os.path.abspath("config/synonyms.json")


def _get_synonyms_lock(filepath: str) -> Any:
    """Acquisisce il lock sul file per concorrenza multi-processo."""
    from core.governance import _get_file_lock

    lock_path = filepath + ".lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    return _get_file_lock(lock_path)


def load_custom_synonyms(filepath: str | Path | None = None) -> dict[str, list[str]]:
    """Carica i sinonimi custom da file JSON con protezione lock e cache su mtime."""
    global _cached_custom_synonyms, _cached_mtime, _cached_file

    target_path = get_custom_synonyms_path(filepath)

    if not os.path.exists(target_path):
        with _cache_lock:
            if _cached_file == target_path:
                _cached_custom_synonyms = {}
                _cached_mtime = -1.0
        return {}

    try:
        mtime = os.path.getmtime(target_path)
    except OSError:
        return {}

    with _cache_lock:
        if _cached_file == target_path and _cached_mtime == mtime:
            return copy.deepcopy(_cached_custom_synonyms)

    lock = _get_synonyms_lock(target_path)
    with lock:
        if not os.path.exists(target_path):
            return {}
        try:
            mtime = os.path.getmtime(target_path)
            with _cache_lock:
                if _cached_file == target_path and _cached_mtime == mtime:
                    return copy.deepcopy(_cached_custom_synonyms)

            with open(target_path, encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    raw_data = {}
                else:
                    raw_data = json.loads(content)
        except Exception as e:
            _logger.warning("Impossibile caricare sinonimi da %s: %s", target_path, e)
            return {}

        cleaned: dict[str, list[str]] = {}
        if isinstance(raw_data, dict):
            for k, v in raw_data.items():
                if isinstance(k, str) and isinstance(v, (list, tuple)):
                    clean_k = k.strip().lower()
                    if clean_k:
                        clean_v: list[str] = []
                        for item in v:
                            if isinstance(item, str):
                                s = item.strip().lower()
                                if s and s != clean_k and s not in clean_v:
                                    clean_v.append(s)
                        if clean_v:
                            cleaned[clean_k] = clean_v

        with _cache_lock:
            _cached_custom_synonyms = cleaned
            _cached_mtime = mtime
            _cached_file = target_path

        return copy.deepcopy(cleaned)


def save_custom_synonyms(
    synonyms: dict[str, list[str]],
    filepath: str | Path | None = None,
) -> dict[str, list[str]]:
    """Salva atomicamente i sinonimi custom su file JSON protetto da lock."""
    global _cached_custom_synonyms, _cached_mtime, _cached_file

    target_path = get_custom_synonyms_path(filepath)
    target_dir = os.path.dirname(target_path)
    os.makedirs(target_dir, exist_ok=True)

    cleaned: dict[str, list[str]] = {}
    for k, v in synonyms.items():
        if isinstance(k, str) and isinstance(v, (list, tuple)):
            clean_k = k.strip().lower()
            if clean_k:
                clean_v: list[str] = []
                for item in v:
                    if isinstance(item, str):
                        s = item.strip().lower()
                        if s and s != clean_k and s not in clean_v:
                            clean_v.append(s)
                if clean_v:
                    cleaned[clean_k] = clean_v

    lock = _get_synonyms_lock(target_path)
    with lock:
        serialized = json.dumps(cleaned, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile("w", dir=target_dir, delete=False, encoding="utf-8") as tf:
            tf.write(serialized)
            tf.flush()
            temp_name = tf.name

        os.replace(temp_name, target_path)
        mtime = os.path.getmtime(target_path)

        with _cache_lock:
            _cached_custom_synonyms = cleaned
            _cached_mtime = mtime
            _cached_file = target_path

    return copy.deepcopy(cleaned)


def add_custom_synonym(
    term: str,
    synonyms: list[str],
    filepath: str | Path | None = None,
) -> dict[str, list[str]]:
    """Aggiunge o aggiorna un termine personalizzato con i relativi sinonimi."""
    clean_term = term.strip().lower()
    if not clean_term:
        raise ValueError("Il termine del sinonimo non puo' essere vuoto")

    clean_synonyms: list[str] = []
    for s in synonyms:
        if isinstance(s, str):
            clean_s = s.strip().lower()
            if clean_s and clean_s != clean_term and clean_s not in clean_synonyms:
                clean_synonyms.append(clean_s)

    if not clean_synonyms:
        raise ValueError("Specificare almeno un sinonimo valido diverso dal termine")

    current = load_custom_synonyms(filepath)
    current[clean_term] = clean_synonyms
    return save_custom_synonyms(current, filepath)


def delete_custom_synonym(term: str, filepath: str | Path | None = None) -> bool:
    """Elimina un termine personalizzato dai sinonimi custom. Restituisce True se eliminato."""
    clean_term = term.strip().lower()
    current = load_custom_synonyms(filepath)
    if clean_term in current:
        del current[clean_term]
        save_custom_synonyms(current, filepath)
        return True
    return False


def get_all_synonyms(
    custom_dict: dict[str, list[str]] | None = None,
    filepath: str | Path | None = None,
) -> dict[str, list[str]]:
    """Restituisce il dizionario unificato dei sinonimi.

    Unisce il glossario base predefinito con i termini personalizzati su file
    e gli eventuali termini forniti a runtime. I sinonimi custom hanno precedenza.
    """
    merged: dict[str, list[str]] = copy.deepcopy(ENTERPRISE_SYNONYMS)

    custom_on_disk = load_custom_synonyms(filepath)
    for term, syns in custom_on_disk.items():
        if term in merged:
            existing = merged[term]
            combined = list(syns)
            for e in existing:
                if e not in combined:
                    combined.append(e)
            merged[term] = combined
        else:
            merged[term] = list(syns)

    if custom_dict:
        for term, syns in custom_dict.items():
            clean_k = term.strip().lower()
            if clean_k:
                if clean_k in merged:
                    existing = merged[clean_k]
                    combined = [s.strip().lower() for s in syns if s.strip().lower() != clean_k]
                    for e in existing:
                        if e not in combined:
                            combined.append(e)
                    merged[clean_k] = combined
                else:
                    merged[clean_k] = [s.strip().lower() for s in syns if s.strip().lower() != clean_k]

    return merged


def expand_query(
    query: str,
    max_expansions: int = 3,
    custom_synonyms: dict[str, list[str]] | None = None,
    filepath: str | Path | None = None,
) -> list[str]:
    """Data una query utente, genera varianti di ricerca arricchite

    con sinonimi aziendali e acronimi espansi.

    Supporta termini custom caricati da disco o passati come parametro.
    Ordina i termini per lunghezza decrescente per dare precedenza ai composti
    multi-parola rispetto alle singole parole.

    Restituisce una lista di stringhe di ricerca (la prima e' sempre la query originale).
    """
    cleaned = query.strip()
    if not cleaned:
        return [query]

    expanded_terms: list[str] = []
    lowered = cleaned.lower()

    all_synonyms = get_all_synonyms(custom_dict=custom_synonyms, filepath=filepath)

    sorted_terms = sorted(all_synonyms.keys(), key=lambda t: len(t), reverse=True)

    for term in sorted_terms:
        syns = all_synonyms[term]
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, lowered):
            for s in syns:
                if s not in lowered and s not in expanded_terms:
                    expanded_terms.append(s)
                    if len(expanded_terms) >= max_expansions:
                        break
        if len(expanded_terms) >= max_expansions:
            break

    results = [cleaned]
    if expanded_terms:
        combined = f"{cleaned} " + " ".join(expanded_terms[:max_expansions])
        results.append(combined.strip())

    return results
