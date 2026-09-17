"""OCR per pagine PDF senza livello testo (scansioni).

Fino al 18 settembre 2026 il parser tentava `pytesseract` sulle immagini
*incorporate* nella pagina (`page.images` di pypdf). Non funzionava mai in
pratica: la dipendenza non era in requirements.txt, il binario Tesseract non
era nel Dockerfile, e molti scanner producono PDF in cui la pagina e' un
unico oggetto immagine che pypdf non espone. Un documento scansionato
veniva indicizzato con zero passaggi, senza segnalazione.

Qui la pagina viene rasterizzata per intero (pypdfium2, senza dipendenze di
sistema) e passata a Tesseract. Se Tesseract non e' installato la funzione
lo dice — `available()` — e /health lo riporta come degrado: una pagina
scansionata senza OCR e' contenuto perso, non un dettaglio.
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

_logger = logging.getLogger("ermes.ocr")


def available() -> tuple[bool, str]:
    """(True, "") se l'OCR puo' girare; altrimenti (False, ragione leggibile)."""
    try:
        import pypdfium2  # noqa: F401
        import pytesseract
    except ImportError as error:
        return False, f"modulo Python mancante: {error.name}"
    binario = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
    if shutil.which(binario) is None:
        return False, f"binario Tesseract non trovato ({binario})"
    return True, ""


def render_pdf_page(content: bytes, page_index: int, dpi: int) -> Image:
    """Rasterizza una pagina (0-based) del PDF in un'immagine PIL."""
    import pypdfium2

    documento = pypdfium2.PdfDocument(content)
    try:
        pagina = documento[page_index]
        try:
            image: Image = pagina.render(scale=dpi / 72).to_pil()
            return image
        finally:
            pagina.close()
    finally:
        documento.close()


def ocr_image(image: Image, lang: str) -> str:
    """Testo riconosciuto in un'immagine. Vuoto se Tesseract non legge nulla."""
    import pytesseract

    text: str = pytesseract.image_to_string(image, lang=lang)
    return text.strip()


def ocr_pdf_page(content: bytes, page_index: int, *, lang: str, dpi: int) -> str:
    return ocr_image(render_pdf_page(content, page_index, dpi), lang)
