"""
app.py
Entry point dell'applicazione Ermes.
Assembla sistema moduli, utils.py, rag_engine.py, theme.py.
"""
import contextlib
import html
import logging
import os
import sys
from datetime import datetime

import streamlit as st

# Configurazione logging centralizzata
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

_logger = logging.getLogger(__name__)

from config import cfg
from core.governance import (
    append_audit,
    ensure_default_admin,
    validate_admin_user,
    validate_password_strength,
)
from core.input_validator import is_safe_module_name
from core.rag_engine import (
    build_chat_engine,
    get_module_config,
    init_llama_settings,
)
from core.rate_limiter import get_rate_limiter
from core.streamlit_rag import check_ollama, get_index
from core.session_init import init_session
from core.utils import (
    build_log_txt,
    cleanup_old_logs,
    cleanup_orphan_collections,
    compute_dir_hash,
    docs_changed,
    init_session_log,
)
from modules import discover_modules
from modules.generic import GenericModule
from modules.winsarp import FALLBACK_PHRASES, WinSarpModule, is_fallback
from ui.admin_ui import render_admin_auth_section, render_user_management_section
from ui.chat_ui import (
    render_history_messages,
)
from ui.sidebar_ui import (
    list_modules,
    render_docs_changed_warning,
    render_documents_list,
    render_history_warning,
    render_logo,
    render_memory_toggle,
    render_model_selector,
    render_module_badges,
    render_module_selector,
    render_theme_toggle,
    render_workspace_snapshot,
)
from ui.theme import apply_theme
from ui.welcome_ui import (
    render_help_panel,
    render_welcome_screen,
)

# ============================================================
# CONFIGURAZIONE PATH — unica fonte di verita': config.py
# ============================================================
BASE_CHROMA_PATH = cfg.CHROMA_DIR
BASE_DOCS_DIR = cfg.DOCS_DIR
HASH_FILE = cfg.HASH_FILE
LOGS_DIR = cfg.LOGS_DIR
PROMPT_MAX_CHARS = cfg.PROMPT_MAX_CHARS
TYPING_TIMEOUT_SEC = cfg.TYPING_TIMEOUT_SEC
TOKEN_TIMEOUT_SEC = cfg.TOKEN_TIMEOUT_SEC

# Frase canonica unica per fallback WinSarp in UI/log/sessione
CANONICAL_FALLBACK = FALLBACK_PHRASES[0]
from ui.welcome_ui import MODE_INFO

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Ermes - Enterprise Knowledge Hub",
    layout="wide",
    page_icon="🏛️",
    initial_sidebar_state="expanded",
)

with contextlib.suppress(Exception):
    init_llama_settings()

# ============================================================
# INIT SESSIONE
# ============================================================
init_session()

# check_ollama eseguito UNA SOLA VOLTA per sessione/rerun (ora gestito da init_session indirettamente)
# ma qui assicuro la pulizia log se necessario
if "log_path" not in st.session_state:
    cleanup_old_logs(cfg.LOGS_DIR, cfg.LOG_RETENTION_DAYS)
    st.session_state.log_path = init_session_log(cfg.LOGS_DIR)

apply_theme(st.session_state.dark_mode)
ensure_default_admin(cfg.USERS_FILE, cfg.ADMIN_USERNAME, cfg.ADMIN_PASSWORD)

# Validazione configurazione admin password in produzione
if cfg.ADMIN_PASSWORD:
    is_strong, msg = validate_password_strength(cfg.ADMIN_PASSWORD)
    if not is_strong:
        st.markdown(
            f'<p style="color: #d9534f; background-color: #f8d7da; padding: 10px; border-radius: 5px; border: 1px solid #f5c6cb;">⚠️ La password admin non soddisfa i requisiti di sicurezza: {msg}. Si raccomanda di usare una password più forte (8+ caratteri, maiuscole, minuscole, numeri, simboli).</p>',
            unsafe_allow_html=True
        )

if not cfg.ENABLE_FORMULA_GENERATION and st.session_state.modalita_operativa == "generazione":
    st.session_state.modalita_operativa = "retrieval"


from core.input_validator import matches_expected_file_signature, sanitize_upload_name
from ui.chat_ui import display_formula, render_confidence_badge
from ui.sidebar_ui import execute_db_operation, render_health
from ui.welcome_ui import render_mode_explainer, render_workspace_overview

# ============================================================
# SIDEBAR
# ============================================================
from ui.sidebar_ui import render_sidebar
with st.sidebar:
    modulo_scelto, mod_cfg, files = render_sidebar(
        BASE_DOCS_DIR, 
        BASE_CHROMA_PATH, 
        HASH_FILE
    )



