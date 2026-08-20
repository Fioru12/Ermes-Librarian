from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from core.document_parser import chunk_source_units, DocumentParseError, extract_source_units, extract_text, split_into_chunks


def test_extracts_text_and_markdown():
    text, units = extract_text("procedura.md", b"# Procedura\n\nContattare HR")

    assert text == "Contattare HR"
    assert units == 1


def test_extracts_shared_strings_from_xlsx():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Scadenza</t></si><si><t>31 dicembre</t></si></sst>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Scadenze" sheetId="1" r:id="rId1" /></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" /></Relationships>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row></sheetData></worksheet>',
        )

    text, units = extract_text("scadenze.xlsx", buffer.getvalue())

    assert text == "A1: Scadenza | B1: 31 dicembre"
    assert units == 1


def test_rejects_unsupported_file_type():
    with pytest.raises(DocumentParseError):
        extract_text("immagine.png", b"not an image")


def test_rejects_a_zip_disguised_as_xlsx():
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("note.txt", "non è un foglio Excel")

    with pytest.raises(DocumentParseError):
        extract_text("falso.xlsx", buffer.getvalue())


def test_chunks_keep_paragraphs_and_bound_size():
    chunks = split_into_chunks("Uno.\n\n" + ("Due " * 400), max_chars=100, overlap_chars=20)

    assert len(chunks) > 2
    assert all(len(chunk) <= 100 for chunk in chunks)


def test_markdown_sections_are_preserved_as_chunk_citations():
    units = extract_source_units("policy.md", b"# Ferie\nRichiedere ferie via portale.\n\n# Spese\nConservare la ricevuta.")
    chunks = chunk_source_units(units)

    assert chunks[0][1] == "Sezione: Ferie"
    assert chunks[1][1] == "Sezione: Spese"


def test_public_demo_corpus_is_parseable_and_has_section_locators():
    corpus = Path(__file__).parents[1] / "examples" / "demo-corpus"
    documents = sorted(corpus.glob("*.md"))

    assert {document.name for document in documents} >= {
        "employee-handbook.md",
        "expense-policy.md",
        "it-access-policy.md",
    }
    for document in documents:
        units = extract_source_units(document.name, document.read_bytes())
        chunks = chunk_source_units(units)

        assert chunks
        assert all(locator.startswith("Sezione:") for _, locator in chunks)
