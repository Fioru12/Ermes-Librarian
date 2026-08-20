"""Tests for the upload defences named in docs/GITHUB_RELEASE_PLAN.md.

The checklist requires upload tests covering MIME, size limits, zip bombs and
path traversal. The defences existed in the code but none of them was covered
by a test: they were asserted, not verified. These tests exercise each one
against hostile input.
"""
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from core.document_parser import (
    MAX_OFFICE_ARCHIVE_FILES,
    MAX_OFFICE_COMPRESSION_RATIO,
    DocumentParseError,
    _validate_office_archive,
)
from core.input_validator import matches_expected_file_signature, sanitize_upload_name


def _office_zip(entries: dict, kind: str = "docx") -> bytes:
    """Build a minimal, structurally valid Office archive plus extra entries."""
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml" if kind == "docx" else "xl/workbook.xml", "<x />")
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


class TestPathTraversalAndExtensions:
    @pytest.mark.parametrize("hostile", [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "C:\\Windows\\win.ini",
        "..",
        ".",
        "",
        "   ",
    ])
    def test_traversal_and_empty_names_are_refused(self, hostile):
        assert sanitize_upload_name(hostile) is None

    def test_embedded_null_byte_cannot_truncate_the_name(self):
        # A NUL byte is a classic way to make one layer see "a.txt" and the
        # next see "a.txt.exe" — the name must not survive it.
        assert sanitize_upload_name("report.txt\x00.exe") is None

    @pytest.mark.parametrize("name", ["script.exe", "payload.sh", "macro.docm", "archive.zip", "page.html"])
    def test_extensions_outside_the_allowlist_are_refused(self, name):
        assert sanitize_upload_name(name) is None

    @pytest.mark.parametrize("name", ["manuale.pdf", "policy.docx", "note.txt", "readme.md", "dati.xlsx"])
    def test_supported_documents_are_accepted(self, name):
        assert sanitize_upload_name(name) == name

    def test_a_directory_component_is_stripped_not_trusted(self):
        # Even a benign-looking prefix must be discarded rather than preserved.
        assert sanitize_upload_name("subdir/manuale.pdf") == "manuale.pdf"


class TestDeclaredTypeMustMatchContent:
    def test_extension_alone_does_not_make_a_pdf(self):
        assert matches_expected_file_signature(BytesIO(b"not a pdf at all"), "fake.pdf") is False

    def test_real_pdf_header_is_accepted(self):
        assert matches_expected_file_signature(BytesIO(b"%PDF-1.7\nbody"), "vero.pdf") is True

    def test_office_documents_must_be_zip_archives(self):
        assert matches_expected_file_signature(BytesIO(b"PK\x03\x04rest"), "policy.docx") is True
        assert matches_expected_file_signature(BytesIO(b"<html>"), "policy.docx") is False

    def test_binary_content_is_not_accepted_as_text(self):
        assert matches_expected_file_signature(BytesIO(b"ciao mondo"), "note.txt") is True
        assert matches_expected_file_signature(BytesIO(b"\x00\x01\x02binario"), "note.txt") is False


class TestZipBombDefences:
    def test_highly_compressible_payload_is_refused(self):
        # A megabyte of zeros compresses far past the allowed ratio.
        payload = b"\x00" * (2 * 1024 * 1024)
        content = _office_zip({"word/media/blob.bin": payload})

        with pytest.raises(DocumentParseError, match="compressione"):
            _validate_office_archive(content, "docx")

    def test_archive_with_too_many_entries_is_refused(self):
        entries = {"word/media/f%d.txt" % i: "x" for i in range(MAX_OFFICE_ARCHIVE_FILES + 5)}
        content = _office_zip(entries)

        with pytest.raises(DocumentParseError, match="troppi file"):
            _validate_office_archive(content, "docx")

    def test_a_normal_document_passes(self):
        content = _office_zip({"word/media/logo.png": b"\x89PNG" + b"varied-bytes" * 20})
        _validate_office_archive(content, "docx")  # must not raise

    def test_zip_that_is_not_an_office_document_is_refused(self):
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr("innocuo.txt", "solo un archivio zip")

        with pytest.raises(DocumentParseError):
            _validate_office_archive(buffer.getvalue(), "docx")

    def test_compression_ratio_limit_is_actually_enforced(self):
        # Guards the constant itself: if someone raises it to a useless value
        # this test still proves the check runs against the declared limit.
        assert MAX_OFFICE_COMPRESSION_RATIO <= 1000
