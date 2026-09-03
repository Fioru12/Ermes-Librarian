"""
scripts/generate_pdf_tesina.py
Converte il file Markdown docs/TESINA_FINALE_ITS_ERMES.md in un file PDF elegante e professionale.
Genera la tesina in formato A4 con impaginazione accademica,
copertina, indice compatto su 1 pagina, numeri di pagina "Pagina X di Y",
box di approfondimento tecnico e formattazione rigorosa di ~15 pagine.
"""
import os
import re
from typing import Any
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, HRFlowable, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas two-pass per numerazione 'Pagina X di Y' e intestazioni istituzionali."""
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        page_num = getattr(self, '_pageNumber', 1)
        if page_num == 1:
            return  # La copertina non ha intestazione e piè di pagina

        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#0f172a"))

        # Intestazione superiore
        self.drawString(2 * cm, 28.2 * cm, "ISTITUTO TECNICO SUPERIORE (ITS)  |  PROGETTO ERMES KNOWLEDGE")
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawRightString(19 * cm, 28.2 * cm, "TESINA DI FINE PERCORSO")
        
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.75)
        self.line(2 * cm, 27.9 * cm, 19 * cm, 27.9 * cm)

        # Piè di pagina
        self.line(2 * cm, 1.6 * cm, 19 * cm, 1.6 * cm)
        self.drawString(2 * cm, 1.2 * cm, "Candidato: [Nome e Cognome] — Corso Sviluppo Software & AI")
        page_text = f"Pagina {page_num} di {page_count}"
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#0f172a"))
        self.drawRightString(19 * cm, 1.2 * cm, page_text)

        self.restoreState()


def sanitize_text(text: str) -> str:
    replacements = {
        "’": "'", "‘": "'",
        "“": '"', "”": '"',
        "—": " - ", "–": "-",
        "…": "...",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def build_pdf() -> None:
    md_path = "docs/TESINA_FINALE_ITS_ERMES.md"
    pdf_path = "docs/TESINA_FINALE_ITS_ERMES.pdf"

    if not os.path.exists(md_path):
        print(f"Errore: File {md_path} non trovato!")
        return

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=2.4 * cm,
        bottomMargin=2.2 * cm
    )

    styles = getSampleStyleSheet()

    color_primary = colors.HexColor("#0f172a")    # Dark Slate Navy
    color_accent = colors.HexColor("#0284c7")     # Sky / Blue Accent
    color_text = colors.HexColor("#1e293b")       # Dark Charcoal
    color_muted = colors.HexColor("#475569")      # Muted Text

    style_cover_inst = ParagraphStyle(
        'CoverInst',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=color_primary,
        alignment=1, # Center
        spaceAfter=6
    )

    style_cover_course = ParagraphStyle(
        'CoverCourse',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=color_accent,
        alignment=1,
        spaceAfter=25
    )

    style_cover_type = ParagraphStyle(
        'CoverType',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#dc2626"), # Crimson red badge
        alignment=1,
        spaceAfter=15
    )

    style_cover_title = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=26,
        textColor=color_primary,
        alignment=1,
        spaceAfter=35
    )

    style_cover_meta_label = ParagraphStyle(
        'CoverMetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=15,
        textColor=color_accent
    )

    style_cover_meta_val = ParagraphStyle(
        'CoverMetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=15,
        textColor=color_primary
    )

    style_h1 = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14.5,
        leading=19,
        textColor=color_primary,
        spaceBefore=16,
        spaceAfter=9,
        keepWithNext=True
    )

    style_h2 = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=color_accent,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    style_body = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.2,
        leading=15.2,
        textColor=color_text,
        spaceAfter=8,
        alignment=4 # Justified
    )

    style_toc_num = ParagraphStyle(
        'TOCNum',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=color_accent
    )

    style_toc_text = ParagraphStyle(
        'TOCText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=color_primary
    )

    style_toc_sub = ParagraphStyle(
        'TOCSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=color_muted
    )

    story: list[Any] = []
    lines = md_text.split('\n')
    
    state = "COVER" # COVER -> TOC -> BODY
    cover_meta_rows = []

    for line in lines:
        stripped = sanitize_text(line.strip())

        if stripped == r"\newpage":
            if state == "COVER":
                # Finalizza Copertina
                state = "TOC"
                story.append(PageBreak())
                continue
            elif state == "TOC":
                state = "BODY"
                story.append(PageBreak())
                continue
            else:
                story.append(PageBreak())
                continue

        if stripped.startswith("---"):
            if state == "COVER":
                story.append(Spacer(1, 0.4 * cm))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=5, spaceAfter=15))
            continue

        if not stripped:
            continue

        if state == "COVER":
            if stripped.startswith("# "):
                story.append(Spacer(1, 1.5 * cm))
                story.append(Paragraph(stripped[2:].strip(), style_cover_inst))
            elif stripped.startswith("## "):
                story.append(Paragraph(stripped[3:].strip(), style_cover_course))
            elif stripped.startswith("### "):
                story.append(Paragraph(stripped[4:].strip(), style_cover_type))
            elif "Titolo dell'Elaborato:" in stripped:
                continue
            elif stripped.startswith("*Progettazione"):
                title_clean = stripped.replace("*", "").strip()
                story.append(Paragraph(title_clean, style_cover_title))
            elif ":" in stripped and ("Candidato" in stripped or "Corso" in stripped or "Azienda" in stripped or "Tutor" in stripped or "Anno" in stripped):
                clean_line = stripped.replace("**", "").replace("*", "").strip()
                parts = clean_line.split(":", 1)
                lbl = parts[0].strip() + ":"
                val = parts[1].strip() if len(parts) > 1 else ""
                cover_meta_rows.append([Paragraph(lbl, style_cover_meta_label), Paragraph(val, style_cover_meta_val)])
                if len(cover_meta_rows) == 5:
                    story.append(Spacer(1, 1.0 * cm))
                    t_meta = Table(cover_meta_rows, colWidths=[5.5 * cm, 11.5 * cm])
                    t_meta.setStyle(TableStyle([
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                        ('TOPPADDING', (0,0), (-1,-1), 5),
                        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#f1f5f9")),
                    ]))
                    story.append(t_meta)

        elif state == "TOC":
            if stripped.startswith("## "):
                story.append(Paragraph(stripped[3:].strip(), style_h1))
                story.append(Spacer(1, 0.2 * cm))
            elif re.match(r'^\d+\.\s', stripped):
                # Capitolo principale
                clean = re.sub(r'^\d+\.\s', '', stripped).replace('**', '').strip()
                match = re.match(r'^(\d+)\.\s', stripped)
                num = match.group(1) if match else ""
                story.append(Spacer(1, 0.15 * cm))
                t_row = Table([[Paragraph(f"<b>Capitolo {num}</b>", style_toc_num), Paragraph(f"<b>{clean}</b>", style_toc_text)]], colWidths=[2.6 * cm, 14.4 * cm])
                t_row.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('PADDING', (0,0), (-1,-1), 2),
                ]))
                story.append(t_row)
            elif stripped.startswith("- "):
                sub_clean = stripped[2:].replace('**', '').strip()
                t_sub = Table([[Paragraph("", style_toc_sub), Paragraph(sub_clean, style_toc_sub)]], colWidths=[2.6 * cm, 14.4 * cm])
                t_sub.setStyle(TableStyle([
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('PADDING', (0,0), (-1,-1), 1),
                ]))
                story.append(t_sub)

        else: # BODY
            if stripped.startswith("# "):
                story.append(Spacer(1, 0.4 * cm))
                story.append(Paragraph(stripped[2:].strip(), style_h1))
            elif stripped.startswith("## "):
                story.append(Paragraph(stripped[3:].strip(), style_h2))
            elif stripped.startswith("### "):
                story.append(Paragraph(stripped[4:].strip(), style_h2))
            elif stripped.startswith("- ") or stripped.startswith("* "):
                text = stripped[2:].strip()
                text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
                text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
                story.append(Paragraph(f"• {text}", style_body))
            elif re.match(r'^\d+\.\s', stripped):
                text = re.sub(r'^\d+\.\s', '', stripped)
                text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
                text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
                story.append(Paragraph(f"• {text}", style_body))
            else:
                text = stripped
                text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
                text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
                text = re.sub(r'`(.*?)`', r'<font face="Courier" color="#0284c7">\1</font>', text)
                story.append(Paragraph(text, style_body))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"File PDF Tesina aggiornato con successo in: {pdf_path}")


if __name__ == "__main__":
    build_pdf()
