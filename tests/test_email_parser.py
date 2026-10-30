"""Email salvate (.eml) come documenti: core/document_parser.py, voce 1.4 del piano."""

from email.message import EmailMessage

from core.document_parser import extract_source_units
from core.input_validator import validate_and_scan_document


def _email(body: str = "Il pagamento e' a 90 giorni.", html: str | None = None) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Laura <laura@fornitore.example>"
    message["To"] = "amministrazione@azienda.example"
    message["Date"] = "Tue, 14 Apr 2026 10:12:00 +0200"
    message["Subject"] = "Condizioni di fornitura però confermate"
    message.set_content(body)
    if html is not None:
        message.add_alternative(html, subtype="html")
    return message


def test_the_citation_names_the_email_and_the_body_keeps_the_headers():
    units = extract_source_units("conferma.eml", bytes(_email()))

    assert units[0].locator == "Email: Condizioni di fornitura però confermate (Tue, 14 Apr 2026 10:12:00 +0200)"
    assert "Da: Laura <laura@fornitore.example>" in units[0].text
    assert "90 giorni" in units[0].text


def test_plain_text_is_preferred_and_html_only_mail_is_still_read():
    con_entrambi = extract_source_units("a.eml", bytes(_email("testo semplice", "<p>versione <b>html</b></p>")))
    solo_html = EmailMessage()
    solo_html["Subject"] = "Solo HTML"
    solo_html.set_content("<p>Consegna in <b>dieci</b> giorni</p>", subtype="html")

    assert "testo semplice" in con_entrambi[0].text and "html" not in con_entrambi[0].text
    testo = extract_source_units("b.eml", bytes(solo_html))[0].text
    assert "Consegna in" in testo and "<b>" not in testo


def test_supported_attachments_become_their_own_cited_units():
    message = _email()
    message.add_attachment(
        b"## Prezzi\n\nBarra da 40 mm: 1,08 euro/kg.\n", maintype="text", subtype="markdown", filename="listino.md"
    )
    message.add_attachment(b"MZ\x90\x00binario", maintype="application", subtype="octet-stream", filename="setup.exe")

    units = extract_source_units("conferma.eml", bytes(message))

    allegati = [u for u in units if "allegato" in u.locator]
    assert [u.locator.split(", allegato ")[1] for u in allegati] == ["listino.md — Sezione: Prezzi"]
    # Il testo dell'allegato da solo non dice a cosa si riferisce.
    assert allegati[0].text.startswith("Allegato listino.md all'email «Condizioni di fornitura però confermate»")
    assert "setup.exe" not in " ".join(u.locator for u in units)


def test_upload_validation_accepts_eml_and_rejects_binary_content():
    assert validate_and_scan_document("conferma.eml", bytes(_email())) == (True, "conferma.eml")
    ok, _ = validate_and_scan_document("finta.eml", b"From: x\x00\x00binario")
    assert ok is False
