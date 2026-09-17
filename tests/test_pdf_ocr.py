"""PDF scansionati: le pagine senza livello testo passano dall'OCR.

Fino al 18 settembre 2026 il parser provava pytesseract sulle immagini
incorporate (`page.images`), senza dipendenza dichiarata, senza binario nel
Dockerfile e senza test: un PDF da scanner veniva indicizzato con zero
passaggi e nessuna segnalazione. Ora la pagina viene rasterizzata per
intero e il motore e' sostituibile: qui si sostituisce, perche' Tesseract
non e' un requisito della suite — cio' che si verifica e' il percorso.
"""

import io
import logging

import pytest
from pypdf import PdfWriter

import config
from core import document_parser, ocr


def _pdf_with_blank_pages(n: int) -> bytes:
    writer = PdfWriter()
    for _ in range(n):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def motore_finto(monkeypatch):
    """OCR disponibile, che 'legge' un testo dipendente dalla pagina."""
    letture: list[int] = []

    def _ocr(content, page_index, *, lang, dpi):
        letture.append(page_index)
        assert lang == "ita+eng"
        return f"testo riconosciuto pagina {page_index + 1}"

    monkeypatch.setattr(ocr, "available", lambda: (True, ""))
    monkeypatch.setattr(ocr, "ocr_pdf_page", _ocr)
    return letture


def _cfg(monkeypatch, **override):
    monkeypatch.setattr("config.cfg", config.cfg.replace(**override))


def test_scanned_pages_become_cited_units(monkeypatch, motore_finto):
    _cfg(monkeypatch, OCR_ENABLED=True, OCR_MAX_PAGES=50)
    units = document_parser.extract_source_units("scan.pdf", _pdf_with_blank_pages(2))
    assert [u.locator for u in units] == ["Pagina 1 (scansione, OCR)", "Pagina 2 (scansione, OCR)"]
    assert units[0].text == "testo riconosciuto pagina 1"
    assert motore_finto == [0, 1]


def test_page_limit_is_respected_and_logged(monkeypatch, motore_finto, caplog):
    _cfg(monkeypatch, OCR_ENABLED=True, OCR_MAX_PAGES=1)
    with caplog.at_level(logging.WARNING, logger="ermes.parser"):
        units = document_parser.extract_source_units("scan.pdf", _pdf_with_blank_pages(3))
    assert len(units) == 1 and motore_finto == [0]
    assert "2 pagine senza testo saltate" in caplog.text


def test_missing_engine_is_reported_not_silent(monkeypatch, caplog):
    _cfg(monkeypatch, OCR_ENABLED=True)
    monkeypatch.setattr(ocr, "available", lambda: (False, "binario Tesseract non trovato (tesseract)"))
    with caplog.at_level(logging.WARNING, logger="ermes.parser"):
        units = document_parser.extract_source_units("scan.pdf", _pdf_with_blank_pages(2))
    assert units == []
    assert "2 pagine senza testo non lette: OCR non disponibile" in caplog.text


def test_disabled_by_configuration(monkeypatch, motore_finto):
    _cfg(monkeypatch, OCR_ENABLED=False)
    assert document_parser.extract_source_units("scan.pdf", _pdf_with_blank_pages(1)) == []
    assert motore_finto == []


def test_render_pdf_page_produces_an_image_at_the_requested_dpi():
    """Il rasterizzatore e' reale (pypdfium2): a 72 dpi una pagina 200x200 pt
    e' 200x200 px."""
    image = ocr.render_pdf_page(_pdf_with_blank_pages(1), 0, dpi=72)
    assert image.size == (200, 200)


def test_engine_failure_on_one_page_does_not_lose_the_document(monkeypatch):
    _cfg(monkeypatch, OCR_ENABLED=True)
    monkeypatch.setattr(ocr, "available", lambda: (True, ""))

    def _ocr(content, page_index, *, lang, dpi):
        if page_index == 0:
            raise RuntimeError("tesseract crashed")
        return "ok"

    monkeypatch.setattr(ocr, "ocr_pdf_page", _ocr)
    units = document_parser.extract_source_units("scan.pdf", _pdf_with_blank_pages(2))
    assert [u.locator for u in units] == ["Pagina 2 (scansione, OCR)"]
