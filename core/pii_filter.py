"""
pii_filter.py
Filtro Enterprise DLP (Data Loss Prevention) e PII per contesto RAG.
Rileva e oscura dati sensibili prima dell'invio all'LLM e protegge le risposte in uscita.
"""
from __future__ import annotations

import logging
import re

_logger = logging.getLogger(__name__)

# ── Pattern di rilevamento PII ──

PATTERNS: list[tuple[str, str, str]] = [
    # (nome_pattern, regex, replacement)
    ("carta_credito", r"\b(?:\d{4}[-\s]?){3}\d{4}\b", "[CARTA_CREDITO]"),
    ("iban", r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b", "[IBAN]"),
    ("jwt_token", r"eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}", "[JWT_TOKEN]"),
    ("api_key_generic", r"(?:api[_-]?key|secret[_-]?key|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{24,})['\"]?", "[API_KEY]"),
    ("codice_fiscale", r"\b[A-Za-z]{6}\d{2}[A-Za-z]{1}\d{2}[A-Za-z]{1}\d{3}[A-Za-z]{1}\b", "[CODICE_FISCALE]"),
    ("partita_iva", r"\b(?:IT\s?)?\d{11}\b", "[PARTITA_IVA]"),
    ("email", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
    ("telefono_italia", r"\b(?:\+39\s?)?(?:0\d{1,4}[-\s]?\d{4,8}|3\d{2}[-\s]?\d{3,4}[-\s]?\d{3,4})\b", "[TELEFONO]"),
    ("indirizzo_ip", r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b", "[IP]"),
]


def _validate_luhn(card_number_str: str) -> bool:
    """Verifica la validità del numero di carta di credito con l'algoritmo di Luhn."""
    digits = [int(d) for d in re.sub(r"\D", "", card_number_str)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0


def _validate_iban(iban_str: str) -> bool:
    """Verifica validità formale dell'IBAN con algoritmo MOD 97-10 (ISO 7064)."""
    cleaned = re.sub(r"\s+", "", iban_str).upper()
    if len(cleaned) < 15 or len(cleaned) > 34:
        return False
    # Sposta i primi 4 caratteri alla fine
    rearranged = cleaned[4:] + cleaned[:4]
    # Converte lettere in numeri (A=10, B=11, ..., Z=35)
    numeric_str = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric_str) % 97 == 1
    except ValueError:
        return False


def filter_pii(text: str, enabled: bool = True) -> str:
    """
    Applica il filtro PII/DLP al testo. Sostituisce i dati sensibili
    con segnaposto (es. [EMAIL], [IBAN], [CODICE_FISCALE]).

    Args:
        text: Testo da filtrare
        enabled: Se False, restituisce il testo originale.

    Returns:
        Testo con dati sensibili oscurati.
    """
    if not enabled or not text:
        return text

    result = text
    detected = 0

    for name, pattern, replacement in PATTERNS:
        try:
            if name == "carta_credito":
                def _replace_cc(match: re.Match[str]) -> str:
                    nonlocal detected
                    matched = match.group(0)
                    if _validate_luhn(matched):
                        detected += 1
                        return replacement
                    return matched

                result = re.sub(pattern, _replace_cc, result)
            elif name == "iban":
                def _replace_iban(match: re.Match[str]) -> str:
                    nonlocal detected
                    matched = match.group(0)
                    if _validate_iban(matched):
                        detected += 1
                        return replacement
                    return matched

                result = re.sub(pattern, _replace_iban, result, flags=re.IGNORECASE)
            elif name == "api_key_generic":
                def _replace_api_key(match: re.Match[str]) -> str:
                    nonlocal detected
                    detected += 1
                    full = match.group(0)
                    key_val = match.group(1)
                    return full.replace(key_val, replacement)

                result = re.sub(pattern, _replace_api_key, result, flags=re.IGNORECASE)
            else:
                new_result, count = re.subn(pattern, replacement, result, flags=re.IGNORECASE)
                if count > 0:
                    detected += count
                result = new_result
        except re.error as e:
            _logger.warning("PII filter: regex error per '%s': %s", name, e)

    if detected > 0:
        _logger.info("Enterprise DLP: %d dati sensibili oscurati con successo", detected)

    return result


def detect_pii(text: str) -> list[dict]:
    """
    Rileva PII nel testo senza oscurarlo.

    Returns:
        Lista di dict: {type, value, position}
    """
    results: list[dict] = []
    if not text:
        return results

    for name, pattern, _ in PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            val = match.group(0)
            if name == "carta_credito" and not _validate_luhn(val):
                continue
            if name == "iban" and not _validate_iban(val):
                continue
            results.append({
                "type": name,
                "value": val,
                "position": match.start(),
            })
    return results


def filter_pii_batch(texts: list[str], enabled: bool = True) -> list[str]:
    """Applica filter_pii a una lista di testi."""
    return [filter_pii(t, enabled=enabled) for t in texts]
