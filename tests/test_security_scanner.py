"""tests/test_security_scanner.py
Unit and integration tests for document malware and exploit scanning
(core/security_scanner.py and core/input_validator.py).
"""

import io
import zipfile

from core.input_validator import validate_and_scan_document
from core.security_scanner import (
    scan_csv,
    scan_office,
    scan_pdf,
    scan_zip_archive,
)


# ==========================================
# 1. PDF Security Scanning
# ==========================================

def test_pdf_with_javascript_rejected():
    malicious_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R /OpenAction 3 0 R >>\n"
        b"endobj\n"
        b"3 0 obj\n"
        b"<< /Type /Action /S /JavaScript /JS (app.alert('Malware');) >>\n"
        b"endobj\n"
        b"%%EOF\n"
    )
    result = scan_pdf(malicious_pdf)
    assert not result.is_safe
    assert "pdf_javascript" in result.threat_name
    assert "JavaScript" in result.details


def test_pdf_with_launch_action_rejected():
    malicious_pdf = (
        b"%PDF-1.5\n"
        b"1 0 obj\n"
        b"<< /Type /Action /S /Launch /F (calc.exe) >>\n"
        b"endobj\n"
        b"%%EOF\n"
    )
    result = scan_pdf(malicious_pdf)
    assert not result.is_safe
    assert "pdf_launch_action" in result.threat_name


def test_clean_pdf_accepted():
    clean_pdf = (
        b"%PDF-1.7\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R >>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"
        b"endobj\n"
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R >>\n"
        b"endobj\n"
        b"%%EOF\n"
    )
    result = scan_pdf(clean_pdf)
    assert result.is_safe
    assert result.threat_name is None


# ==========================================
# 2. Office Document & VBA Macro Scanning
# ==========================================

def test_docx_with_vba_macro_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", "<w:document></w:document>")
        zf.writestr("word/vbaProject.bin", b"VBA MACRO BINARY PAYLOAD")
    docx_bytes = buf.getvalue()

    result = scan_office("report.docx", docx_bytes)
    assert not result.is_safe
    assert "office_vba_macro" in result.threat_name


def test_clean_docx_accepted():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Hello Ermes</w:t></w:r></w:p></w:body></w:document>")
    clean_bytes = buf.getvalue()

    result = scan_office("document.docx", clean_bytes)
    assert result.is_safe
    assert result.threat_name is None


# ==========================================
# 3. Zip Bomb & Archive Attack Scanning
# ==========================================

def test_zip_bomb_compression_ratio_rejected():
    # In-memory repetitive data that compresses to a huge ratio (> 100:1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("large_repeated.txt", b"A" * (2 * 1024 * 1024))  # 2MB compresses to ~2KB (ratio ~1000)
    zip_bytes = buf.getvalue()

    result = scan_zip_archive(zip_bytes, max_ratio=50.0)
    assert not result.is_safe
    assert "zip_bomb_ratio_exceeded" in result.threat_name


def test_zip_with_directory_traversal_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../../etc/passwd", b"root:x:0:0:root")
    zip_bytes = buf.getvalue()

    result = scan_zip_archive(zip_bytes)
    assert not result.is_safe
    assert "archive_path_traversal" in result.threat_name


# ==========================================
# 4. CSV Formula Injection Scanning
# ==========================================

def test_csv_formula_injection_equals_rejected():
    malicious_csv = b"id,name,cmd\n1,Alice,=cmd|'/c calc'!A0\n2,Bob,safe\n"
    result = scan_csv(malicious_csv)
    assert not result.is_safe
    assert "csv_formula_injection" in result.threat_name


def test_csv_formula_injection_at_symbol_rejected():
    malicious_csv = b"col1,col2\n@SUM(1+1)*cmd|' /C calc'!A0,test\n"
    result = scan_csv(malicious_csv)
    assert not result.is_safe
    assert "csv_formula_injection" in result.threat_name


def test_clean_csv_accepted():
    clean_csv = b"id,title,count\n1,Document A,42\n2,Document B,100\n"
    result = scan_csv(clean_csv)
    assert result.is_safe


# ==========================================
# 5. Integrated validate_and_scan_document
# ==========================================

def test_validate_and_scan_safe_text():
    content = b"# Document Title\n\nThis is safe markdown documentation."
    is_safe, name = validate_and_scan_document("guide.md", content)
    assert is_safe
    assert name == "guide.md"


def test_validate_and_scan_malicious_pdf_rejected():
    malicious_pdf = (
        b"%PDF-1.4\n"
        b"<< /Type /Action /S /JavaScript /JS (app.alert(1);) >>\n"
        b"%%EOF\n"
    )
    is_safe, reason = validate_and_scan_document("report.pdf", malicious_pdf)
    assert not is_safe
    assert "pdf_javascript" in reason


def test_validate_and_scan_invalid_magic_bytes_rejected():
    # PDF extension but not %PDF-
    fake_pdf = b"NOT A PDF FILE AT ALL"
    is_safe, reason = validate_and_scan_document("fake.pdf", fake_pdf)
    assert not is_safe
    assert "firma" in reason.lower() or "valido" in reason.lower()


def test_validate_and_scan_empty_rejected():
    is_safe, reason = validate_and_scan_document("empty.txt", b"")
    assert not is_safe
    assert "vuoto" in reason.lower()
