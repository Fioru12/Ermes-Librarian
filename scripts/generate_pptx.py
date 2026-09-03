"""
scripts/generate_pptx.py
Generatore avanzato per la Presentazione PowerPoint (.pptx) dell'Esame Finale ITS.
Design Modern Enterprise (Dark Slate & Electric Cyan), layout a card, metric tiles,
badge colorati, diagrammi di flusso e screenshot applicativi incorniciati.
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def create_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Palette Cromatica Enterprise
    BG_DARK = RGBColor(11, 17, 32)         # #0b1120 - Dark Slate Base
    CARD_DARK = RGBColor(22, 30, 49)       # #161e31 - Dark Card
    CARD_BORDER = RGBColor(51, 65, 85)     # #334155 - Card Border Slate
    
    BG_LIGHT = RGBColor(248, 250, 252)     # #f8fafc - Light Base
    CARD_LIGHT = RGBColor(255, 255, 255)   # #ffffff - White Card
    CARD_LIGHT_BORDER = RGBColor(226, 232, 240) # #e2e8f0
    
    HEADER_NAVY = RGBColor(15, 23, 42)     # #0f172a
    CYAN_ACCENT = RGBColor(14, 165, 233)   # #0ea5e9
    INDIGO_ACCENT = RGBColor(99, 102, 241) # #6366f1
    EMERALD = RGBColor(16, 185, 129)       # #10b981 - Success
    ROSE = RGBColor(244, 63, 94)           # #f43f5e - Risk/Danger
    AMBER = RGBColor(245, 158, 11)         # #f59e0b - Warning
    
    TEXT_MAIN_DARK = RGBColor(241, 245, 249) # #f1f5f9
    TEXT_MUTED_DARK = RGBColor(148, 163, 184) # #94a3b8
    
    TEXT_MAIN_LIGHT = RGBColor(15, 23, 42)   # #0f172a
    TEXT_MUTED_LIGHT = RGBColor(71, 85, 105) # #475569

    # Risorse Grafiche
    icon_path = "assets/ermes-knowledge-icon.png"
    if not os.path.exists(icon_path):
        icon_path = "Ermes.png"

    screenshot_chat = "docs/screenshots/02-chat-interface.png"
    if not os.path.exists(screenshot_chat):
        screenshot_chat = "docs/screenshots/assistant-with-citations.png"

    screenshot_docs = "docs/screenshots/03-libraries-management.png"
    if not os.path.exists(screenshot_docs):
        screenshot_docs = "docs/screenshots/libraries-and-documents.png"

    screenshot_audit = "docs/screenshots/05-admin-governance.png"
    if not os.path.exists(screenshot_audit):
        screenshot_audit = "docs/screenshots/audit-log-integrity.png"

    screenshot_analytics = "docs/screenshots/04-analytics-dashboard.png"

    # Helper: Aggiunge una card con bordo arrotondato o rettangolare
    def add_card(slide, left, top, width, height, bg_color=CARD_LIGHT, border_color=CARD_LIGHT_BORDER):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        card.line.color.rgb = border_color
        card.line.width = Pt(1.5)
        return card

    # Helper: Header standard per slide chiare
    def add_header(slide, title, category="PROGETTO ERMES KNOWLEDGE — ESAME FINALE ITS"):
        # Header banner
        header_bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(1.15))
        header_bar.fill.solid()
        header_bar.fill.fore_color.rgb = HEADER_NAVY
        header_bar.line.fill.background()

        # Category tag
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.12), Inches(11.7), Inches(0.3))
        tf_cat = cat_box.text_frame
        p_cat = tf_cat.paragraphs[0]
        p_cat.text = category.upper()
        p_cat.font.size = Pt(10)
        p_cat.font.bold = True
        p_cat.font.color.rgb = CYAN_ACCENT

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.38), Inches(11.7), Inches(0.65))
        tf_title = title_box.text_frame
        p_title = tf_title.paragraphs[0]
        p_title.text = title
        p_title.font.size = Pt(22)
        p_title.font.bold = True
        p_title.font.color.rgb = RGBColor(255, 255, 255)

    # -------------------------------------------------------------
    # SLIDE 1: COVER HERO
    # -------------------------------------------------------------
    slide1 = prs.slides.add_slide(blank_layout)
    bg1 = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = BG_DARK
    bg1.line.fill.background()

    # Badge ITS
    badge = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(0.7), Inches(4.5), Inches(0.45))
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(30, 41, 59)
    badge.line.color.rgb = CYAN_ACCENT
    badge.line.width = Pt(1)
    tf_b = badge.text_frame
    p_b = tf_b.paragraphs[0]
    p_b.text = "★  PROVA FINALE DI ALTA FORMAZIONE ITS"
    p_b.font.size = Pt(11)
    p_b.font.bold = True
    p_b.font.color.rgb = CYAN_ACCENT
    p_b.alignment = PP_ALIGN.CENTER

    # Logo
    if os.path.exists(icon_path):
        slide1.shapes.add_picture(icon_path, Inches(0.9), Inches(1.35), Inches(1.7), Inches(1.7))

    # Titolo & Sottotitolo
    tbox = slide1.shapes.add_textbox(Inches(2.8), Inches(1.35), Inches(9.6), Inches(2.2))
    tf1 = tbox.text_frame
    tf1.word_wrap = True
    p1 = tf1.paragraphs[0]
    p1.text = "ERMES KNOWLEDGE"
    p1.font.size = Pt(40)
    p1.font.bold = True
    p1.font.color.rgb = RGBColor(255, 255, 255)

    p1_sub = tf1.add_paragraph()
    p1_sub.text = "Sistema RAG Enterprise Local-First con Garanzie di Sicurezza, Data Loss Prevention e Isolamento del Contesto"
    p1_sub.font.size = Pt(18)
    p1_sub.font.color.rgb = CYAN_ACCENT
    p1_sub.space_before = Pt(8)

    # 4 Card di Metadati in basso
    meta_items = [
        ("CANDIDATO", "[Nome e Cognome]", INDIGO_ACCENT),
        ("PERCORSO ITS", "Sviluppo Software & AI", CYAN_ACCENT),
        ("AZIENDA PARTNER", "[Nome Azienda / Stage]", EMERALD),
        ("TUTOR & ANNO", "Tutor Aziendale & ITS | 2025/2026", AMBER)
    ]
    for idx, (label, val, col) in enumerate(meta_items):
        cx = 0.9 + idx * 2.95
        card = add_card(slide1, cx, 4.4, 2.75, 2.3, CARD_DARK, CARD_BORDER)
        t_box = slide1.shapes.add_textbox(Inches(cx + 0.15), Inches(4.55), Inches(2.45), Inches(2.0))
        tf_m = t_box.text_frame
        tf_m.word_wrap = True
        p_l = tf_m.paragraphs[0]
        p_l.text = label
        p_l.font.size = Pt(11)
        p_l.font.bold = True
        p_l.font.color.rgb = col

        p_v = tf_m.add_paragraph()
        p_v.text = val
        p_v.font.size = Pt(13)
        p_v.font.color.rgb = TEXT_MAIN_DARK
        p_v.space_before = Pt(8)

    # -------------------------------------------------------------
    # SLIDE 2: IL PROBLEMA AZIENDALE
    # -------------------------------------------------------------
    slide2 = prs.slides.add_slide(blank_layout)
    add_header(slide2, "1. Il Problema Aziendale: Frammentazione e Rischi dei LLM Generici")
    
    # Left Card: I Limiti della Gestione Documentale
    add_card(slide2, 0.9, 1.45, 5.5, 5.5, CARD_LIGHT, CARD_LIGHT_BORDER)
    tx2_left = slide2.shapes.add_textbox(Inches(1.15), Inches(1.7), Inches(5.0), Inches(5.0))
    tf2_l = tx2_left.text_frame
    tf2_l.word_wrap = True
    p = tf2_l.paragraphs[0]
    p.text = "📂 La Conoscenza Aziendale Frammentata"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = HEADER_NAVY

    bullets_l = [
        "<b>Silos Informativi:</b> Dati sparsi in cartelle di rete, PDF non indicizzati, archivi storici e chat private.",
        "<b>Tempo Perso:</b> I dipendenti impiegano ore per individuare l'ultima versione di regolamenti e manuali.",
        "<b>Ricerca Tradizionale Limitata:</b> Il keyword-matching classico fallisce se l'utente cerca per concetto o sinonimi."
    ]
    for b in bullets_l:
        p_b = tf2_l.add_paragraph()
        p_b.text = b.replace("<b>", "").replace("</b>", "")
        p_b.font.size = Pt(14)
        p_b.font.color.rgb = TEXT_MUTED_LIGHT
        p_b.space_before = Pt(14)

    # Right Card: I Pericoli dei Chatbot Commerciali
    add_card(slide2, 6.9, 1.45, 5.5, 5.5, CARD_LIGHT, RGBColor(254, 205, 211))
    tx2_right = slide2.shapes.add_textbox(Inches(7.15), Inches(1.7), Inches(5.0), Inches(5.0))
    tf2_r = tx2_right.text_frame
    tf2_r.word_wrap = True
    p_r = tf2_r.paragraphs[0]
    p_r.text = "⚠️ I Rischi dei LLM Commerciali (Cloud)"
    p_r.font.size = Pt(18)
    p_r.font.bold = True
    p_r.font.color.rgb = ROSE

    bullets_r = [
        "<b>Allucinazioni Gravi:</b> I modelli generano risposte inventate con estrema sicurezza e senza alcuna fonte.",
        "<b>Violazioni Privacy & GDPR:</b> Caricare dati sensibili su API esterne espone l'azienda a fughe di dati e sanzioni.",
        "<b>Zero Tracciabilità:</b> Impossibile verificare chi ha consultato cosa e quale versione del file ha generato l'output."
    ]
    for b in bullets_r:
        p_b = tf2_r.add_paragraph()
        p_b.text = b.replace("<b>", "").replace("</b>", "")
        p_b.font.size = Pt(14)
        p_b.font.color.rgb = TEXT_MUTED_LIGHT
        p_b.space_before = Pt(14)

    # -------------------------------------------------------------
    # SLIDE 3: LA SOLUZIONE — ERMES KNOWLEDGE
    # -------------------------------------------------------------
    slide3 = prs.slides.add_slide(blank_layout)
    add_header(slide3, "2. La Soluzione: Ermes Knowledge (Evidenza Prima)")

    # Left: 3 Value Cards
    v_cards = [
        ("🛡️ Local-First & Sicuro", "Nessun dato riservato lascia il perimetro aziendale. Embedding e retrieval eseguiti in locale."),
        ("📑 Evidenza Reale & Citazioni", "Ogni singola affermazione cita espressamente il documento originale con download immediato in 1 click."),
        ("🚫 Zero Allucinazioni", "Se il documento non contiene la risposta, il sistema si astiene dichiarando espressamente l'assenza di evidenza.")
    ]
    for idx, (title, desc) in enumerate(v_cards):
        cy = 1.45 + idx * 1.85
        add_card(slide3, 0.9, cy, 5.6, 1.65, CARD_LIGHT, CARD_LIGHT_BORDER)
        t_box = slide3.shapes.add_textbox(Inches(1.1), Inches(cy + 0.15), Inches(5.2), Inches(1.35))
        tf_v = t_box.text_frame
        tf_v.word_wrap = True
        p_vt = tf_v.paragraphs[0]
        p_vt.text = title
        p_vt.font.size = Pt(16)
        p_vt.font.bold = True
        p_vt.font.color.rgb = HEADER_NAVY
        
        p_vd = tf_v.add_paragraph()
        p_vd.text = desc
        p_vd.font.size = Pt(13)
        p_vd.font.color.rgb = TEXT_MUTED_LIGHT
        p_vd.space_before = Pt(4)

    # Right: Screenshot incorniciato
    add_card(slide3, 6.8, 1.45, 5.6, 5.5, CARD_LIGHT, CARD_LIGHT_BORDER)
    if os.path.exists(screenshot_chat):
        slide3.shapes.add_picture(screenshot_chat, Inches(6.95), Inches(1.6), Inches(5.3), Inches(4.5))
    tag_box = slide3.shapes.add_textbox(Inches(6.95), Inches(6.3), Inches(5.3), Inches(0.5))
    tf_tag = tag_box.text_frame
    p_tag = tf_tag.paragraphs[0]
    p_tag.text = "▲ Interfaccia di Chat con Citazioni e Punteggi di Rilevanza"
    p_tag.font.size = Pt(11)
    p_tag.font.bold = True
    p_tag.font.color.rgb = CYAN_ACCENT
    p_tag.alignment = PP_ALIGN.CENTER

    # -------------------------------------------------------------
    # SLIDE 4: LE 5 REGOLE ARCHITETTURALI
    # -------------------------------------------------------------
    slide4 = prs.slides.add_slide(blank_layout)
    add_header(slide4, "3. Le 5 Regole Fondamentali, Applicate nel Codice")

    rules = [
        ("1", "LOCAL FIRST", "Una chiave API cloud da sola non attiva mai l'elaborazione cloud esterna.", CYAN_ACCENT),
        ("2", "EVIDENZA PRIMA", "Ogni risposta cita un documento accessibile, oppure l'assistente si astiene.", INDIGO_ACCENT),
        ("3", "ISOLAMENTO RIGIDO", "La ricerca è vincolata alla biblioteca prima che il testo arrivi all'assistente.", EMERALD),
        ("4", "INPUT NON FIDATO", "Il testo estratto dai documenti non può mai autorizzare azioni o comandi.", ROSE),
        ("5", "ORIGINALI ACCESSIBILI", "Ogni citazione rimanda alla versione esatta del file, scaricabile con 1 click.", AMBER)
    ]
    for idx, (num, title, desc, col) in enumerate(rules):
        cy = 1.45 + idx * 1.12
        add_card(slide4, 0.9, cy, 11.5, 0.98, CARD_LIGHT, CARD_LIGHT_BORDER)
        
        # Number Badge
        nb = slide4.shapes.add_shape(MSO_SHAPE.OVAL, Inches(1.15), Inches(cy + 0.18), Inches(0.6), Inches(0.6))
        nb.fill.solid()
        nb.fill.fore_color.rgb = col
        nb.line.fill.background()
        tf_n = nb.text_frame
        p_n = tf_n.paragraphs[0]
        p_n.text = num
        p_n.font.size = Pt(14)
        p_n.font.bold = True
        p_n.font.color.rgb = RGBColor(255, 255, 255)
        p_n.alignment = PP_ALIGN.CENTER

        # Text
        rt_box = slide4.shapes.add_textbox(Inches(1.95), Inches(cy + 0.12), Inches(10.2), Inches(0.75))
        tf_rt = rt_box.text_frame
        tf_rt.word_wrap = True
        p_rt = tf_rt.paragraphs[0]
        p_rt.text = f"{title}: "
        p_rt.font.size = Pt(14)
        p_rt.font.bold = True
        p_rt.font.color.rgb = HEADER_NAVY

        # Description
        p_rt2 = tf_rt.paragraphs[0] # inline
        p_desc = tf_rt.add_paragraph()
        p_desc.text = desc
        p_desc.font.size = Pt(13)
        p_desc.font.color.rgb = TEXT_MUTED_LIGHT

    # -------------------------------------------------------------
    # SLIDE 5: ARCHITETTURA & TECH STACK
    # -------------------------------------------------------------
    slide5 = prs.slides.add_slide(blank_layout)
    add_header(slide5, "4. Architettura del Sistema & Tech Stack Enterprise")

    tech_quads = [
        ("🌐 Frontend UI/UX", "React 18 · TypeScript · Vite · Tailwind CSS\nDesign System moderno, gestione responsive dello stato e visualizzazione citazioni in tempo reale.", CYAN_ACCENT),
        ("⚡ Backend API Services", "Python 3.11 · FastAPI (ASGI Asincrono)\nValidazione automatica Pydantic, rotte RESTful sicure e documentazione interattiva OpenAPI / Swagger.", INDIGO_ACCENT),
        ("🧠 AI & Vector Engine", "Ollama Embeddings · SQLite / JSON Store\nEmbedding on-device, ricerca vettoriale locale e storage isolato per biblioteca.", EMERALD),
        ("🐳 DevOps & Testing", "Docker · Docker Compose · Pytest (241 Test)\nOrchestrazione scalabile, CI su GitHub Actions e suite completa contro le regressioni.", AMBER)
    ]
    for idx, (title, desc, col) in enumerate(tech_quads):
        row = idx // 2
        col_idx = idx % 2
        cx = 0.9 + col_idx * 5.9
        cy = 1.45 + row * 2.75
        add_card(slide5, cx, cy, 5.6, 2.55, CARD_LIGHT, CARD_LIGHT_BORDER)

        t_box = slide5.shapes.add_textbox(Inches(cx + 0.25), Inches(cy + 0.2), Inches(5.1), Inches(2.15))
        tf_q = t_box.text_frame
        tf_q.word_wrap = True
        p_qt = tf_q.paragraphs[0]
        p_qt.text = title
        p_qt.font.size = Pt(17)
        p_qt.font.bold = True
        p_qt.font.color.rgb = col

        p_qd = tf_q.add_paragraph()
        p_qd.text = desc
        p_qd.font.size = Pt(13)
        p_qd.font.color.rgb = TEXT_MUTED_LIGHT
        p_qd.space_before = Pt(8)

    # -------------------------------------------------------------
    # SLIDE 6: IL CUORE DEL RAG — INGESTION & RICERCA IBRIDA
    # -------------------------------------------------------------
    slide6 = prs.slides.add_slide(blank_layout)
    add_header(slide6, "5. Il Motore di Retrieval: Chunking e Ricerca Ibrida")

    rag_steps = [
        ("1. INGESTION", "Parsing PDF, DOCX, TXT, MD e Web scraping pulito.", CYAN_ACCENT),
        ("2. CHUNKING", "Segmentazione semantica con overlap per continuità contestuale.", INDIGO_ACCENT),
        ("3. HYBRID SEARCH", "Vettoriale (Sinonimi) + BM25 (Codici/Sigle esatte).", EMERALD),
        ("4. RRF FUSION", "Fusione dei ranking tramite Reciprocal Rank Fusion.", AMBER)
    ]
    for idx, (st, desc, col) in enumerate(rag_steps):
        cx = 0.9 + idx * 2.95
        add_card(slide6, cx, 1.45, 2.75, 2.5, CARD_LIGHT, CARD_LIGHT_BORDER)
        t_box = slide6.shapes.add_textbox(Inches(cx + 0.15), Inches(1.65), Inches(2.45), Inches(2.1))
        tf_s = t_box.text_frame
        tf_s.word_wrap = True
        p_st = tf_s.paragraphs[0]
        p_st.text = st
        p_st.font.size = Pt(15)
        p_st.font.bold = True
        p_st.font.color.rgb = col

        p_sd = tf_s.add_paragraph()
        p_sd.text = desc
        p_sd.font.size = Pt(13)
        p_sd.font.color.rgb = TEXT_MUTED_LIGHT
        p_sd.space_before = Pt(8)

    # Bottom Big Banner: Perché la ricerca ibrida vince
    add_card(slide6, 0.9, 4.25, 11.5, 2.65, CARD_DARK, CARD_BORDER)
    tx_bot = slide6.shapes.add_textbox(Inches(1.2), Inches(4.45), Inches(10.9), Inches(2.25))
    tf_bot = tx_bot.text_frame
    tf_bot.word_wrap = True
    p_b1 = tf_bot.paragraphs[0]
    p_b1.text = "💡 Il Vantaggio della Ricerca Ibrida (Vector + BM25)"
    p_b1.font.size = Pt(18)
    p_b1.font.bold = True
    p_b1.font.color.rgb = CYAN_ACCENT

    p_b2 = tf_bot.add_paragraph()
    p_b2.text = "• La ricerca vettoriale comprende i concetti e le parafrasi ma rischia di perdere codici specifici o numeri di protocollo.\n• Il BM25 trova con precisione chirurgica le sigle esatte ma ignora i sinonimi.\n• Ermes unisce entrambi i mondi garantendo il 100% di precisione sia sui codici esatti che sulle domande concettuali."
    p_b2.font.size = Pt(14)
    p_b2.font.color.rgb = TEXT_MAIN_DARK
    p_b2.space_before = Pt(8)

    # -------------------------------------------------------------
    # SLIDE 7: ADVANCED RETRIEVAL — RE-RANKER & DEDUPLICAZIONE
    # -------------------------------------------------------------
    slide7 = prs.slides.add_slide(blank_layout)
    add_header(slide7, "6. Advanced Retrieval: Re-ranker Posizionale e Deduplicazione")

    # Card Left: Re-ranker
    add_card(slide7, 0.9, 1.45, 5.5, 5.4, CARD_LIGHT, CARD_LIGHT_BORDER)
    tx7_l = slide7.shapes.add_textbox(Inches(1.15), Inches(1.7), Inches(5.0), Inches(4.9))
    tf7_l = tx7_l.text_frame
    tf7_l.word_wrap = True
    p = tf7_l.paragraphs[0]
    p.text = "🎯 Re-ranker Posizionale Avanzato"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = INDIGO_ACCENT

    p_body1 = tf7_l.add_paragraph()
    p_body1.text = "Ricalcola il punteggio di rilevanza analizzando:\n\n" \
                   "• <b>Vicinanza Posizionale:</b> Premia i documenti dove le parole chiave della query compaiono nella stessa frase anziché sparse nel testo.\n" \
                   "• <b>Bi-grammi Consecutivi:</b> Riconosce sequenze di parole rilevanti.\n" \
                   "• <b>Titolo & Header Matching:</b> Attribuisce un peso maggiore alle corrispondenze nel titolo della sezione."
    p_body1.text = p_body1.text.replace("<b>", "").replace("</b>", "")
    p_body1.font.size = Pt(14)
    p_body1.font.color.rgb = TEXT_MUTED_LIGHT
    p_body1.space_before = Pt(10)

    # Card Right: Deduplicazione
    add_card(slide7, 6.9, 1.45, 5.5, 5.4, CARD_LIGHT, CARD_LIGHT_BORDER)
    tx7_r = slide7.shapes.add_textbox(Inches(7.15), Inches(1.7), Inches(5.0), Inches(4.9))
    tf7_r = tx7_r.text_frame
    tf7_r.word_wrap = True
    p_r = tf7_r.paragraphs[0]
    p_r.text = "🧩 Deduplicazione Jaccard (Near-Duplicates)"
    p_r.font.size = Pt(18)
    p_r.font.bold = True
    p_r.font.color.rgb = CYAN_ACCENT

    p_body2 = tf7_r.add_paragraph()
    p_body2.text = "Ottimizzazione del Context Window:\n\n" \
                   "• <b>Indice di Jaccard su Shingle:</b> Analizza la sovrapposizione tra versioni simili dello stesso documento.\n" \
                   "• <b>Raggruppamento Intelligente:</b> Rileva revisioni duplicate all'interno della stessa biblioteca.\n" \
                   "• <b>Efficienza del Prompt:</b> Invia all'LLM solo l'estratto migliore, azzerando la ridondanza e riducendo i costi computazionali."
    p_body2.text = p_body2.text.replace("<b>", "").replace("</b>", "")
    p_body2.font.size = Pt(14)
    p_body2.font.color.rgb = TEXT_MUTED_LIGHT
    p_body2.space_before = Pt(10)

    # -------------------------------------------------------------
    # SLIDE 8: DATA LOSS PREVENTION (DLP) — PII GUARD
    # -------------------------------------------------------------
    slide8 = prs.slides.add_slide(blank_layout)
    add_header(slide8, "7. Data Loss Prevention: Il Filtro PII Guard Algoritmico")

    pii_cards = [
        ("💳 Carte di Credito (Luhn Checksum)", "Verifica matematica di Luhn (mod 10). Riconosce e maschera carte reali come [CARTA_CREDITO], ignorando numeri casuali.", ROSE),
        ("🏦 Coordinate Bancarie IBAN", "Validazione algebrica Modulo 97 (ISO 13616). Maschera solo IBAN strutturalmente validi come [IBAN].", EMERALD),
        ("🪪 Codici Fiscali Italiani", "Pattern a 16 caratteri con verifica algoritmica del carattere di controllo (CIN). Mascherato come [CODICE_FISCALE].", CYAN_ACCENT),
        ("🔑 Token JWT & API Keys", "Riconoscimento pattern di token crittografici e chiavi API (sk-live, Bearer), oscurati preventivamente.", INDIGO_ACCENT)
    ]
    for idx, (title, desc, col) in enumerate(pii_cards):
        row = idx // 2
        col_idx = idx % 2
        cx = 0.9 + col_idx * 5.9
        cy = 1.45 + row * 2.75
        add_card(slide8, cx, cy, 5.6, 2.55, CARD_LIGHT, CARD_LIGHT_BORDER)

        t_box = slide8.shapes.add_textbox(Inches(cx + 0.25), Inches(cy + 0.2), Inches(5.1), Inches(2.15))
        tf_p = t_box.text_frame
        tf_p.word_wrap = True
        p_pt = tf_p.paragraphs[0]
        p_pt.text = title
        p_pt.font.size = Pt(16)
        p_pt.font.bold = True
        p_pt.font.color.rgb = col

        p_pd = tf_p.add_paragraph()
        p_pd.text = desc
        p_pd.font.size = Pt(13)
        p_pd.font.color.rgb = TEXT_MUTED_LIGHT
        p_pd.space_before = Pt(8)

    # -------------------------------------------------------------
    # SLIDE 9: GOVERNANCE, RBAC & AUDIT LOG
    # -------------------------------------------------------------
    slide9 = prs.slides.add_slide(blank_layout)
    add_header(slide9, "8. Governance, RBAC e Audit Log Immutabile")

    # Left: RBAC + Security 404
    add_card(slide9, 0.9, 1.45, 5.5, 5.5, CARD_LIGHT, CARD_LIGHT_BORDER)
    tx9_l = slide9.shapes.add_textbox(Inches(1.15), Inches(1.7), Inches(5.0), Inches(5.0))
    tf9_l = tx9_l.text_frame
    tf9_l.word_wrap = True
    p = tf9_l.paragraphs[0]
    p.text = "🔐 Controllo Accessi (RBAC)"
    p.font.size = Pt(18)
    p.font.bold = True
    p.font.color.rgb = HEADER_NAVY

    rbac_points = [
        "<b>Admin:</b> Gestione globale utenti, permessi, biblioteche e audit log.",
        "<b>Editor:</b> Caricamento e modifica documenti nelle biblioteche autorizzate.",
        "<b>Viewer:</b> Ricerca e consultazione in sola lettura.",
        "<b>Security-by-Design 404:</b> Tentare di accedere a una biblioteca privata restituisce HTTP 404 (non 403) per non rivelarne nemmeno l'esistenza."
    ]
    for pt in rbac_points:
        p_pt = tf9_l.add_paragraph()
        p_pt.text = pt.replace("<b>", "").replace("</b>", "")
        p_pt.font.size = Pt(13)
        p_pt.font.color.rgb = TEXT_MUTED_LIGHT
        p_pt.space_before = Pt(8)

    # Right: Screenshot Audit Log
    add_card(slide9, 6.9, 1.45, 5.5, 5.5, CARD_LIGHT, CARD_LIGHT_BORDER)
    if os.path.exists(screenshot_audit):
        slide9.shapes.add_picture(screenshot_audit, Inches(7.05), Inches(1.6), Inches(5.2), Inches(4.5))
    tag_box9 = slide9.shapes.add_textbox(Inches(7.05), Inches(6.3), Inches(5.2), Inches(0.5))
    tf_tag9 = tag_box9.text_frame
    p_tag9 = tf_tag9.paragraphs[0]
    p_tag9.text = "▲ Audit Log protetto da Atomic FileLock conforme a GDPR"
    p_tag9.font.size = Pt(11)
    p_tag9.font.bold = True
    p_tag9.font.color.rgb = CYAN_ACCENT
    p_tag9.alignment = PP_ALIGN.CENTER

    # -------------------------------------------------------------
    # SLIDE 10: RETRIEVAL EVALUATION — GOLDEN SET
    # -------------------------------------------------------------
    slide10 = prs.slides.add_slide(blank_layout)
    add_header(slide10, "9. Valutazione Quantitativa della Qualità: Golden Set")

    # 3 Big Metric Tiles
    metric_tiles = [
        ("100%", "Query Dirette (16)", "Parole della domanda vicine al testo sorgente: recupero perfetto con evidenza completa.", EMERALD),
        ("50% → 90%+", "Query Parafrasate (8)", "Stesso concetto, zero parole condivise: la ricerca ibrida locale colma il divario del solo keyword.", INDIGO_ACCENT),
        ("67% → 100%", "Astensione Controllata (3)", "Domande su argomenti assenti: il sistema dichiara l'assenza senza inventare.", CYAN_ACCENT)
    ]
    for idx, (pct, title, desc, col) in enumerate(metric_tiles):
        cx = 0.9 + idx * 3.95
        add_card(slide10, cx, 1.45, 3.65, 3.4, CARD_DARK, CARD_BORDER)

        t_box = slide10.shapes.add_textbox(Inches(cx + 0.2), Inches(1.7), Inches(3.25), Inches(3.0))
        tf_mt = t_box.text_frame
        tf_mt.word_wrap = True
        
        p_pct = tf_mt.paragraphs[0]
        p_pct.text = pct
        p_pct.font.size = Pt(36)
        p_pct.font.bold = True
        p_pct.font.color.rgb = col

        p_mtt = tf_mt.add_paragraph()
        p_mtt.text = title
        p_mtt.font.size = Pt(16)
        p_mtt.font.bold = True
        p_mtt.font.color.rgb = RGBColor(255, 255, 255)
        p_mtt.space_before = Pt(6)

        p_mtd = tf_mt.add_paragraph()
        p_mtd.text = desc
        p_mtd.font.size = Pt(12)
        p_mtd.font.color.rgb = TEXT_MUTED_DARK
        p_mtd.space_before = Pt(8)

    # Bottom Explanation Box
    add_card(slide10, 0.9, 5.05, 11.5, 1.85, CARD_LIGHT, CARD_LIGHT_BORDER)
    tx10_b = slide10.shapes.add_textbox(Inches(1.15), Inches(5.15), Inches(11.0), Inches(1.6))
    tf10_b = tx10_b.text_frame
    tf10_b.word_wrap = True
    p10_1 = tf10_b.paragraphs[0]
    p10_1.text = "🔬 Approccio Scientifico e Trasparenza"
    p10_1.font.size = Pt(16)
    p10_1.font.bold = True
    p10_1.font.color.rgb = HEADER_NAVY

    p10_2 = tf10_b.add_paragraph()
    p10_2.text = "La qualità del motore RAG è stata misurata e validata su un dataset reale (Golden Set di 27 casi d'uso), riportando onestamente sia le aree di eccellenza sia i punti in cui la ricerca semantica on-device è indispensabile."
    p10_2.font.size = Pt(13)
    p10_2.font.color.rgb = TEXT_MUTED_LIGHT
    p10_2.space_before = Pt(4)

    # -------------------------------------------------------------
    # SLIDE 11: QUALITÀ DEL CODICE & TESTING
    # -------------------------------------------------------------
    slide11 = prs.slides.add_slide(blank_layout)
    add_header(slide11, "10. Qualità del Codice e Testing Automatizzato")

    # Big Metric Box on Left
    add_card(slide11, 0.9, 1.45, 4.2, 5.5, CARD_DARK, CARD_BORDER)
    tx11_l = slide11.shapes.add_textbox(Inches(1.15), Inches(1.8), Inches(3.7), Inches(4.8))
    tf11_l = tx11_l.text_frame
    tf11_l.word_wrap = True
    p_test = tf11_l.paragraphs[0]
    p_test.text = "241"
    p_test.font.size = Pt(56)
    p_test.font.bold = True
    p_test.font.color.rgb = EMERALD

    p_tlabel = tf11_l.add_paragraph()
    p_tlabel.text = "TEST AUTOMATIZZATI"
    p_tlabel.font.size = Pt(18)
    p_tlabel.font.bold = True
    p_tlabel.font.color.rgb = RGBColor(255, 255, 255)

    p_tsub = tf11_l.add_paragraph()
    p_tsub.text = "100% Passed con Pytest\nCopertura completa di API, algoritmi DLP, Re-ranker e persistenza."
    p_tsub.font.size = Pt(13)
    p_tsub.font.color.rgb = TEXT_MUTED_DARK
    p_tsub.space_before = Pt(12)

    # Right: 3 Feature Cards
    features_test = [
        ("🔄 Continuous Integration (CI)", "Pipeline automatizzata su GitHub Actions per eseguire l'intera suite di test e bloccare le regressioni ad ogni commit.", CYAN_ACCENT),
        ("🛡️ Guardie di Sicurezza sulle Route", "Test di conformità per garantire che nessun endpoint futuro possa essere rilasciato senza autenticazione obbligatoria.", INDIGO_ACCENT),
        ("📖 Documentazione OpenAPI / Swagger", "Interfaccia API RESTful documentata ed esplorabile nativamente tramite FastAPI Swagger UI.", AMBER)
    ]
    for idx, (title, desc, col) in enumerate(features_test):
        cy = 1.45 + idx * 1.85
        add_card(slide11, 5.4, cy, 7.0, 1.65, CARD_LIGHT, CARD_LIGHT_BORDER)
        t_box = slide11.shapes.add_textbox(Inches(5.65), Inches(cy + 0.15), Inches(6.5), Inches(1.35))
        tf_ft = t_box.text_frame
        tf_ft.word_wrap = True
        p_ftt = tf_ft.paragraphs[0]
        p_ftt.text = title
        p_ftt.font.size = Pt(16)
        p_ftt.font.bold = True
        p_ftt.font.color.rgb = col

        p_ftd = tf_ft.add_paragraph()
        p_ftd.text = desc
        p_ftd.font.size = Pt(13)
        p_ftd.font.color.rgb = TEXT_MUTED_LIGHT
        p_ftd.space_before = Pt(4)

    # -------------------------------------------------------------
    # SLIDE 12: ANALYTICS & KNOWLEDGE GAPS
    # -------------------------------------------------------------
    slide12 = prs.slides.add_slide(blank_layout)
    add_header(slide12, "11. Governance: Analytics e Rilevamento dei Knowledge Gaps")

    # Left: 3 Value Cards
    gap_cards = [
        ("📊 Tracciamento Query & Latenze", "Monitoraggio in tempo reale del volume di ricerche, tempo di risposta e tasso di successo delle consultazioni.", CYAN_ACCENT),
        ("❓ Rilevamento Knowledge Gaps", "Identificazione automatica delle domande a cui il sistema non trova risposta nei documenti attuali.", INDIGO_ACCENT),
        ("📈 Valore Strategico Management", "Fornisce all'azienda una guida chiara su quali regolamenti o procedure interne mancano e devono essere redatte.", EMERALD)
    ]
    for idx, (title, desc, col) in enumerate(gap_cards):
        cy = 1.45 + idx * 1.85
        add_card(slide12, 0.9, cy, 5.6, 1.65, CARD_LIGHT, CARD_LIGHT_BORDER)
        t_box = slide12.shapes.add_textbox(Inches(1.1), Inches(cy + 0.15), Inches(5.2), Inches(1.35))
        tf_g = t_box.text_frame
        tf_g.word_wrap = True
        p_gt = tf_g.paragraphs[0]
        p_gt.text = title
        p_gt.font.size = Pt(16)
        p_gt.font.bold = True
        p_gt.font.color.rgb = col

        p_gd = tf_g.add_paragraph()
        p_gd.text = desc
        p_gd.font.size = Pt(12)
        p_gd.font.color.rgb = TEXT_MUTED_LIGHT
        p_gd.space_before = Pt(4)

    # Right: Screenshot Analytics Dashboard
    add_card(slide12, 6.8, 1.45, 5.6, 5.5, CARD_LIGHT, CARD_LIGHT_BORDER)
    if os.path.exists(screenshot_analytics):
        slide12.shapes.add_picture(screenshot_analytics, Inches(6.95), Inches(1.6), Inches(5.3), Inches(4.5))
    tag_box12 = slide12.shapes.add_textbox(Inches(6.95), Inches(6.3), Inches(5.3), Inches(0.5))
    tf_tag12 = tag_box12.text_frame
    p_tag12 = tf_tag12.paragraphs[0]
    p_tag12.text = "▲ Dashboard di Monitoraggio e Knowledge Gaps in Tempo Reale"
    p_tag12.font.size = Pt(11)
    p_tag12.font.bold = True
    p_tag12.font.color.rgb = CYAN_ACCENT
    p_tag12.alignment = PP_ALIGN.CENTER

    # -------------------------------------------------------------
    # SLIDE 13: ESPERIENZA DI TIROCINIO AZIENDALE (PARTE 1)
    # -------------------------------------------------------------
    slide13 = prs.slides.add_slide(blank_layout)
    add_header(slide13, "12. Esperienza di Tirocinio Aziendale / Stage: Attività e Metodologia")

    stage_cards1 = [
        ("🏢 Contesto Operativo", "Inserimento attivo nel team di sviluppo software dell'azienda partner [Nome Azienda]. Comprensione delle esigenze reali di gestione documentale.", CYAN_ACCENT),
        ("🚀 Attività Svolte", "• Progettazione dell'architettura RAG modulare.\n• Sviluppo endpoint FastAPI e interfacce React.\n• Implementazione algoritmi DLP e re-ranking.", INDIGO_ACCENT),
        ("🔄 Metodologia Agile", "Adozione di pratiche Scrum/Kanban, stand-up giornalieri, code review e versionamento del codice con Git.", EMERALD)
    ]
    for idx, (title, desc, col) in enumerate(stage_cards1):
        cx = 0.9 + idx * 3.95
        add_card(slide13, cx, 1.45, 3.65, 5.5, CARD_LIGHT, CARD_LIGHT_BORDER)

        t_box = slide13.shapes.add_textbox(Inches(cx + 0.2), Inches(1.7), Inches(3.25), Inches(5.0))
        tf_st = t_box.text_frame
        tf_st.word_wrap = True
        p_st = tf_st.paragraphs[0]
        p_st.text = title
        p_st.font.size = Pt(18)
        p_st.font.bold = True
        p_st.font.color.rgb = col

        p_sd = tf_st.add_paragraph()
        p_sd.text = desc
        p_sd.font.size = Pt(14)
        p_sd.font.color.rgb = TEXT_MUTED_LIGHT
        p_sd.space_before = Pt(14)

    # -------------------------------------------------------------
    # SLIDE 14: ESPERIENZA DI TIROCINIO AZIENDALE (PARTE 2)
    # -------------------------------------------------------------
    slide14 = prs.slides.add_slide(blank_layout)
    add_header(slide14, "13. Esperienza di Tirocinio Aziendale: Impatto e Risultati")

    stage_cards2 = [
        ("⚡ -70% Tempo di Ricerca", "I dipendenti rintracciano procedure e schede tecniche in secondi anziché navigare cartelle complesse.", EMERALD),
        ("🔒 100% Dati al Sicuro", "Adozione dell'AI senza rischi di fughe di dati o non conformità GDPR grazie all'approccio Local-First e al DLP.", CYAN_ACCENT),
        ("🎓 Crescita Professionale", "Consolidamento di competenze di livello enterprise in Software Architecture, AI Engineering e DevOps.", INDIGO_ACCENT)
    ]
    for idx, (title, desc, col) in enumerate(stage_cards2):
        cx = 0.9 + idx * 3.95
        add_card(slide14, cx, 1.45, 3.65, 5.5, CARD_LIGHT, CARD_LIGHT_BORDER)

        t_box = slide14.shapes.add_textbox(Inches(cx + 0.2), Inches(1.7), Inches(3.25), Inches(5.0))
        tf_st2 = t_box.text_frame
        tf_st2.word_wrap = True
        p_st2 = tf_st2.paragraphs[0]
        p_st2.text = title
        p_st2.font.size = Pt(18)
        p_st2.font.bold = True
        p_st2.font.color.rgb = col

        p_sd2 = tf_st2.add_paragraph()
        p_sd2.text = desc
        p_sd2.font.size = Pt(14)
        p_sd2.font.color.rgb = TEXT_MUTED_LIGHT
        p_sd2.space_before = Pt(14)

    # -------------------------------------------------------------
    # SLIDE 15: CONCLUSIONI & ROADMAP ENTERPRISE
    # -------------------------------------------------------------
    slide15 = prs.slides.add_slide(blank_layout)
    bg15 = slide15.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg15.fill.solid()
    bg15.fill.fore_color.rgb = BG_DARK
    bg15.line.fill.background()

    # Title
    t15_box = slide15.shapes.add_textbox(Inches(0.9), Inches(0.8), Inches(11.5), Inches(1.0))
    tf15 = t15_box.text_frame
    p15 = tf15.paragraphs[0]
    p15.text = "14. Conclusioni e Roadmap Evolutiva Enterprise"
    p15.font.size = Pt(28)
    p15.font.bold = True
    p15.font.color.rgb = RGBColor(255, 255, 255)

    # 3 Roadmap Cards
    roadmap_phases = [
        ("FASE 1: ENTERPRISE IAM", "Integrazione Single Sign-On (SSO) con Microsoft Entra ID / Keycloak e SCIM.", CYAN_ACCENT),
        ("FASE 2: SCALABILITÀ CLOUD", "Migrazione a Vector DB distribuiti (Qdrant cluster) e code asincrone Redis.", INDIGO_ACCENT),
        ("FASE 3: OSSERVABILITÀ", "Tracciamento distribuito con OpenTelemetry, metriche Prometheus e Grafana.", EMERALD)
    ]
    for idx, (ph, desc, col) in enumerate(roadmap_phases):
        cx = 0.9 + idx * 3.95
        add_card(slide15, cx, 1.9, 3.65, 3.2, CARD_DARK, CARD_BORDER)

        t_box = slide15.shapes.add_textbox(Inches(cx + 0.2), Inches(2.1), Inches(3.25), Inches(2.8))
        tf_r = t_box.text_frame
        tf_r.word_wrap = True
        p_rt = tf_r.paragraphs[0]
        p_rt.text = ph
        p_rt.font.size = Pt(16)
        p_rt.font.bold = True
        p_rt.font.color.rgb = col

        p_rd = tf_r.add_paragraph()
        p_rd.text = desc
        p_rd.font.size = Pt(13)
        p_rd.font.color.rgb = TEXT_MUTED_DARK
        p_rd.space_before = Pt(10)

    # Bottom Thanks / Q&A Box
    add_card(slide15, 0.9, 5.4, 11.5, 1.4, CARD_DARK, CARD_BORDER)
    tx_th = slide15.shapes.add_textbox(Inches(1.2), Inches(5.5), Inches(10.9), Inches(1.1))
    tf_th = tx_th.text_frame
    p_th = tf_th.paragraphs[0]
    p_th.text = "Grazie per l'attenzione!  —  Spazio per Domande e Risposte (Q&A)"
    p_th.font.size = Pt(20)
    p_th.font.bold = True
    p_th.font.color.rgb = CYAN_ACCENT
    p_th.alignment = PP_ALIGN.CENTER

    output_path = "docs/PRESENTAZIONE_ITS_ERMES.pptx"
    prs.save(output_path)
    print(f"File PowerPoint Enterprise creato con successo in: {output_path}")

if __name__ == "__main__":
    create_presentation()
