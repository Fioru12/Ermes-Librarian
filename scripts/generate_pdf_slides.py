"""
scripts/generate_pdf_slides.py
Genera il file PDF Widescreen 16:9 della presentazione (docs/PRESENTAZIONE_ITS_ERMES.pdf)
con layout modern enterprise a card, metriche evidenziate e screenshot applicativi.
"""
import os
from typing import Any

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SLIDE_WIDTH = 13.333 * inch
SLIDE_HEIGHT = 7.5 * inch

def build_slides_pdf() -> None:
    pdf_path = "docs/PRESENTAZIONE_ITS_ERMES.pdf"

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=(SLIDE_WIDTH, SLIDE_HEIGHT),
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch
    )

    _styles = getSampleStyleSheet()

    # Colori
    NAVY = colors.HexColor("#0f172a")
    CYAN = colors.HexColor("#0284c7")
    INDIGO = colors.HexColor("#4f46e5")
    EMERALD = colors.HexColor("#059669")
    ROSE = colors.HexColor("#e11d48")
    DARK_TEXT = colors.HexColor("#1e293b")
    MUTED_TEXT = colors.HexColor("#475569")
    BG_LIGHT_CARD = colors.HexColor("#f8fafc")
    BORDER_CARD = colors.HexColor("#cbd5e1")
    _WHITE = colors.HexColor("#ffffff")

    style_cover_title = ParagraphStyle(
        'CoverTitle',
        fontName='Helvetica-Bold',
        fontSize=38,
        leading=44,
        textColor=NAVY,
        spaceAfter=10
    )

    style_cover_sub = ParagraphStyle(
        'CoverSub',
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=24,
        textColor=CYAN,
        spaceAfter=25
    )

    style_cover_meta = ParagraphStyle(
        'CoverMeta',
        fontName='Helvetica',
        fontSize=12,
        leading=18,
        textColor=DARK_TEXT
    )

    style_header_title = ParagraphStyle(
        'HeaderTitle',
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=28,
        textColor=NAVY,
        spaceAfter=15
    )

    style_card_title = ParagraphStyle(
        'CardTitle',
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=20,
        textColor=NAVY,
        spaceAfter=6
    )

    style_card_body = ParagraphStyle(
        'CardBody',
        fontName='Helvetica',
        fontSize=12,
        leading=17,
        textColor=MUTED_TEXT
    )

    style_metric_big = ParagraphStyle(
        'MetricBig',
        fontName='Helvetica-Bold',
        fontSize=36,
        leading=42,
        textColor=EMERALD,
        spaceAfter=4
    )

    icon_path = "assets/ermes-knowledge-icon.png"
    if not os.path.exists(icon_path):
        icon_path = "Ermes.png"

    screenshot_chat = "docs/screenshots/assistant-with-citations.png"
    _screenshot_docs = "docs/screenshots/libraries-and-documents.png"
    screenshot_audit = "docs/screenshots/audit-log-integrity.png"

    story: list[Any] = []

    def make_card(title: str, text: str, title_color: Any = NAVY) -> list[Any]:
        t_style = ParagraphStyle('CT', parent=style_card_title, textColor=title_color)
        return [Paragraph(title, t_style), Spacer(1, 0.05 * inch), Paragraph(text, style_card_body)]

    # 1. COVER
    cover_left: list[Any] = []
    if os.path.exists(icon_path):
        try:
            cover_left.append(Image(icon_path, width=1.6 * inch, height=1.6 * inch))
            cover_left.append(Spacer(1, 0.2 * inch))
        except Exception:
            pass
    cover_left.append(Paragraph("★ PROVA FINALE DI ALTA FORMAZIONE ITS", ParagraphStyle('B', fontName='Helvetica-Bold', fontSize=12, textColor=CYAN)))
    cover_left.append(Paragraph("ERMES KNOWLEDGE", style_cover_title))
    cover_left.append(Paragraph("Sistema RAG Enterprise Local-First con Garanzie di Sicurezza, DLP e Isolamento", style_cover_sub))

    meta_p = [
        Paragraph("<b>Candidato:</b> [Nome e Cognome]", style_cover_meta),
        Paragraph("<b>Corso:</b> Tecnico Superiore Sviluppo Software e AI", style_cover_meta),
        Paragraph("<b>Azienda Partner:</b> [Nome Azienda / Stage]", style_cover_meta),
        Paragraph("<b>Tutor Aziendale / ITS:</b> [Nome Tutor] / [Nome Tutor]", style_cover_meta),
        Paragraph("<b>Anno Formativo:</b> 2025 / 2026", style_cover_meta)
    ]
    t_cov = Table([[cover_left, meta_p]], colWidths=[7.5 * inch, 4.3 * inch])
    t_cov.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (1,0), (1,0), BG_LIGHT_CARD),
        ('BOX', (1,0), (1,0), 1, BORDER_CARD),
        ('PADDING', (1,0), (1,0), 16),
    ]))
    story.append(t_cov)
    story.append(PageBreak())

    # 2. IL PROBLEMA
    story.append(Paragraph("1. Il Problema Aziendale: Frammentazione e Rischi dei LLM Generici", style_header_title))
    c2_l = make_card("📂 La Conoscenza Frammentata nei Silos", "• <b>Silos Informativi:</b> Dati dispersi tra cartelle condivise, PDF non indicizzati e chat.<br/>• <b>Tempo Perso:</b> Ore spese dai dipendenti per rintracciare regolamenti aggiornati.<br/>• <b>Ricerca Tradizionale Cieca:</b> Il keyword-matching classico ignora sinonimi e parafrasi.", NAVY)
    c2_r = make_card("⚠️ I Pericoli dei Chatbot Commerciali (Cloud)", "• <b>Allucinazioni Gravi:</b> Modelli che inventano risposte plausibili ma prive di riscontro.<br/>• <b>Violazioni Privacy (GDPR):</b> Dati aziendali inviati all'esterno su server cloud terzi.<br/>• <b>Zero Tracciabilità:</b> Nessuna prova verificabile su chi ha consultato cosa.", ROSE)
    t2 = Table([[c2_l, c2_r]], colWidths=[5.8 * inch, 5.8 * inch])
    t2.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(t2)
    story.append(PageBreak())

    # 3. LA SOLUZIONE
    story.append(Paragraph("2. La Soluzione: Ermes Knowledge (Evidenza Prima)", style_header_title))
    c3_text = [
        Paragraph("🛡️ <b>Local-First:</b> Nessun dato riservato lascia il perimetro aziendale. Embedding on-device.", style_card_body),
        Spacer(1, 0.15 * inch),
        Paragraph("📑 <b>Evidenza Reale:</b> Ogni affermazione cita il documento originale scaricabile in 1 click.", style_card_body),
        Spacer(1, 0.15 * inch),
        Paragraph("🚫 <b>Zero Allucinazioni:</b> Se il documento manca, l'assistente dichiara l'assenza di evidenza.", style_card_body)
    ]
    img3 = []
    if os.path.exists(screenshot_chat):
        img3.append(Image(screenshot_chat, width=5.6 * inch, height=4.3 * inch))
    t3 = Table([[c3_text, img3]], colWidths=[5.8 * inch, 5.8 * inch])
    t3.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (0,0), BG_LIGHT_CARD),
        ('BOX', (0,0), (0,0), 1, BORDER_CARD),
        ('PADDING', (0,0), (0,0), 14),
    ]))
    story.append(t3)
    story.append(PageBreak())

    # 4. LE 5 REGOLE
    story.append(Paragraph("3. Le 5 Regole Fondamentali, Applicate nel Codice", style_header_title))
    rules_table_data = [
        [Paragraph("<b>1. Local-First</b>", style_card_title), Paragraph("Una chiave API cloud da sola non attiva mai l'elaborazione cloud esterna.", style_card_body)],
        [Paragraph("<b>2. Evidenza Prima</b>", style_card_title), Paragraph("Ogni risposta cita un documento accessibile, oppure l'assistente si astiene.", style_card_body)],
        [Paragraph("<b>3. Isolamento Rigido</b>", style_card_title), Paragraph("La ricerca è vincolata alla biblioteca prima che il testo arrivi all'assistente.", style_card_body)],
        [Paragraph("<b>4. Input Non Fidato</b>", style_card_title), Paragraph("Il testo estratto dai documenti non può mai eseguire codice o autorizzare azioni.", style_card_body)],
        [Paragraph("<b>5. Originali Accessibili</b>", style_card_title), Paragraph("Ogni citazione rimanda alla versione esatta del file scaricabile con 1 click.", style_card_body)]
    ]
    t4 = Table(rules_table_data, colWidths=[3.2 * inch, 8.4 * inch])
    t4.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('GRID', (0,0), (-1,-1), 0.5, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t4)
    story.append(PageBreak())

    # 5. ARCHITETTURA & TECH STACK
    story.append(Paragraph("4. Architettura del Sistema & Tech Stack Enterprise", style_header_title))
    c5_1 = make_card("🌐 Frontend UI/UX", "React 18 · TypeScript · Vite · Tailwind CSS<br/>Design System moderno e gestione responsive dello stato.", CYAN)
    c5_2 = make_card("⚡ Backend API Services", "Python 3.11 · FastAPI (ASGI Asincrono)<br/>Validazione automatica Pydantic e Swagger nativo.", INDIGO)
    c5_3 = make_card("🧠 AI & Vector Engine", "Ollama Embeddings · SQLite / JSON Store<br/>Embedding on-device e storage documentale isolato.", EMERALD)
    c5_4 = make_card("🐳 DevOps & Testing", "Docker · Docker Compose · Pytest (241 Test)<br/>Orchestrazione scalabile e CI su GitHub Actions.", ROSE)
    t5 = Table([[c5_1, c5_2], [c5_3, c5_4]], colWidths=[5.8 * inch, 5.8 * inch])
    t5.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t5)
    story.append(PageBreak())

    # 6. PIPELINE RAG
    story.append(Paragraph("5. Il Motore di Retrieval: Chunking e Ricerca Ibrida", style_header_title))
    c6_1 = make_card("1. Ingestion", "Parsing PDF, Word, Markdown, TXT e Web scraper.", CYAN)
    c6_2 = make_card("2. Chunking", "Segmentazione semantica con overlap contestuale.", INDIGO)
    c6_3 = make_card("3. Hybrid Search", "Vettoriale (Sinonimi) + BM25 (Codici esatti).", EMERALD)
    c6_4 = make_card("4. RRF Fusion", "Fusione con Reciprocal Rank Fusion.", ROSE)
    t6_steps = Table([[c6_1, c6_2, c6_3, c6_4]], colWidths=[2.85 * inch, 2.85 * inch, 2.85 * inch, 2.85 * inch])
    t6_steps.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t6_steps)
    story.append(Spacer(1, 0.2 * inch))
    c6_banner = [Paragraph("<b>💡 Perché la Ricerca Ibrida vince nei contesti aziendali:</b>", style_card_title),
                 Paragraph("La ricerca vettoriale capisce i concetti e le parafrasi ma rischia di fallire su codici articolo specifici. Il BM25 cattura esattamente le sigle tecniche ma ignora i sinonimi. La loro combinazione raggiunge il massimo della precisione.", style_card_body)]
    t6_b = Table([[c6_banner]], colWidths=[11.7 * inch])
    t6_b.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t6_b)
    story.append(PageBreak())

    # 7. RE-RANKER & DEDUPLICA
    story.append(Paragraph("6. Advanced Retrieval: Re-ranker Posizionale e Deduplicazione", style_header_title))
    c7_l = make_card("🎯 Re-ranker Posizionale Avanzato", "• <b>Vicinanza Posizionale:</b> Premia i documenti in cui le parole chiave compaiono vicine nella stessa frase.<br/>• <b>Bi-grammi Consecutivi:</b> Riconosce sequenze di vocaboli ad alta pertinenza.<br/>• <b>Title Matching:</b> Assegna un peso superiore alle intestazioni di sezione.", INDIGO)
    c7_r = make_card("🧩 Deduplicazione Jaccard", "• <b>Indice di Jaccard su Shingle:</b> Analizza la somiglianza tra versioni simili dello stesso documento.<br/>• <b>Raggruppamento Duplicati:</b> Identifica revisioni duplicate nella stessa biblioteca.<br/>• <b>Efficienza:</b> Invia all'LLM solo il frammento migliore, azzerando le ridondanze.", CYAN)
    t7 = Table([[c7_l, c7_r]], colWidths=[5.8 * inch, 5.8 * inch])
    t7.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(t7)
    story.append(PageBreak())

    # 8. DLP & PII GUARD
    story.append(Paragraph("7. Data Loss Prevention: Il Filtro PII Guard Algoritmico", style_header_title))
    c8_1 = make_card("💳 Carte di Credito (Luhn Checksum)", "Verifica matematica di Luhn (mod 10). Maschera le carte reali come [CARTA_CREDITO], ignorando numeri casuali.", ROSE)
    c8_2 = make_card("🏦 Coordinate Bancarie IBAN", "Validazione algebrica Modulo 97 (ISO 13616). Maschera solo IBAN validi come [IBAN].", EMERALD)
    c8_3 = make_card("🪪 Codici Fiscali Italiani", "Pattern alfanumerico a 16 caratteri con verifica algoritmica del carattere di controllo (CIN).", CYAN)
    c8_4 = make_card("🔑 Token JWT & API Keys", "Riconoscimento pattern di token crittografici e chiavi API (sk-live, Bearer), oscurati preventivamente.", INDIGO)
    t8 = Table([[c8_1, c8_2], [c8_3, c8_4]], colWidths=[5.8 * inch, 5.8 * inch])
    t8.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t8)
    story.append(PageBreak())

    # 9. GOVERNANCE & RBAC
    story.append(Paragraph("8. Governance, RBAC e Audit Log Immutabile", style_header_title))
    c9_text = [
        Paragraph("<b>Ruoli di Accesso (RBAC):</b>", style_card_title),
        Paragraph("• <b>Admin:</b> Gestione globale di utenti, biblioteche e registri di audit.<br/>• <b>Editor:</b> Upload e gestione documenti nelle biblioteche abilitate.<br/>• <b>Viewer:</b> Consultazione e ricerca in sola lettura.<br/>• <b>Security 404:</b> Le biblioteche non autorizzate restituiscono 404 per non rivelarne l'esistenza.", style_card_body)
    ]
    img9 = []
    if os.path.exists(screenshot_audit):
        img9.append(Image(screenshot_audit, width=5.6 * inch, height=4.3 * inch))
    t9 = Table([[c9_text, img9]], colWidths=[5.8 * inch, 5.8 * inch])
    t9.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (0,0), BG_LIGHT_CARD),
        ('BOX', (0,0), (0,0), 1, BORDER_CARD),
        ('PADDING', (0,0), (0,0), 14),
    ]))
    story.append(t9)
    story.append(PageBreak())

    # 10. GOLDEN SET EVALUATION
    story.append(Paragraph("9. Valutazione Quantitativa della Qualità: Golden Set", style_header_title))
    c10_1 = [Paragraph("100%", style_metric_big), Paragraph("<b>Query Dirette (16)</b>", style_card_title), Paragraph("Parole della domanda vicine al testo: recupero perfetto.", style_card_body)]
    c10_2 = [Paragraph("50% → 90%+", ParagraphStyle('M2', parent=style_metric_big, textColor=INDIGO)), Paragraph("<b>Query Parafrasate (8)</b>", style_card_title), Paragraph("Concetto condiviso, zero parole in comune: la ricerca semantica locale colma il divario.", style_card_body)]
    c10_3 = [Paragraph("67% → 100%", ParagraphStyle('M3', parent=style_metric_big, textColor=CYAN)), Paragraph("<b>Astensione (3)</b>", style_card_title), Paragraph("Domande su argomenti assenti: il sistema dichiara l'assenza senza allucinare.", style_card_body)]
    t10 = Table([[c10_1, c10_2, c10_3]], colWidths=[3.85 * inch, 3.85 * inch, 3.85 * inch])
    t10.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t10)
    story.append(PageBreak())

    # 11. TESTING & DEVOPS
    story.append(Paragraph("10. Qualità del Codice e Testing Automatizzato", style_header_title))
    c11_l = [
        Paragraph("241", style_metric_big),
        Paragraph("<b>TEST AUTOMATIZZATI (PYTEST)</b>", style_card_title),
        Paragraph("100% Passed. Copertura completa di API, algoritmi DLP (Luhn/IBAN), Re-ranker e sincronizzazione.", style_card_body)
    ]
    c11_r = [
        Paragraph("<b>Garanzie di Qualità & Continuous Integration:</b>", style_card_title),
        Paragraph("• <b>GitHub Actions CI:</b> Pipeline automatizzata che blocca le regressioni a ogni commit.<br/>• <b>Guardie di Sicurezza:</b> Nessun endpoint futuro può essere rilasciato senza autenticazione.<br/>• <b>OpenAPI / Swagger:</b> Documentazione API RESTful interattiva ed auto-generata.", style_card_body)
    ]
    t11 = Table([[c11_l, c11_r]], colWidths=[4.5 * inch, 7.1 * inch])
    t11.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(t11)
    story.append(PageBreak())

    # 12. ANALYTICS & KNOWLEDGE GAPS
    story.append(Paragraph("11. Governance: Analytics e Rilevamento dei Knowledge Gaps", style_header_title))
    c12_1 = make_card("📊 Monitoraggio Query & Latenze", "Tracciamento in tempo reale del volume di ricerche, tempo di risposta e gradimento delle risposte.", CYAN)
    c12_2 = make_card("❓ Rilevamento Knowledge Gaps", "Identificazione automatica delle domande a cui il sistema non trova risposte nella documentazione aziendale.", INDIGO)
    c12_3 = make_card("📈 Valore per il Management", "Fornisce alla direzione una guida chiara su quali regolamenti o schede tecniche mancano e devono essere redatte.", EMERALD)
    t12 = Table([[c12_1, c12_2, c12_3]], colWidths=[3.85 * inch, 3.85 * inch, 3.85 * inch])
    t12.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t12)
    story.append(PageBreak())

    # 13. STAGE ATTIVITÀ
    story.append(Paragraph("12. Esperienza di Tirocinio Aziendale / Stage: Attività e Metodologia", style_header_title))
    c13_1 = make_card("🏢 Contesto Operativo", "Inserimento nel team di sviluppo software dell'azienda partner [Nome Azienda]. Comprensione delle esigenze reali di gestione documentale.", CYAN)
    c13_2 = make_card("🚀 Attività Svolte", "• Progettazione architettura RAG modulare.<br/>• Sviluppo endpoint FastAPI e interfacce React.<br/>• Implementazione algoritmi DLP e re-ranking.", INDIGO)
    c13_3 = make_card("🔄 Metodologia Agile", "Adozione di pratiche Scrum/Kanban, stand-up giornalieri, code review e versionamento git organizzato.", EMERALD)
    t13 = Table([[c13_1, c13_2, c13_3]], colWidths=[3.85 * inch, 3.85 * inch, 3.85 * inch])
    t13.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t13)
    story.append(PageBreak())

    # 14. STAGE IMPATTO
    story.append(Paragraph("13. Esperienza di Tirocinio Aziendale: Impatto e Risultati", style_header_title))
    c14_1 = make_card("⚡ -70% Tempo di Ricerca", "I dipendenti rintracciano procedure e schede tecniche in secondi anziché navigare cartelle complesse.", EMERALD)
    c14_2 = make_card("🔒 100% Dati al Sicuro", "Adozione dell'AI senza rischi di fughe di dati o non conformità GDPR grazie all'approccio Local-First e al DLP.", CYAN)
    c14_3 = make_card("🎓 Crescita Professionale", "Consolidamento di competenze di livello enterprise in Software Architecture, AI Engineering e DevOps.", INDIGO)
    t14 = Table([[c14_1, c14_2, c14_3]], colWidths=[3.85 * inch, 3.85 * inch, 3.85 * inch])
    t14.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t14)
    story.append(PageBreak())

    # 15. CONCLUSIONI
    story.append(Paragraph("14. Conclusioni e Roadmap Evolutiva Enterprise", style_header_title))
    c15_1 = make_card("FASE 1: ENTERPRISE IAM", "Integrazione Single Sign-On (SSO) con Microsoft Entra ID / Keycloak e SCIM.", CYAN)
    c15_2 = make_card("FASE 2: SCALABILITÀ CLOUD", "Migrazione a Vector DB distribuiti (Qdrant cluster) e code asincrone Redis.", INDIGO)
    c15_3 = make_card("FASE 3: OSSERVABILITÀ", "Tracciamento distribuito con OpenTelemetry, metriche Prometheus e Grafana.", EMERALD)
    t15 = Table([[c15_1, c15_2, c15_3]], colWidths=[3.85 * inch, 3.85 * inch, 3.85 * inch])
    t15.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(t15)
    story.append(Spacer(1, 0.4 * inch))
    thanks_box = [Paragraph("<b>Grazie per l'attenzione!  —  Spazio per Domande e Risposte (Q&A)</b>", ParagraphStyle('Th', fontName='Helvetica-Bold', fontSize=16, textColor=CYAN, alignment=1))]
    t15_th = Table([[thanks_box]], colWidths=[11.7 * inch])
    t15_th.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_LIGHT_CARD),
        ('BOX', (0,0), (-1,-1), 1, BORDER_CARD),
        ('PADDING', (0,0), (-1,-1), 14),
    ]))
    story.append(t15_th)

    doc.build(story)
    print(f"File PDF Presentazione Widescreen creato con successo in: {pdf_path}")

if __name__ == "__main__":
    build_slides_pdf()
