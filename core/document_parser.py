"""Small, deterministic parsers used by the first Ermes ingestion flow.

The parser deliberately returns plain text and source locators only.  Vectorisation
and LLM calls belong to later stages, so uploading a document never requires an
external model or network connection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile


class DocumentParseError(ValueError):
    """Raised when a supported document cannot be read safely."""


MAX_OFFICE_ARCHIVE_FILES = 10_000
MAX_OFFICE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_OFFICE_COMPRESSION_RATIO = 100


@dataclass(frozen=True)
class SourceUnit:
    """A readable source boundary that must never be crossed by a chunk."""

    text: str
    locator: str


def split_into_chunks(text: str, max_chars: int = 900, overlap_chars: int = 140) -> list[str]:
    """Split text on paragraph boundaries, preserving small readable citations."""
    normalized = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in normalized.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > max_chars:
            boundary = paragraph.rfind(" ", 0, max_chars)
            boundary = boundary if boundary > max_chars // 2 else max_chars
            chunks.append(paragraph[:boundary].strip())
            paragraph = paragraph[max(0, boundary - overlap_chars):].strip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def chunk_source_units(units: list[SourceUnit]) -> list[tuple[str, str]]:
    """Chunk every source unit independently so provenance remains precise."""
    chunks: list[tuple[str, str]] = []
    for unit in units:
        parts = split_into_chunks(unit.text)
        for index, part in enumerate(parts, start=1):
            suffix = f", parte {index}" if len(parts) > 1 else ""
            chunks.append((part, f"{unit.locator}{suffix}"))
    return chunks


def extract_text(filename: str, content: bytes) -> tuple[str, int]:
    """Return normalized text and the number of logical source units."""
    units = extract_source_units(filename, content)
    return "\n\n".join(unit.text for unit in units), len(units)


def extract_source_units(filename: str, content: bytes) -> list[SourceUnit]:
    """Extract text with source boundaries suitable for evidence citations."""
    suffix = Path(filename).suffix.lower()
    try:
        if suffix in {".txt", ".md"}:
            return _extract_text_units(content.decode("utf-8-sig", errors="replace"), suffix)
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            return [
                SourceUnit((page.extract_text() or "").strip(), f"Pagina {number}")
                for number, page in enumerate(reader.pages, start=1)
                if (page.extract_text() or "").strip()
            ]
        if suffix == ".docx":
            _validate_office_archive(content, "docx")
            from docx import Document

            document = Document(BytesIO(content))
            heading = "Documento"
            units: list[SourceUnit] = []
            for number, paragraph in enumerate(document.paragraphs, start=1):
                text = paragraph.text.strip()
                if not text:
                    continue
                if paragraph.style and paragraph.style.name.lower().startswith("heading"):
                    heading = text
                    continue
                units.append(SourceUnit(text, f"{heading}, paragrafo {number}"))
            return units
        if suffix == ".xlsx":
            _validate_office_archive(content, "xlsx")
            return _extract_xlsx_units(content)
    except Exception as error:
        raise DocumentParseError(f"Impossibile leggere il documento: {error}") from error
    raise DocumentParseError("Formato documento non supportato")


def _extract_text_units(text: str, suffix: str) -> list[SourceUnit]:
    normalized = text.strip()
    if not normalized:
        return []
    if suffix != ".md":
        return [SourceUnit(normalized, "Testo")]
    sections = re.split(r"(?m)^(#{1,6}\s+.+)$", normalized)
    units: list[SourceUnit] = []
    heading = "Documento"
    for part in sections:
        part = part.strip()
        if not part:
            continue
        if part.startswith("#"):
            heading = part.lstrip("#").strip()
        else:
            units.append(SourceUnit(part, f"Sezione: {heading}"))
    return units or [SourceUnit(normalized, "Documento")]


def _extract_xlsx_units(content: bytes) -> list[SourceUnit]:
    """Read an XLSX without adding an office-suite dependency.

    The generated workbook uses a private ZIP entry so callers can treat the
    result as a deterministic preview.  It is not a replacement for a full
    spreadsheet engine and formula values are intentionally not calculated.
    """
    with ZipFile(BytesIO(content)) as archive:
        from xml.etree import ElementTree

        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(item.itertext()).strip() for item in root.findall(f"{ns}si")]
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        worksheet_paths = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml"))
        units: list[SourceUnit] = []
        for index, sheet in enumerate(workbook.iter(f"{ns}sheet")):
            name = sheet.attrib.get("name", "Foglio")
            if index >= len(worksheet_paths):
                continue
            sheet_path = worksheet_paths[index]
            root = ElementTree.fromstring(archive.read(sheet_path))
            for row in root.findall(f".//{ns}row"):
                values: list[str] = []
                for cell in row.findall(f"{ns}c"):
                    reference = cell.attrib.get("r", "?")
                    kind = cell.attrib.get("t", "")
                    value_node = cell.find(f"{ns}v")
                    value = value_node.text if value_node is not None and value_node.text is not None else ""
                    if kind == "s" and value.isdigit() and int(value) < len(shared_strings):
                        value = shared_strings[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(cell.itertext()).strip()
                    if value:
                        values.append(f"{reference}: {value}")
                if values:
                    row_number = row.attrib.get("r", "?")
                    units.append(SourceUnit(" | ".join(values), f"Foglio {name}, riga {row_number}"))
        return units


def _validate_office_archive(content: bytes, kind: str) -> None:
    """Reject malformed or suspicious Office ZIP archives before extraction."""
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_OFFICE_ARCHIVE_FILES:
                raise DocumentParseError("Archivio Office con troppi file interni")
            uncompressed = sum(entry.file_size for entry in entries)
            if uncompressed > MAX_OFFICE_UNCOMPRESSED_BYTES:
                raise DocumentParseError("Archivio Office troppo grande dopo l'estrazione")
            for entry in entries:
                if entry.compress_size and entry.file_size / entry.compress_size > MAX_OFFICE_COMPRESSION_RATIO:
                    raise DocumentParseError("Archivio Office con rapporto di compressione non sicuro")
            names = set(archive.namelist())
            required = {"[Content_Types].xml"}
            required.add("word/document.xml" if kind == "docx" else "xl/workbook.xml")
            if not required.issubset(names):
                raise DocumentParseError("Il file ZIP non è un documento Office valido")
    except DocumentParseError:
        raise
    except Exception as error:
        raise DocumentParseError("Archivio Office non leggibile") from error
