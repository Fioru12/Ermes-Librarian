"""
welcome_ui.py
Welcome screen, feedback system, help modal per l'applicazione Ermes.
"""
import html

import streamlit as st


def render_welcome_screen(dark_mode: bool = True):
    """
    Schermata di benvenuto per nuovi utenti (quando non ci sono messaggi
    e nessun modulo e' selezionato). Mostra una guida rapida all'uso.
    """
    _ = dark_mode
    st.markdown(
        """
        <div class="ws-welcome">
            <div class="ws-welcome-header">
                <div class="ws-welcome-icon">ER</div>
                <div>
                    <div class="ws-welcome-title">Benvenuto in Ermes</div>
                    <div class="ws-welcome-sub">
                        Knowledge hub locale per consultazione documentale e bozze guidate
                    </div>
                </div>
            </div>
            <div class="ws-welcome-band">
                <div class="ws-welcome-band-item">
                    <div class="ws-welcome-band-label">Catalogo</div>
                    <div class="ws-welcome-band-text">Risposte ancorate ai documenti ufficiali caricati</div>
                </div>
                <div class="ws-welcome-band-item">
                    <div class="ws-welcome-band-label">Bozze AI</div>
                    <div class="ws-welcome-band-text">Formule proposte da validare prima dei test operativi</div>
                </div>
                <div class="ws-welcome-band-item">
                    <div class="ws-welcome-band-label">Offline</div>
                    <div class="ws-welcome-band-text">Dati, modelli e conversazioni restano all'interno dell'ambiente locale</div>
                </div>
            </div>
            <div class="ws-welcome-grid">
                <div class="ws-welcome-card">
                    <div class="ws-welcome-card-icon">01</div>
                    <div class="ws-welcome-card-title">Seleziona un modulo</div>
                    <div class="ws-welcome-card-text">
                        Ogni modulo raccoglie documentazione specifica di reparto,
                        processo o dominio applicativo.
                    </div>
                </div>
                <div class="ws-welcome-card">
                    <div class="ws-welcome-card-icon">02</div>
                    <div class="ws-welcome-card-title">Scegli la modalita'</div>
                    <div class="ws-welcome-card-text">
                        Consulta catalogo per risposte ufficiali. Genera formula
                        per una bozza separata dal materiale documentale.
                    </div>
                </div>
                <div class="ws-welcome-card">
                    <div class="ws-welcome-card-icon">03</div>
                    <div class="ws-welcome-card-title">Fai una domanda</div>
                    <div class="ws-welcome-card-text">
                        Scrivi in linguaggio naturale quello che ti serve e
                        usa le fonti per capire subito da dove arriva la risposta.
                    </div>
                </div>
                <div class="ws-welcome-card">
                    <div class="ws-welcome-card-icon">04</div>
                    <div class="ws-welcome-card-title">Valida il risultato</div>
                    <div class="ws-welcome-card-text">
                        Controlla confidenza, fonti, sintassi e note operative
                        prima di condividere o testare il contenuto.
                    </div>
                </div>
            </div>
            <div class="ws-welcome-tips">
                <div class="ws-welcome-tips-title">Guida rapida</div>
                <ul class="ws-welcome-tips-list">
                    <li>Usa <strong>Consulta catalogo</strong> quando vuoi una risposta supportata dai documenti indicizzati</li>
                    <li>Usa <strong>Genera formula</strong> solo per bozze da rivedere e testare</li>
                    <li>Carica nuovi file da <strong>Admin documenti</strong> e poi clicca <strong>Aggiorna</strong></li>
                    <li>Apri <strong>Fonti</strong> per vedere i passaggi testuali usati dal sistema</li>
                    <li>Scarica la conversazione dalla sidebar quando vuoi conservare un test o una demo</li>
                </ul>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_feedback_buttons(resp_num: int):
    """
    Renderizza pulsanti di feedback (utile/non utile) per una risposta.
    Salva il feedback in st.session_state per persistenza nella sessione.
    """
    fb_key = f"feedback_{resp_num}"
    if fb_key not in st.session_state:
        st.session_state[fb_key] = None

    current = st.session_state[fb_key]

    cols = st.columns([1, 1, 4])
    with cols[0]:
        if st.button("Utile", key=f"fb_up_{resp_num}", use_container_width=True,
                     type="secondary" if current != "up" else "primary"):
            if current == "up":
                st.session_state[fb_key] = None
            else:
                st.session_state[fb_key] = "up"
            st.rerun()
    with cols[1]:
        if st.button("Non utile", key=f"fb_down_{resp_num}", use_container_width=True,
                     type="secondary" if current != "down" else "primary"):
            if current == "down":
                st.session_state[fb_key] = None
            else:
                st.session_state[fb_key] = "down"
            st.rerun()
    with cols[2]:
        if current == "up":
            st.markdown(
                '<span class="ws-feedback-up">Feedback registrato</span>',
                unsafe_allow_html=True,
            )
        elif current == "down":
            st.markdown(
                '<span class="ws-feedback-down">Grazie, ci aiuti a migliorare</span>',
                unsafe_allow_html=True,
            )


def render_help_panel():
    """Renderizza il pannello di aiuto/FAQ nella sidebar."""
    st.markdown("---")
    with st.expander("Aiuto e FAQ", expanded=False):
        st.markdown("""
        **Come si usa?**
        1. Seleziona un modulo dalla lista
        2. Scegli la modalita' di lavoro
        3. Scrivi la domanda in chat
        4. Controlla fonti e confidenza

        **Come caricare documenti?**
        - Vai su "Admin documenti" nella sidebar
        - Fai login con credenziali admin
        - Carica file PDF, Word o TXT
        - Clicca "Aggiorna" per reindicizzare

        **Catalogo o Genera formula?**
        - Catalogo: usa solo documenti indicizzati
        - Genera formula: produce una bozza da validare

        **Perche' la risposta ha confidenza bassa?**
        Significa che il sistema non ha trovato documenti
        sufficientemente pertinenti alla domanda.

        **I dati sono sicuri?**
        Si', tutto rimane sulla macchina aziendale.
        """)

        if st.button("Ricarica sistema", use_container_width=True,
                     help="Forza il ricaricamento dell'app"):
            st.cache_resource.clear()
            st.session_state.pop("ollama_ok", None)
            st.session_state.pop("ollama_msg", None)
            st.rerun()


def render_conversation_actions():
    """Renderizza azioni rapide sulla conversazione (cancella, scarica)."""
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Nuova chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.chat_engine = None
            st.session_state.response_count = 0
            from config import cfg
            from core.utils import init_session_log
            st.session_state.log_path = init_session_log(cfg.LOGS_DIR)
            st.rerun()
    with col2:
        if st.button("Scarica log", use_container_width=True):
            from datetime import datetime

            from core.utils import build_log_txt
            txt = build_log_txt(st.session_state.messages)
            st.download_button(
                "Salva",
                txt,
                f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                use_container_width=True,
            )


MODE_INFO = {
    "retrieval": {
        "label": "Consulta catalogo",
        "header": "Risposte ancorate ai documenti indicizzati",
        "description": (
            "Usa solo formule e contenuti trovati nel catalogo ufficiale. "
            "Se non trova evidenza sufficiente, lo dichiara apertamente."
        ),
        "badge": "CATALOGO UFFICIALE",
    },
    "generazione": {
        "label": "Genera formula",
        "header": "Bozze AI separate dal catalogo ufficiale",
        "description": (
            "Crea una proposta nuova da validare. Questa modalita' non sostituisce "
            "il catalogo e va usata solo per analisi, test e revisione umana."
        ),
        "badge": "BOZZA DA VALIDARE",
    },
    "analisi": {
        "label": "Analisi Approfondita",
        "header": "Analisi multi-formula con grafo della conoscenza",
        "description": (
            "L'agente analizza relazioni tra formule, campi e logiche "
            "di business usando il grafo della conoscenza. "
            "Non usa il retrieval RAG ma naviga direttamente le dipendenze del catalogo."
        ),
        "badge": "ANALISI FORMULE",
    },
}


def render_mode_explainer(mode_key: str) -> None:
    info = MODE_INFO[mode_key]
    if mode_key == "retrieval":
        st.info(f"{info['header']}. {info['description']}")
    elif mode_key == "generazione":
        st.warning(f"{info['header']}. {info['description']}")
    else:
        st.success(f"{info['header']}. {info['description']}")


def render_workspace_overview(modulo_scelto: str | None, files: list[str], mode_key: str) -> None:
    if not modulo_scelto:
        return
    mode_label = MODE_INFO.get(mode_key, {}).get("label", mode_key)
    doc_count = len(files)
    st.markdown(
        f'<div class="ws-overview-grid">'
        f'<div class="ws-overview-card">'
        f'<div class="ws-overview-label">Modulo</div>'
        f'<div class="ws-overview-value">{html.escape(modulo_scelto)}</div>'
        f'<div class="ws-overview-text">Area di lavoro attiva</div>'
        f'</div>'
        f'<div class="ws-overview-card">'
        f'<div class="ws-overview-label">Documenti</div>'
        f'<div class="ws-overview-value">{doc_count}</div>'
        f'<div class="ws-overview-text">{"File caricati nel modulo" if doc_count else "Nessun file presente"}</div>'
        f'</div>'
        f'<div class="ws-overview-card">'
        f'<div class="ws-overview-label">Modalità</div>'
        f'<div class="ws-overview-value">{html.escape(mode_label)}</div>'
        f'<div class="ws-overview-text">Operatività corrente</div>'
        f'</div>'
        f'<div class="ws-overview-card">'
        f'<div class="ws-overview-label">Stato</div>'
        f'<div class="ws-overview-value">{"⚡ Pronto" if doc_count else "📭 Vuoto"}</div>'
        f'<div class="ws-overview-text">{"Documenti indicizzati" if doc_count else "Carica documenti per iniziare"}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