# ============================================================
# CONTROLLO OLLAMA — legge da session_state, nessuna chiamata di rete
# ============================================================
ollama_ok = st.session_state.ollama_ok
ollama_msg = st.session_state.ollama_msg

if not ollama_ok:
    st.markdown(
        f'<div class="ws-ollama-card">'
        f'<div class="ws-ollama-icon">⚙️</div>'
        f'<div class="ws-ollama-title">Servizio non disponibile</div>'
        f'<div class="ws-ollama-sub">Ermes non riesce a connettersi a Ollama</div>'
        f'<div class="ws-ollama-msg">⚠️ {html.escape(ollama_msg)}</div>'
        f'<div class="ws-ollama-steps">'
        f'<p>1. Apri un terminale (cmd o PowerShell)</p>'
        f'<p>2. Digita: <code>ollama serve</code></p>'
        f'<p>3. Ricarica questa pagina</p>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    st.stop()


# ============================================================
# HEADER PRINCIPALE
# ============================================================
mode_key = st.session_state.modalita_operativa
mode_badge = MODE_INFO[mode_key]["badge"]
if mode_key == "retrieval":
    header_subtitle = "Sistema RAG locale per il modulo WinSarp"
elif mode_key == "generazione":
    header_subtitle = "Area separata per bozze e prototipi di formula"
else:
    header_subtitle = "Analisi multi-formula con grafo della conoscenza"
mod_label = modulo_scelto or "—"
st.markdown(
    f'<div class="ws-header">'
    f'<div class="ws-header-left">'
    f'<div class="ws-header-icon">⚙️</div>'
    f'<div>'
        f'<div class="ws-header-title">Ermes</div>'
    f'<div class="ws-header-sub">{header_subtitle}</div>'
    f'</div></div>'
    f'<div class="ws-header-right">'
    f'<span class="ws-hbadge">📂 {html.escape(mod_label)}</span>'
    f'<span class="ws-hbadge violet">🤖 {st.session_state.model_id}</span>'
    f'<span class="ws-hbadge">{html.escape(mode_badge)}</span>'
    f'<span class="ws-hbadge green">🛡️ FULL LOCAL</span>'
    f'</div></div>'
    f'<div class="ws-local-badge">'
    f'🛡️ Nessun dato esce dalla macchina — documenti e conversazioni restano al sicuro.'
    f'</div>',
    unsafe_allow_html=True,
)


# ============================================================
# SELETTORE MODALITÀ OPERATIVA (solo per moduli che la supportano)
# ============================================================
_mod = st.session_state.modules.get(modulo_scelto)
mod_supports_gen = _mod is not None and _mod.supports_generation()
mod_is_winsarp = modulo_scelto == "WinSarp"
if modulo_scelto and (mod_supports_gen or mod_is_winsarp):
    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col1:
        options = ["📖 Consulta Catalogo (Default)"]
        if mod_supports_gen:
            options.append("✨ Generatore Formule")
        if mod_is_winsarp:
            options.append("🔬 Analisi Approfondita")
        modalita = st.radio(
            "🎯 **Seleziona Modalità:**",
            options,
            horizontal=True,
            label_visibility="visible",
            key="selettore_modalita"
        )
        if modalita == "📖 Consulta Catalogo (Default)":
            st.session_state.modalita_operativa = "retrieval"
        elif modalita == "✨ Generatore Formule":
            st.session_state.modalita_operativa = "generazione"
        else:
            st.session_state.modalita_operativa = "analisi"
    with col2:
        if st.session_state.modalita_operativa == "generazione":
            st.warning("⚠️ MODALITÀ GENERAZIONE - FORMULE NON DOCUMENTATE")
        elif st.session_state.modalita_operativa == "analisi":
            st.info("🔬 Analisi con grafo conoscenza")
    if st.session_state.modalita_operativa == "generazione" and not cfg.ENABLE_FORMULA_GENERATION:
        st.session_state.modalita_operativa = "retrieval"
        st.caption("La generazione formule e' disattivata nella configurazione corrente.")
    render_mode_explainer(st.session_state.modalita_operativa)
    st.markdown("---")

if modulo_scelto:
    render_workspace_overview(
        modulo_scelto,
        files,
        st.session_state.modalita_operativa,
    )


# ============================================================
# WELCOME SCREEN (nessun modulo selezionato)
# ============================================================
if not modulo_scelto:
    if not st.session_state.messages:
        render_welcome_screen(st.session_state.dark_mode)
    else:
        st.markdown(
            '<div class="ws-footer">Ermes · Sistema RAG 100% locale</div>',
            unsafe_allow_html=True,
        )
    st.stop()


# Reset chat engine se cambia modulo o modello
if (st.session_state.current_modulo != modulo_scelto or
        st.session_state.current_model != st.session_state.model_id):
    if (st.session_state.current_modulo
            and st.session_state.current_modulo != modulo_scelto):
        st.toast(
            f"📂 Modulo: {st.session_state.current_modulo} → {modulo_scelto}",
            icon="🔄",
        )
    st.session_state.chat_engine = None
    st.session_state.messages = []
    st.session_state.response_count = 0
    st.session_state.current_modulo = modulo_scelto
    st.session_state.current_model = st.session_state.model_id


index = st.session_state.get("_cached_index", None)
modulo_path = os.path.join(BASE_DOCS_DIR, modulo_scelto)

# Calcola hash documenti per rilevare cambiamenti senza ri-indicizzare a ogni rerun.
# Incluso in _index_cache_key: se i documenti cambiano, l'hash cambia → re-indicizzazione.
doc_hash = compute_dir_hash(modulo_path) if os.path.exists(modulo_path) else ""
index_cache_key = f"{modulo_scelto}_{st.session_state.model_id}_{doc_hash}"
if index is None or st.session_state.get("_index_cache_key") != index_cache_key:
    cache_buster = index_cache_key
    index = get_index(
        modulo_scelto, st.session_state.model_id,
        BASE_DOCS_DIR, BASE_CHROMA_PATH, HASH_FILE,
        cache_buster=cache_buster,
    )
    st.session_state["_cached_index"] = index
    st.session_state["_index_cache_key"] = index_cache_key

if index and st.session_state.chat_engine is None:
    _mod = st.session_state.modules.get(modulo_scelto)
    use_gen_prompt = (
        cfg.ENABLE_FORMULA_GENERATION
        and st.session_state.modalita_operativa == "generazione"
        and _mod is not None
        and _mod.supports_generation()
    )
    st.session_state.chat_engine = build_chat_engine(
        modulo_scelto,
        st.session_state.model_id,
        index,
        use_generation_prompt=use_gen_prompt,
        modules=st.session_state.get("modules"),
    )


# ============================================================
# SUGGESTION BUTTONS
# ============================================================
if not st.session_state.messages:
    _mod = st.session_state.modules.get(modulo_scelto)
    if st.session_state.modalita_operativa == "generazione":
        suggestions = _mod.get_generation_suggestions() if _mod else []
        label_suggerimenti = "💡 Esempi per bozze AI da validare"
    elif st.session_state.modalita_operativa == "analisi":
        suggestions = [
            "Quali formule chiama la 120?",
            "Chi chiama la formula 200?",
            "Quali formule usano il campo 561?",
            "Spiega la catena formula 100",
            "Differenza tra formula 130 e 140",
        ]
        label_suggerimenti = "🔬 Analisi di esempio"
    else:
        suggestions = _mod.get_retrieval_suggestions() if _mod else []
        label_suggerimenti = "💡 Domande di esempio"

    if suggestions:
        st.markdown(
            f'<div class="ws-suggestions-label">{label_suggerimenti}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, sug in enumerate(suggestions):
            with cols[i % 2]:
                if st.button(sug, key=f"sug_{i}", use_container_width=True):
                    st.session_state["_pending_prompt"] = sug
                    st.rerun()


# ============================================================
# STORICO MESSAGGI
# ============================================================
render_history_messages(
    st.session_state.messages,
    modulo_scelto,
    PROMPT_MAX_CHARS,
    is_fallback,
    CANONICAL_FALLBACK,
    display_formula,
    render_confidence_badge,
    modules=st.session_state.modules,
)


# ============================================================
# INPUT CHAT
# ============================================================
if st.session_state.modalita_operativa == "generazione":
    placeholder = (
        "Descrivi la formula da proporre... "
        "(bozza AI separata dal catalogo ufficiale)"
    )
elif st.session_state.modalita_operativa == "analisi":
    placeholder = (
        "Chiedi un'analisi tra formule (es. 'Quali formule usano il campo 561?')..."
    )
else:
    _mod = st.session_state.modules.get(modulo_scelto)
    placeholder = _mod.get_chat_placeholder("retrieval") if _mod else "Fai una domanda sui documenti..."

pending = st.session_state.pop("_pending_prompt", None)
prompt = st.chat_input(placeholder) or pending

if prompt:
    from ui.chat_handler import stream_response, submit_user_message

    submit_user_message(prompt, modulo_scelto, PROMPT_MAX_CHARS, st.session_state.log_path)

    with st.chat_message("assistant"):
        stream_response(
            prompt=prompt,
            modulo_scelto=modulo_scelto,
            index=index,
            model_id=st.session_state.model_id,
            modalita=st.session_state.modalita_operativa,
            timeout_sec=TOKEN_TIMEOUT_SEC,
            typing_timeout_sec=TYPING_TIMEOUT_SEC,
            log_path=st.session_state.log_path,
        )


