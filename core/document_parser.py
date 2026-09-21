"""Small, deterministic parsers used by the first Ermes ingestion flow.

The parser deliberately returns plain text and source locators only.  Vectorisation
and LLM calls belong to later stages, so uploading a document never requires an
external model or network connection.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

_logger = logging.getLogger("ermes.parser")


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


def split_into_chunks(text: str, max_chars: int | None = None, overlap_chars: int | None = None) -> list[str]:
    """Split text on paragraph boundaries, preserving small readable citations.

    I valori vengono dalla configurazione (ERMES_CHUNK_SIZE, ERMES_CHUNK_OVERLAP).
    Erano dichiarati nel config e non letti da nessuna riga di codice: chi li
    impostava non cambiava la dimensione dei chunk, e nulla glielo diceva.
    """
    from config import cfg

    max_chars = int(max_chars if max_chars is not None else getattr(cfg, "CHUNK_SIZE", 900))
    overlap_chars = int(overlap_chars if overlap_chars is not None else getattr(cfg, "CHUNK_OVERLAP", 140))
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
            # Prefer sentence boundaries (. ! ? \n) over simple whitespace
            sentence_boundary = -1
            for sep in (". ", ".\n", "! ", "? ", "\n"):
                pos = paragraph.rfind(sep, max_chars // 2, max_chars)
                if pos != -1:
                    sentence_boundary = max(sentence_boundary, pos + len(sep))
            boundary = sentence_boundary if sentence_boundary != -1 else paragraph.rfind(" ", 0, max_chars)
            boundary = boundary if boundary > max_chars // 2 else max_chars
            chunks.append(paragraph[:boundary].strip())
            paragraph = paragraph[max(0, boundary - overlap_chars) :].strip()
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
        if suffix in {".html", ".htm"}:
            return _extract_html_units(content)
        if suffix in {".json", ".jsonl"}:
            return _extract_json_units(content, suffix)
        if suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            units: list[SourceUnit] = []
            ocr = _OcrSession(content)
            for number, page in enumerate(reader.pages, start=1):
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    units.append(SourceUnit(page_text, f"Pagina {number}"))
                    continue
                ocr_text = ocr.page(number)
                if ocr_text:
                    units.append(SourceUnit(ocr_text, f"Pagina {number} (scansione, OCR)"))
            ocr.report()
            return units
        if suffix == ".docx":
            _validate_office_archive(content, "docx")
            from docx import Document

            document = Document(BytesIO(content))
            heading = "Documento"
            docx_units: list[SourceUnit] = []
            for number, paragraph in enumerate(document.paragraphs, start=1):
                text = paragraph.text.strip()
                if not text:
                    continue
                if paragraph.style and paragraph.style.name.lower().startswith("heading"):
                    heading = text
                    continue
                docx_units.append(SourceUnit(text, f"{heading}, paragrafo {number}"))

            # Estrazione tabelle strutturate DOCX
            for t_idx, table in enumerate(document.tables, start=1):
                table_rows: list[list[str]] = []
                for row in table.rows:
                    row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    deduped: list[str] = []
                    for c in row_cells:
                        if not deduped or c != deduped[-1]:
                            deduped.append(c)
                    if any(c for c in deduped):
                        table_rows.append(deduped)

                if table_rows:
                    header = table_rows[0]
                    formatted_lines = [" | ".join(header), " | ".join(["---"] * len(header))]
                    for r in table_rows[1:]:
                        padded = r + [""] * max(0, len(header) - len(r))
                        formatted_lines.append(" | ".join(padded[: len(header)]))
                    table_md = "\n".join(formatted_lines)
                    docx_units.append(SourceUnit(table_md, f"{heading}, Tabella {t_idx}"))

            return docx_units
        if suffix == ".xlsx":
            _validate_office_archive(content, "xlsx")
            return _extract_xlsx_units(content)
        if suffix == ".pptx":
            _validate_office_archive(content, "pptx")
            return _extract_pptx_units(content)
        if suffix == ".csv":
            return _extract_csv_units(content)
        if suffix == ".rtf":
            return _extract_rtf_units(content)
    except Exception as error:
        raise DocumentParseError(f"Impossibile leggere il documento: {error}") from error
    raise DocumentParseError("Formato documento non supportato")


class _OcrSession:
    """OCR delle pagine di un PDF prive di livello testo, con i limiti del config.

    Una sessione per documento: decide una volta se l'OCR e' disponibile,
    conta le pagine lavorate contro ERMES_OCR_MAX_PAGES e a fine documento
    scrive nel log cosa e' stato saltato e perche'. Prima del 18 settembre
    2026 una pagina scansionata spariva in silenzio.
    """

    def __init__(self, content: bytes) -> None:
        from config import cfg
        from core import ocr

        self._content = content
        self._lang = getattr(cfg, "OCR_LANG", "ita+eng")
        self._dpi = int(getattr(cfg, "OCR_DPI", 200))
        self._max_pages = int(getattr(cfg, "OCR_MAX_PAGES", 50))
        self._done = 0
        self._skipped_limit: list[int] = []
        self._skipped_unavailable: list[int] = []
        if not getattr(cfg, "OCR_ENABLED", True):
            self._available, self._reason = False, "disattivato (ERMES_OCR_ENABLED=0)"
        else:
            self._available, self._reason = ocr.available()

    def page(self, number: int) -> str:
        if not self._available:
            self._skipped_unavailable.append(number)
            return ""
        if self._done >= self._max_pages:
            self._skipped_limit.append(number)
            return ""
        from core import ocr

        self._done += 1
        try:
            return ocr.ocr_pdf_page(self._content, number - 1, lang=self._lang, dpi=self._dpi)
        except Exception as error:
            _logger.warning("OCR fallito sulla pagina %d: %s", number, error)
            return ""

    def report(self) -> None:
        if self._skipped_unavailable:
            _logger.warning(
                "%d pagine senza testo non lette: OCR non disponibile (%s)",
                len(self._skipped_unavailable),
                self._reason,
            )
        if self._skipped_limit:
            _logger.warning(
                "%d pagine senza testo saltate: oltre ERMES_OCR_MAX_PAGES=%d",
                len(self._skipped_limit),
                self._max_pages,
            )


def _extract_csv_units(content: bytes) -> list[SourceUnit]:
    import csv
    import io

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    header = rows[0] if len(rows) > 1 else None
    units: list[SourceUnit] = []
    data_rows = rows[1:] if header else rows
    for idx, row in enumerate(data_rows, start=2 if header else 1):
        if not any(cell.strip() for cell in row):
            continue
        if header and len(header) == len(row):
            formatted_row = " | ".join(f"{h.strip()}: {c.strip()}" for h, c in zip(header, row) if c.strip())
        else:
            formatted_row = " | ".join(c.strip() for c in row if c.strip())
        if formatted_row:
            units.append(SourceUnit(formatted_row, f"Riga {idx}"))
    return units or [SourceUnit(text[:2000], "Documento CSV")]


def _strip_rtf(rtf: str) -> str:
    # Remove groups like font tables, color tables, stylesheets, info, pict, etc.
    rtf = re.sub(r"{\\\*(?:[^{}]|{[^{}]*})*}", "", rtf)
    rtf = re.sub(r"{\\(?:fonttbl|colortbl|stylesheet|info|pict|header|footer)[^{}]*(?:{[^{}]*}[^{}]*)*}", "", rtf)
    # Hex character escapes \'hh
    rtf = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), rtf)
    # Paragraph and line breaks
    rtf = re.sub(r"\\par\b|\\line\b", "\n", rtf)
    rtf = re.sub(r"\\tab\b", "\t", rtf)
    # Strip remaining RTF control words
    rtf = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", rtf)
    # Handle escaped characters
    rtf = rtf.replace(r"\{", "{").replace(r"\}", "}").replace(r"\\", "\\")
    # Strip remaining formatting braces
    rtf = re.sub(r"[{}]", "", rtf)
    return "\n".join(line.strip() for line in rtf.splitlines() if line.strip())


def _extract_rtf_units(content: bytes) -> list[SourceUnit]:
    try:
        from striprtf.striprtf import rtf_to_text

        raw_text = content.decode("latin-1", errors="replace")
        clean_text = rtf_to_text(raw_text).strip()
    except Exception:
        raw_text = content.decode("latin-1", errors="replace")
        clean_text = _strip_rtf(raw_text).strip()

    if not clean_text:
        return []
    return [SourceUnit(clean_text, "Documento RTF")]


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


def _parse_office_xml(data: bytes):
    """Parse XML from an uploaded Office archive, refusing document type
    declarations.

    `xml.etree.ElementTree` expands internal entities, so a few kilobytes of
    nested entity definitions inside an uploaded .xlsx expand to gigabytes in
    memory — the classic "billion laughs" denial of service. Verified before
    this guard existed: a 1.157-byte file produced 10.001 characters with only
    four nesting levels.

    A legitimate OOXML part never carries a DTD, so refusing `<!DOCTYPE`
    outright removes the entire entity-expansion class without pulling in a
    third-party parser. Documents are untrusted input: this is the product's
    fourth stated principle, and the parser has to honour it too.
    """
    from xml.etree import ElementTree

    # The declaration precedes the root element, but nothing bounds how much
    # whitespace, comments or processing instructions may precede it: until
    # 21 September 2026 only the first 4096 bytes were inspected, and 4097
    # bytes of padding walked straight past the check. A bytes scan of the
    # whole part costs microseconds; the parts are capped at 100 MB by
    # _validate_office_archive anyway.
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise DocumentParseError("Il file contiene una dichiarazione XML non ammessa")
    # nosec B314 — bandit segnala ElementTree su input non fidato. Qui la classe
    # di attacco (espansione di entita') e' gia' esclusa dal controllo sopra,
    # che rifiuta qualunque DTD, ed e' coperta da un test di regressione:
    # tests/test_document_parser.py::test_xlsx_with_entity_declarations_is_rejected
    return ElementTree.fromstring(data)  # nosec B314


def _extract_xlsx_units(content: bytes) -> list[SourceUnit]:
    """Read an XLSX without adding an office-suite dependency.

    The generated workbook uses a private ZIP entry so callers can treat the
    result as a deterministic preview.  It is not a replacement for a full
    spreadsheet engine and formula values are intentionally not calculated.
    """
    with ZipFile(BytesIO(content)) as archive:
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = _parse_office_xml(archive.read("xl/sharedStrings.xml"))
            shared_strings = ["".join(item.itertext()).strip() for item in root.findall(f"{ns}si")]
        workbook = _parse_office_xml(archive.read("xl/workbook.xml"))
        worksheet_paths = sorted(
            name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")
        )
        units: list[SourceUnit] = []
        for index, sheet in enumerate(workbook.iter(f"{ns}sheet")):
            name = sheet.attrib.get("name", "Foglio")
            if index >= len(worksheet_paths):
                continue
            sheet_path = worksheet_paths[index]
            root = _parse_office_xml(archive.read(sheet_path))
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


def _extract_pptx_units(content: bytes) -> list[SourceUnit]:
    """Read a PPTX without adding an office-suite dependency.

    Same approach as `_extract_xlsx_units`: raw OOXML parsing guarded by
    `_parse_office_xml` (entity-expansion safe). Each slide becomes a unit
    so citations point at "Slide N". Notes slides are included as part of
    the slide unit because they carry presenter context.
    """
    with ZipFile(BytesIO(content)) as archive:
        slide_paths = sorted(
            (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda name: int(re.search(r"slide(\d+)\.xml", name).group(1)),  # type: ignore[union-attr]
        )
        units: list[SourceUnit] = []
        for index, slide_path in enumerate(slide_paths, start=1):
            root = _parse_office_xml(archive.read(slide_path))
            a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
            paragraphs: list[str] = []
            for paragraph in root.iter(f"{a}p"):
                text = " ".join(run.text.strip() for run in paragraph.iter(f"{a}t") if run.text and run.text.strip())
                if text:
                    paragraphs.append(text)
            if paragraphs:
                units.append(SourceUnit("\n".join(paragraphs), f"Slide {index}"))
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
            required_for_kind = {
                "docx": "word/document.xml",
                "xlsx": "xl/workbook.xml",
                "pptx": "ppt/presentation.xml",
            }
            required.add(required_for_kind[kind])
            if not required.issubset(names):
                raise DocumentParseError("Il file ZIP non è un documento Office valido")
    except DocumentParseError:
        raise
    except Exception as error:
        raise DocumentParseError("Archivio Office non leggibile") from error


class _HTMLStructureExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.units: list[SourceUnit] = []
        self._current_heading: str = "Documento"
        self._current_text: list[str] = []
        self._in_table = False
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._table_count = 0
        self._ignore_stack = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in {"script", "style", "head", "noscript"}:
            self._ignore_stack += 1
            return
        if self._ignore_stack > 0:
            return

        if tag_lower in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_text()
        elif tag_lower == "table":
            self._flush_text()
            self._in_table = True
            self._table_rows = []
            self._table_count += 1
        elif tag_lower == "tr":
            self._current_row = []
        elif tag_lower in {"td", "th"}:
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in {"script", "style", "head", "noscript"}:
            if self._ignore_stack > 0:
                self._ignore_stack -= 1
            return
        if self._ignore_stack > 0:
            return

        if tag_lower in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading_text = "".join(self._current_text).strip()
            self._current_text = []
            if heading_text:
                self._current_heading = heading_text
        elif tag_lower in {"p", "div", "li", "blockquote"}:
            self._flush_text()
        elif tag_lower in {"td", "th"}:
            cell_text = "".join(self._current_cell).strip().replace("\n", " ")
            self._current_row.append(cell_text)
            self._current_cell = []
        elif tag_lower == "tr":
            if any(self._current_row):
                self._table_rows.append(self._current_row)
            self._current_row = []
        elif tag_lower == "table":
            self._in_table = False
            self._flush_table()

    def handle_data(self, data: str) -> None:
        if self._ignore_stack > 0:
            return
        if self._in_table:
            self._current_cell.append(data)
        else:
            self._current_text.append(data)

    def _flush_text(self) -> None:
        raw = "".join(self._current_text).strip()
        self._current_text = []
        cleaned = re.sub(r"\s+", " ", raw).strip()
        if cleaned:
            self.units.append(SourceUnit(cleaned, f"Sezione: {self._current_heading}"))

    def _flush_table(self) -> None:
        if not self._table_rows:
            return
        header = self._table_rows[0]
        formatted = [" | ".join(header), " | ".join(["---"] * len(header))]
        for row in self._table_rows[1:]:
            padded = row + [""] * max(0, len(header) - len(row))
            formatted.append(" | ".join(padded[: len(header)]))
        table_str = "\n".join(formatted)
        self.units.append(SourceUnit(table_str, f"Sezione: {self._current_heading}, Tabella {self._table_count}"))
        self._table_rows = []

    def finish(self) -> list[SourceUnit]:
        self._flush_text()
        self._flush_table()
        return self.units


def _extract_html_units(content: bytes) -> list[SourceUnit]:
    """Estrae unità strutturate con titoli, paragrafi e tabelle da documenti HTML."""
    text = content.decode("utf-8", errors="replace")
    parser = _HTMLStructureExtractor()
    parser.feed(text)
    units = parser.finish()
    if not units:
        # Fallback stripped
        clean_text = re.sub(r"<[^>]+>", " ", text)
        normalized = re.sub(r"\s+", " ", clean_text).strip()
        return [SourceUnit(normalized, "Documento HTML")] if normalized else []
    return units


def _format_json_object(val: Any) -> str:
    if isinstance(val, dict):
        parts = []
        for k, v in val.items():
            parts.append(f"{k}: {_format_json_object(v)}")
        return " | ".join(parts)
    elif isinstance(val, list):
        return ", ".join(_format_json_object(x) for x in val)
    return str(val)


def _extract_json_units(content: bytes, suffix: str = ".json") -> list[SourceUnit]:
    """Estrae record e proprietà strutturate da file JSON e JSONL."""
    text = content.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return []

    units: list[SourceUnit] = []

    # Rileva formato JSON Lines (.jsonl o multiriga di oggetti JSON)
    if suffix == ".jsonl" or ("\n" in text and not text.startswith("[")):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        parsed_jsonl: list[SourceUnit] = []
        is_all_json = True
        for idx, line in enumerate(lines, start=1):
            try:
                obj = json.loads(line)
                formatted = _format_json_object(obj)
                if formatted:
                    parsed_jsonl.append(SourceUnit(formatted, f"Record JSONL {idx}"))
            except Exception:
                is_all_json = False
                break
        if is_all_json and parsed_jsonl:
            return parsed_jsonl

    try:
        data = json.loads(text)
    except Exception as e:
        raise DocumentParseError(f"JSON non valido: {e}") from e

    if isinstance(data, list):
        for idx, item in enumerate(data, start=1):
            formatted = _format_json_object(item)
            if formatted:
                units.append(SourceUnit(formatted, f"Elemento {idx}"))
    elif isinstance(data, dict):
        for key, val in data.items():
            formatted = f"{key}: {_format_json_object(val)}"
            units.append(SourceUnit(formatted, f"Proprietà '{key}'"))
    return units or [SourceUnit(text[:2000], "Documento JSON")]
