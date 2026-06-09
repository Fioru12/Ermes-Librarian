import streamlit as st
from core.utils import init_session_log
from config import cfg
from modules import discover_modules
from modules.generic import GenericModule
from modules.winsarp import WinSarpModule
from core.streamlit_rag import check_ollama

def init_session():
    """Inizializza lo stato della sessione di Ermes."""
    if "dark_mode" not in st.session_state:
        st.session_state.dark_mode = True
    if "log_path" not in st.session_state:
        st.session_state.log_path = init_session_log(cfg.LOGS_DIR)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chat_engine" not in st.session_state:
        st.session_state.chat_engine = None
    if "current_modulo" not in st.session_state:
        st.session_state.current_modulo = None
    if "current_model" not in st.session_state:
        st.session_state.current_model = None
    if "model_id" not in st.session_state:
        st.session_state.model_id = cfg.DEFAULT_MODEL_ID
    if "response_count" not in st.session_state:
        st.session_state.response_count = 0
    if "_docs_cache" not in st.session_state:
        st.session_state["_docs_cache"] = {}
    if "_cached_index" not in st.session_state:
        st.session_state["_cached_index"] = None
    if "_index_cache_key" not in st.session_state:
        st.session_state["_index_cache_key"] = ""
    if "admin_unlocked" not in st.session_state:
        st.session_state.admin_unlocked = False
    if "admin_user" not in st.session_state:
        st.session_state.admin_user = None
    
    # Sistema moduli Ermes
    if "modules" not in st.session_state:
        discovered = discover_modules()
        if "WinSarp" not in discovered:
            discovered["WinSarp"] = WinSarpModule()
        if "Generic" not in discovered:
            discovered["Generic"] = GenericModule()
        st.session_state.modules = discovered
        
    # Modalità operativa: retrieval (default) o generazione
    if "modalita_operativa" not in st.session_state:
        st.session_state.modalita_operativa = "retrieval"
    if "memoria_attiva" not in st.session_state:
        st.session_state.memoria_attiva = True

    # Check Ollama
    if "ollama_ok" not in st.session_state:
        _ok, _msg = check_ollama(st.session_state.model_id)
        st.session_state.ollama_ok = _ok
        st.session_state.ollama_msg = _msg
