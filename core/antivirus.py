"""
core/antivirus.py
Enterprise Antivirus & Malware Scanner per Ermes Knowledge.

Fornisce scansione in-memory via demone ClamAV (protocollo TCP INSTREAM su porta 3310).
Non richiede librerie C esterne né dipendenze aggiuntive (usa il modulo socket standard).
Supporta modalità fail-open (default resiliente) e fail-closed (ambienti ad alta sicurezza).
"""

from __future__ import annotations

import contextlib
import logging
import re
import socket
import struct
from dataclasses import dataclass

from config import cfg

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    is_clean: bool
    virus_name: str | None = None
    details: str = ""


class AntivirusScanError(Exception):
    """Sollevata quando il servizio antivirus non è raggiungibile in modalità fail-closed."""


def scan_bytes_clamav(
    content: bytes,
    host: str = "localhost",
    port: int = 3310,
    timeout: float = 10.0,
) -> ScanResult:
    """Invia il contenuto binario a un demone clamd via protocollo zINSTREAM.

    Format:
      - Send b"zINSTREAM\\x00"
      - Per ogni chunk: 4-byte big-endian length + chunk
      - Termina con 4-byte 0 (b"\\x00\\x00\\x00\\x00")
      - Risposta: "stream: OK" oppure "stream: <VirusName> FOUND"
    """
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(b"zINSTREAM\x00")
        chunk_size = 8192
        for offset in range(0, len(content), chunk_size):
            chunk = content[offset : offset + chunk_size]
            sock.sendall(struct.pack("!I", len(chunk)) + chunk)
        # Terminatore fine stream
        sock.sendall(b"\x00\x00\x00\x00")

        # Legge la risposta
        response_bytes = b""
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                break
            response_bytes += chunk
            if b"\n" in chunk or b"\x00" in chunk:
                break

    response_text = response_bytes.decode("utf-8", errors="replace").strip().strip("\x00")
    if "FOUND" in response_text:
        match = re.search(r"stream:\s*(.+?)\s+FOUND", response_text, re.IGNORECASE)
        virus_name = match.group(1).strip() if match else "Infected"
        return ScanResult(is_clean=False, virus_name=virus_name, details=response_text)
    if "OK" in response_text:
        return ScanResult(is_clean=True, details="Clean")

    # Risposta anomala o codice di errore demone
    return ScanResult(is_clean=False, virus_name="UnknownThreat", details=response_text)


def scan_document(content: bytes, filename: str = "", actor: str = "system") -> ScanResult:
    """Scansiona il documento caricato. Se disabilitato, ritorna immediatamente esito pulito.

    Se viene rilevato un malware, registra automaticamente un evento di audit firmato.
    """
    if not getattr(cfg, "CLAMAV_ENABLED", False):
        return ScanResult(is_clean=True, details="Antivirus disattivato da configurazione")

    host = getattr(cfg, "CLAMAV_HOST", "localhost")
    port = int(getattr(cfg, "CLAMAV_PORT", 3310))
    timeout = float(getattr(cfg, "CLAMAV_TIMEOUT", 10.0))
    fail_closed = bool(getattr(cfg, "CLAMAV_FAIL_CLOSED", False))

    try:
        result = scan_bytes_clamav(content, host=host, port=port, timeout=timeout)
    except Exception as err:
        if fail_closed:
            _logger.error("Scansione antivirus fallita e fail-closed attivo: %s", err)
            raise AntivirusScanError(f"Scansione antivirus fallita (fail-closed attivo): {err}") from err
        _logger.warning("Demone antivirus ClamAV non raggiungibile (%s:%s) - fail-open attivo: %s", host, port, err)
        return ScanResult(is_clean=True, details=f"Antivirus non raggiungibile (fail-open): {err}")

    if not result.is_clean:
        _logger.warning("MALWARE BLOCCATO su upload '%s' da '%s': %s", filename, actor, result.virus_name)
        with contextlib.suppress(Exception):
            from core.governance import append_audit

            append_audit(
                cfg.AUDIT_FILE,
                "security_malware_blocked",
                actor,
                {"filename": filename, "virus": result.virus_name, "details": result.details},
            )

    return result
