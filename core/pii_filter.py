"""
pii_filter.py
Filtro PII (Personal Identifiable Information) per contesto RAG.
Rileva e oscura dati sensibili prima dell'invio all'LLM.
"""
import logging
import re

_logger = logging.getLogger(__name__)

# ── Pattern di rilevamento PII ──

PATTERNS: list[tuple[str, str, str]] = [
    # (nome_pattern, regex, replacement)
    ("email", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
    ("telefono_italia", r"(?:\+39\s?)?(?:\d{3,4}[-\s]?){2,4}\d{3,4}", "[TELEFONO]"),
    ("codice_fiscale", r"[A-Za-z]{6}\d{2}[A-Za-z]{1}\d{2}[A-Za-z]{1}\d{3}[A-Za-z]{1}", "[CODICE_FISCALE]"),
    ("partita_iva", r"(?:IT\s?)?\d{11}", "[PARTITA_IVA]"),
    ("carta_credito", r"(?:\d{4}[-\s]?){3}\d{4}", "[CARTA_CREDITO]"),
    ("indirizzo_ip", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]"),
]


def filter_pii(text: str, enabled: bool = True) -> str:
    """
    Applica il filtro PII al testo. Sostituisce i dati sensibili
    con segnaposto (es. [EMAIL], [TELEFONO]).

    Args:
        text: Testo da filtrare
        enabled: Se False, restituisce il testo originale (utile per debug)

    Returns:
        Testo con dati sensibili oscurati
    """
    if not enabled or not text:
        return text

    result = text
    detected = 0

    for name, pattern, replacement in PATTERNS:
        try:
            new_result, count = re.subn(pattern, replacement, result, flags=re.IGNORECASE)
            if count > 0:
                detected += count
                _logger.debug("PII filter: %d occorrenze di '%s' oscurate", count, name)
            result = new_result
        except re.error as e:
            _logger.warning("PII filter: regex error per '%s': %s", name, e)

    if detected > 0:
        _logger.info("PII filter: %d occorrenze totali oscurate", detected)

    return result


def detect_pii(text: str) -> list[dict]:
    """
    Rileva PII nel testo senza oscurarlo.

    Returns:
        Lista di dict: {type, value, position}
    """
    results = []
    for name, pattern, _ in PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            results.append({
                "type": name,
                "value": match.group(),
                "position": match.start(),
            })
    return results


def filter_pii_batch(texts: list[str], enabled: bool = True) -> list[str]:
    """Applica filter_pii a una lista di testi."""
    return [filter_pii(t, enabled=enabled) for t in texts]
