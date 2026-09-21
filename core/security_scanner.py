"""
core/security_scanner.py
Enterprise Document Security & Malware Scanner for Ermes Knowledge.

Inspects document content before parsing or persistence to prevent:
- PDF embedded JavaScript, /Launch actions, and malicious embedded files.
- Office OpenXML macro executables (vbaProject.bin, OLE streams).
- Decompression bombs (Zip bombs / archive ratio attacks).
- CSV / Formula Injection attacks (DDE execution payloads).
- Binary or null-byte poisoning in plaintext documents.
"""

from __future__ import annotations

import io
import logging
import os
import re
import zipfile
from dataclasses import dataclass

_logger = logging.getLogger("ermes.security_scanner")

# Limiti per mitigazione Decompression Bomb
MAX_COMPRESSION_RATIO = 100.0  # Rapporto max decompresso/compresso
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB max decompressi da archivio

# Pattern di PDF Action sospette
_PDF_DANGEROUS_PATTERNS = [
    (rb"/JavaScript\b", "PDF_JAVASCRIPT", "Script JavaScript incorporato nel PDF"),
    (rb"/JS\b", "PDF_JS_STREAM", "Stream di esecuzione JavaScript nel PDF"),
    (rb"/Launch\b", "PDF_LAUNCH_ACTION", "Azione di esecuzione applicazione esterna (/Launch)"),
    (rb"/EmbeddedFiles\b", "PDF_EMBEDDED_FILES", "File eseguibili o payload incorporati nel PDF"),
    (rb"/SubmitForm\b", "PDF_SUBMIT_FORM", "Esfiltrazione dati automatica tramite form (/SubmitForm)"),
    (rb"/URI\s*\([^)]*(cmd|powershell|mshta|cscript|wscript|file:\/\/)", "PDF_MALICIOUS_URI", "URI con esecuzione comandi nel PDF"),
]

# Pattern per CSV / Formula Injection (DDE)
_CSV_INJECTION_RE = re.compile(
    r"(?:^|[,;\t])\s*(?:[=\+\-@](?:[^\r\n,;]*[|!]|(?:\s*|['\"])(?:cmd|powershell|cscript|wscript|mshta|calc|rundll32|regsvr32|curl|wget|certutil)\b)|=?[a-z0-9_.]*\|'?[^'\r\n]+'?!|\b(?:DDE|DDEAUTO)\b\s*\()",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class SecurityScanResult:
    """Risultato della scansione di sicurezza del file."""

    is_safe: bool
    threat_name: str | None = None
    details: str = ""


ScanResult = SecurityScanResult


def scan_pdf(content: bytes) -> SecurityScanResult:
    """Ispeziona il PDF alla ricerca di exploit noti, JavaScript e azioni /Launch."""
    for pattern, threat_name, desc in _PDF_DANGEROUS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return SecurityScanResult(is_safe=False, threat_name=threat_name.lower(), details=desc)
    return SecurityScanResult(is_safe=True)


def scan_zip_archive(
    content: bytes,
    max_ratio: float = MAX_COMPRESSION_RATIO,
    max_uncompressed: int = MAX_TOTAL_UNCOMPRESSED_BYTES,
) -> SecurityScanResult:
    """Ispeziona archivi ZIP per decompression bomb, path traversal ed eseguibili."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            total_uncompressed = 0
            compressed_size = max(1, len(content))

            for info in zf.infolist():
                total_uncompressed += info.file_size
                name = info.filename

                # Path traversal check
                if ".." in name or name.startswith("/") or name.startswith("\\"):
                    return SecurityScanResult(
                        is_safe=False,
                        threat_name="archive_path_traversal",
                        details=f"Path traversal rilevato nell'archivio ({name})",
                    )

                filename_lower = name.lower()

                # 1. Rilevamento macro VBA
                if "vbaproject.bin" in filename_lower:
                    return SecurityScanResult(
                        is_safe=False,
                        threat_name="office_vba_macro",
                        details=f"Macro VBA rilevata nell'archivio Office ({info.filename})",
                    )

                # 2. Rilevamento file eseguibili / script incorporati
                ext = os.path.splitext(filename_lower)[1]
                if ext in {".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".scr", ".com", ".pif"}:
                    return SecurityScanResult(
                        is_safe=False,
                        threat_name="office_embedded_executable",
                        details=f"File eseguibile/script incorporato non consentito ({info.filename})",
                    )

            # 3. Protezione Decompression Bomb
            if total_uncompressed > max_uncompressed:
                return SecurityScanResult(
                    is_safe=False,
                    threat_name="zip_bomb_size_exceeded",
                    details=f"Dimensione decompressa eccessiva: {total_uncompressed / (1024*1024):.1f} MB",
                )

            ratio = total_uncompressed / compressed_size
            if ratio > max_ratio and total_uncompressed > 1024 * 1024:
                return SecurityScanResult(
                    is_safe=False,
                    threat_name="zip_bomb_ratio_exceeded",
                    details=f"Rapporto di compressione anomalo ({ratio:.1f}:1), possibile zip bomb",
                )

    except zipfile.BadZipFile:
        return SecurityScanResult(
            is_safe=False,
            threat_name="corrupt_archive",
            details="Archivio OpenXML/ZIP corrotto o non conforme",
        )

    return SecurityScanResult(is_safe=True)


def scan_office(filename: str, content: bytes) -> SecurityScanResult:
    """Ispeziona documenti OpenXML (DOCX, XLSX, PPTX)."""
    return scan_zip_archive(content)


def scan_csv(content: bytes) -> SecurityScanResult:
    """Ispeziona file CSV per CSV Formula / DDE Injection."""
    if b"\x00" in content:
        return SecurityScanResult(
            is_safe=False,
            threat_name="null_byte_poisoning",
            details="Il file contiene byte nulli (0x00)",
        )

    try:
        text = content.decode("utf-8", errors="ignore")
        if _CSV_INJECTION_RE.search(text):
            return SecurityScanResult(
                is_safe=False,
                threat_name="csv_formula_injection",
                details="Rilevata formula malevola CSV/DDE con esecuzione comandi di sistema",
            )
    except Exception:
        pass

    return SecurityScanResult(is_safe=True)


def scan_document(filename: str, content: bytes) -> SecurityScanResult:
    """Scansiona il documento binario alla ricerca di minacce informatiche ed exploit.

    Restituisce SecurityScanResult indicando se il file è sicuro o quale minaccia è stata rilevata.
    """
    if not content:
        return SecurityScanResult(is_safe=False, threat_name="empty_file", details="Il file è vuoto (0 byte)")

    ext = os.path.splitext(filename.strip().lower())[1]

    if ext == ".pdf":
        return scan_pdf(content)

    if ext in {".docx", ".xlsx", ".pptx"}:
        return scan_office(filename, content)

    if ext == ".csv":
        return scan_csv(content)

    if ext in {".txt", ".md", ".markdown", ".rtf"}:
        if b"\x00" in content:
            return SecurityScanResult(
                is_safe=False,
                threat_name="null_byte_poisoning",
                details="Il file testuale contiene byte nulli (0x00)",
            )
        return SecurityScanResult(is_safe=True)

    # Estensione non supportata o sconosciuta
    return SecurityScanResult(is_safe=True)
