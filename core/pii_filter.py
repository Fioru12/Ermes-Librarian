"""
pii_filter.py
Filtro Enterprise DLP (Data Loss Prevention) e PII per contesto RAG.
Rileva e oscura dati sensibili prima dell'invio all'LLM e protegge le risposte in uscita.
Supporta la configurazione dinamica dei pattern e regole Regex personalizzate.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from config import cfg

_logger = logging.getLogger(__name__)
_config_lock = threading.Lock()

# ── Pattern PII Standard ──

STANDARD_PATTERNS: dict[str, dict[str, Any]] = {
    "carta_credito": {
        "label": "Carte di Credito (Algoritmo Luhn)",
        "pattern": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
        "replacement": "[CARTA_CREDITO]",
        "default_enabled": True,
    },
    "iban": {
        "label": "IBAN (Algoritmo ISO 7064 MOD 97-10)",
        "pattern": r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b",
        "replacement": "[IBAN]",
        "default_enabled": True,
    },
    "codice_fiscale": {
        "label": "Codice Fiscale Italiano",
        "pattern": r"\b[A-Za-z]{6}\d{2}[A-Za-z]{1}\d{2}[A-Za-z]{1}\d{3}[A-Za-z]{1}\b",
        "replacement": "[CODICE_FISCALE]",
        "default_enabled": True,
    },
    "partita_iva": {
        "label": "Partita IVA",
        "pattern": r"\b(?:IT\s?)?\d{11}\b",
        "replacement": "[PARTITA_IVA]",
        "default_enabled": True,
    },
    "email": {
        "label": "Indirizzi Email",
        "pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "replacement": "[EMAIL]",
        "default_enabled": True,
    },
    "telefono_italia": {
        "label": "Numeri di Telefono (Fissi/Cellulari)",
        "pattern": r"\b(?:\+39\s?)?(?:0\d{1,4}[-\s]?\d{4,8}|3\d{2}[-\s]?\d{3,4}[-\s]?\d{3,4})\b",
        "replacement": "[TELEFONO]",
        "default_enabled": True,
    },
    "jwt_token": {
        "label": "Token JWT & Session Keys",
        "pattern": r"eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}",
        "replacement": "[JWT_TOKEN]",
        "default_enabled": True,
    },
    "api_key_generic": {
        "label": "API Key & Secret Credentials",
        "pattern": r"(?:api[_-]?key|secret[_-]?key|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{24,})['\"]?",
        "replacement": "[API_KEY]",
        "default_enabled": True,
    },
    "indirizzo_ip": {
        "label": "Indirizzi IP (IPv4)",
        "pattern": r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
        "replacement": "[IP]",
        "default_enabled": True,
    },
}


def _get_config_path() -> Path:
    data_dir = Path(getattr(cfg, "BASE_DIR", ".")) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "pii_config.json"


_cached_config: dict[str, Any] | None = None


def get_pii_config() -> dict[str, Any]:
    """Restituisce la configurazione PII/DLP corrente."""
    global _cached_config
    with _config_lock:
        if _cached_config is not None:
            return _cached_config

        config_path = _get_config_path()
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                    _cached_config = loaded
                    return loaded
            except Exception as e:
                _logger.warning("Impossibile caricare pii_config.json: %s", e)

        # Default fallback config
        enabled_patterns = {pid: data["default_enabled"] for pid, data in STANDARD_PATTERNS.items()}
        default_config = {
            "enabled_patterns": enabled_patterns,
            "custom_rules": [],
        }
        _cached_config = default_config
        return default_config


def update_pii_config(new_config: dict[str, Any]) -> dict[str, Any]:
    """Aggiorna e persiste la configurazione PII/DLP su disco."""
    global _cached_config
    with _config_lock:
        enabled_patterns = new_config.get("enabled_patterns", {})
        custom_rules = new_config.get("custom_rules", [])

        # Sanitizza custom rules
        sanitized_rules = []
        for r in custom_rules:
            if isinstance(r, dict) and r.get("name") and r.get("pattern") and r.get("replacement"):
                # Testa se la regex e' valida
                try:
                    re.compile(r["pattern"])
                    sanitized_rules.append({
                        "id": str(r.get("id") or f"custom_{len(sanitized_rules)+1}"),
                        "name": str(r["name"]).strip(),
                        "pattern": str(r["pattern"]).strip(),
                        "replacement": str(r["replacement"]).strip(),
                        "enabled": bool(r.get("enabled", True)),
                    })
                except re.error as reg_err:
                    _logger.warning("Regex personalizzata non valida '%s': %s", r.get("name"), reg_err)

        updated = {
            "enabled_patterns": enabled_patterns,
            "custom_rules": sanitized_rules,
        }
        _cached_config = updated

        try:
            config_path = _get_config_path()
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(updated, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _logger.error("Errore salvataggio pii_config.json: %s", e)

        return updated


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
    rearranged = cleaned[4:] + cleaned[:4]
    numeric_str = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric_str) % 97 == 1
    except ValueError:
        return False


def filter_pii(text: str, enabled: bool = True) -> str:
    """
    Applica il filtro PII/DLP al testo in base alla configurazione attiva.
    Oscura i dati sensibili con segnaposto.
    """
    if not enabled or not text:
        return text

    config = get_pii_config()
    enabled_map = config.get("enabled_patterns", {})
    custom_rules = config.get("custom_rules", [])

    result = text
    detected = 0

    # 1. Filtra pattern standard abilitati
    for pid, meta in STANDARD_PATTERNS.items():
        if not enabled_map.get(pid, meta["default_enabled"]):
            continue

        pattern = meta["pattern"]
        replacement = meta["replacement"]

        try:
            if pid == "carta_credito":
                def _replace_cc(match: re.Match[str]) -> str:
                    nonlocal detected
                    matched = match.group(0)
                    if _validate_luhn(matched):
                        detected += 1
                        return replacement
                    return matched

                result = re.sub(pattern, _replace_cc, result)
            elif pid == "iban":
                def _replace_iban(match: re.Match[str]) -> str:
                    nonlocal detected
                    matched = match.group(0)
                    if _validate_iban(matched):
                        detected += 1
                        return replacement
                    return matched

                result = re.sub(pattern, _replace_iban, result, flags=re.IGNORECASE)
            elif pid == "api_key_generic":
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
            _logger.warning("PII filter: regex error per '%s': %s", pid, e)

    # 2. Filtra regole custom abilitate
    for rule in custom_rules:
        if not rule.get("enabled", True):
            continue

        pattern = rule.get("pattern", "")
        replacement = rule.get("replacement", "[DATO_RISERVATO]")
        if not pattern:
            continue

        try:
            new_result, count = re.subn(pattern, replacement, result, flags=re.IGNORECASE)
            if count > 0:
                detected += count
            result = new_result
        except re.error as e:
            _logger.warning("PII filter: regex error per custom rule '%s': %s", rule.get("name"), e)

    if detected > 0:
        _logger.info("Enterprise DLP: %d dati sensibili oscurati con successo", detected)

    return result


def detect_pii(text: str) -> list[dict[str, Any]]:
    """
    Rileva PII nel testo senza oscurarlo.
    Restituisce una lista di oggetti dict: {type, label, value, position}
    """
    results: list[dict[str, Any]] = []
    if not text:
        return results

    config = get_pii_config()
    enabled_map = config.get("enabled_patterns", {})
    custom_rules = config.get("custom_rules", [])

    # Standard patterns
    for pid, meta in STANDARD_PATTERNS.items():
        if not enabled_map.get(pid, meta["default_enabled"]):
            continue
        pattern = meta["pattern"]
        for match in re.finditer(pattern, text, re.IGNORECASE):
            val = match.group(0)
            if pid == "carta_credito" and not _validate_luhn(val):
                continue
            if pid == "iban" and not _validate_iban(val):
                continue
            results.append({
                "type": pid,
                "label": meta["label"],
                "value": val,
                "position": match.start(),
            })

    # Custom rules
    for rule in custom_rules:
        if not rule.get("enabled", True):
            continue
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        try:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                results.append({
                    "type": f"custom_{rule.get('id')}",
                    "label": f"Custom: {rule.get('name')}",
                    "value": match.group(0),
                    "position": match.start(),
                })
        except re.error:
            pass

    return results


def filter_pii_batch(texts: list[str], enabled: bool = True) -> list[str]:
    """Applica filter_pii a una lista di testi."""
    return [filter_pii(t, enabled=enabled) for t in texts]
