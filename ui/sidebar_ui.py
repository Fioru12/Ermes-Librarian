"""
sidebar_ui.py
Helper UI per la sidebar (presentazione e selezione modulo).
"""
import html
import logging
import os
import sys
from functools import lru_cache

import streamlit as st


@lru_cache(maxsize=1)
def _fetch_available_models() -> list[str]:
    try:
        from core.rag_engine import fetch_ollama_models
        return fetch_ollama_models()
    except Exception:
        return []


def render_model_selector() -> str | None:
    models = list(_fetch_available_models())
    if not models:
        st.warning("Nessun modello Ollama disponibile")
        return None
    current = st.session_state.get("model_id", models[0])
    if current not in models:
        current = models[0]
    selected = st.selectbox(
        "🤖 Modello LLM",
        models,
        index=models.index(current),
        help="Modello LLM per generazione risposte",
    )
    return selected


def render_logo() -> None:
    st.markdown(
        '<div class="ws-logo">'
        '<div class="ws-logo-icon">ER</div>'
        '<div>'
        '<div class="ws-logo-title">Ermes</div>'
        '<div class="ws-logo-sub">knowledge hub locale</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_theme_toggle(dark_mode: bool) -> bool:
    btn_label = "🌙 Tema scuro" if dark_mode else "☀️ Tema chiaro"
    clicked = st.button(btn_label, use_container_width=True)
    return clicked


def render_memory_toggle() -> bool:
    active = st.session_state.get("memoria_attiva", True)
    btn_label = "🧠 Memoria: ON" if active else "🧠 Memoria: OFF"
    clicked = st.button(btn_label, use_container_width=True)
    return clicked


def list_modules(base_docs_dir: str) -> list[str]:
    if not os.path.exists(base_docs_dir):
        return []
    return sorted(
        [d for d in os.listdir(base_docs_dir) if os.path.isdir(os.path.join(base_docs_dir, d))]
    )


def render_module_selector(moduli: list[str]) -> str | None:
    if not moduli:
        st.warning("Nessun modulo trovato. Crea una cartella in /documenti.")
        return None
    return st.selectbox("📂 Area di lavoro", moduli)


def render_module_badges(mod_cfg: dict, response_count: int) -> None:
    st.markdown(
        f'<div class="ws-badge-row">'
        f'<span class="ws-badge">T={mod_cfg["temperature"]}</span>'
        f'<span class="ws-badge">ctx={mod_cfg["num_ctx"]}</span>'
        f'<span class="ws-badge">top-k={mod_cfg["top_k"]}</span>'
        f'<span class="ws-badge green">#{response_count} risposte</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_workspace_snapshot(modulo_scelto: str | None, files: list[str], mode_label: str) -> None:
    doc_count = len(files)
    module_label = modulo_scelto or "Nessuno"
    st.markdown(
        f'<div class="ws-sidebar-snapshot">'
        f'<div class="ws-sidebar-snapshot-title">Sessione corrente</div>'
        f'<div class="ws-sidebar-snapshot-grid">'
        f'<div class="ws-sidebar-snapshot-item"><span>Modulo</span><strong>{html.escape(module_label)}</strong></div>'
        f'<div class="ws-sidebar-snapshot-item"><span>Documenti</span><strong>{doc_count}</strong></div>'
        f'<div class="ws-sidebar-snapshot-item"><span>Modalita\'</span><strong>{html.escape(mode_label)}</strong></div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def render_documents_list(modulo_path: str) -> list[str]:
    files = (
        [f for f in os.listdir(modulo_path) if os.path.isfile(os.path.join(modulo_path, f))]
        if os.path.exists(modulo_path)
        else []
    )
    with st.expander(f"📄 Documenti ({len(files)})", expanded=False):
        for fname in files:
            fpath = os.path.join(modulo_path, fname)
            size_kb = round(os.path.getsize(fpath) / 1024, 1)
            icon = "⚠️" if size_kb == 0 else "📄"
            st.markdown(
                f'<div class="ws-doc-item">'
                f'<span class="ws-doc-name">{icon} {html.escape(fname)}</span>'
                f'<span class="ws-doc-size">{size_kb} KB</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    return files


def render_history_warning(message_count: int, max_history: int) -> None:
    if message_count >= max_history - 2 and message_count > 0:
        st.markdown(
            f'<div class="ws-alert yellow">⚠️ Storia quasi piena '
            f'({message_count}/{max_history}). Apri nuova conversazione.</div>',
            unsafe_allow_html=True,
        )


def render_docs_changed_warning(changed: bool) -> None:
    if changed:
        st.markdown(
            '<div class="ws-alert blue">\U0001f504 Documenti aggiornati \u2014 '
            'clicca <b>Aggiorna</b> per reindicizzare.</div>',
            unsafe_allow_html=True,
        )


def render_health(modulo_scelto: str | None, base_chroma_path: str, base_docs_dir: str, model_id: str) -> None:
    def _row(label: str, ok: bool, detail: str = "") -> None:
        icon = "\U0001f7e2" if ok else "\U0001f534"
        det = f" \u2014 {detail}" if detail else ""
        st.markdown(
            f'<div class="ws-health-row">'
            f'<span class="ws-health-icon">{icon}</span>'
            f'<span class="ws-health-label">{label}</span>'
            f'<span class="ws-health-detail">{det}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    _row("Python", True, py_ver)

    ollama_ok = st.session_state.ollama_ok
    ollama_msg = st.session_state.ollama_msg
    _row("Ollama", ollama_ok, "OK" if ollama_ok else ollama_msg)
    _row("Modello", ollama_ok, model_id if ollama_ok else "non verificabile")

    if modulo_scelto:
        import re
        import chromadb
        persist_path = os.path.join(base_chroma_path, modulo_scelto.lower())
        db_ok = False
        db_info = "non inizializzato"
        if os.path.exists(persist_path):
            try:
                db = chromadb.PersistentClient(path=persist_path)
                cname = f"coll_{re.sub(r'[^a-zA-Z0-9]', '', modulo_scelto.lower())}"
                coll = db.get_or_create_collection(cname)
                n = coll.count()
                db_ok = n > 0
                db_info = f"{n} chunk indicizzati" if n > 0 else "vuoto \u2014 reindicizzare"
            except Exception as ex:
                db_info = f"errore: {ex}"
        _row("ChromaDB", db_ok, db_info)

        modulo_path = os.path.join(base_docs_dir, modulo_scelto)
        try:
            n_docs = len([f for f in os.listdir(modulo_path)
                         if os.path.isfile(os.path.join(modulo_path, f))])
            docs_ok = n_docs > 0
            docs_info = f"{n_docs} file presenti"
        except Exception:
            docs_ok = False
            docs_info = "cartella non trovata"
        _row("Documenti", docs_ok, docs_info)
    else:
        _row("ChromaDB", False, "nessun modulo selezionato")
        _row("Documenti", False, "nessun modulo selezionato")


_logger_sidebar = logging.getLogger(__name__)


def execute_db_operation(action_label: str, audit_action: str, modulo_scelto: str,
                         base_chroma_path: str, remove_docs: bool = False):
    from config import cfg
    from core.governance import append_audit, validate_admin_user
    from core.rag_engine import _chroma_lock

    if not validate_admin_user(st.session_state.admin_user):
        st.error("Operazione riservata ad admin.")
        st.stop()

    import shutil

    actor = st.session_state.admin_user["username"]
    _logger_sidebar.info("Admin %s: %s su modulo %s", actor, audit_action, modulo_scelto)
    append_audit(cfg.AUDIT_FILE, f"{audit_action}_start", actor, {"module": modulo_scelto})

    persist_path = os.path.join(base_chroma_path, modulo_scelto.lower())
    try:
        with _chroma_lock:
            if os.path.exists(persist_path):
                shutil.rmtree(persist_path, ignore_errors=False)
        st.cache_resource.clear()
        st.session_state.chat_engine = None
        st.session_state["_docs_cache"] = {}
        if remove_docs:
            st.session_state.pop("ollama_ok", None)
            st.session_state.pop("ollama_msg", None)
        append_audit(cfg.AUDIT_FILE, f"{audit_action}_done", actor, {"module": modulo_scelto})
        st.toast(action_label, icon="\u2705")
        st.rerun()
    except Exception as e:
        append_audit(cfg.AUDIT_FILE, f"{audit_action}_error", actor,
                     {"module": modulo_scelto, "error": str(e)})
        st.error(f"Errore: {e}")


def render_sidebar(base_docs_dir: str, base_chroma_path: str, hash_file: str) -> tuple[str | None, dict, list[str]]:
    """Renderizza l'intera sidebar."""
    from config import cfg
    from core.memory import clear_module_memory
    from core.utils import docs_changed, init_session_log
    from ui.admin_ui import render_admin_auth_section, render_user_management_section
    from ui.welcome_ui import render_help_panel, MODE_INFO
    from ui.monitor_dashboard import render_dashboard_in_sidebar
    from core.governance import validate_admin_user, append_audit
    from core.rag_engine import get_module_config
    
    mod_cfg = {}
    files = []
    
    # Sidebar UI elements
    render_logo()
    if render_theme_toggle(st.session_state.dark_mode):
        st.session_state.dark_mode = not st.session_state.dark_mode
        st.rerun()

    if render_memory_toggle():
        st.session_state.memoria_attiva = not st.session_state.memoria_attiva
        st.rerun()

    st.divider()

    selected_model = render_model_selector()
    if selected_model is not None:
        st.session_state.model_id = selected_model

    moduli = list_modules(base_docs_dir)
    modulo_scelto = render_module_selector(moduli)

    if modulo_scelto:
        mod_cfg = get_module_config(modulo_scelto)
        render_module_badges(mod_cfg, st.session_state.response_count)

    st.divider()

    with st.expander("🔍 Stato sistema", expanded=False):
        render_health(modulo_scelto, base_chroma_path, base_docs_dir, st.session_state.model_id)

    st.divider()

    if modulo_scelto:
        modulo_path = os.path.join(base_docs_dir, modulo_scelto)
        files = render_documents_list(modulo_path)
        
        render_workspace_snapshot(
            modulo_scelto,
            files,
            MODE_INFO[st.session_state.modalita_operativa]["label"],
        )

        n_msg = len(st.session_state.messages)
        max_msg = mod_cfg.get("chat_history", 10)
        render_history_warning(n_msg, max_msg)

        changed_docs = files and docs_changed(
            hash_file, modulo_scelto, modulo_path,
            cache=st.session_state["_docs_cache"],
        )
        render_docs_changed_warning(bool(changed_docs))

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Aggiorna", use_container_width=True):
                clear_module_memory(modulo_scelto)
                execute_db_operation("Database aggiornato!", "reindex_module",
                                     modulo_scelto, base_chroma_path, remove_docs=True)
                st.rerun()
        with col2:
            if st.button("🗑️ Cancella DB", use_container_width=True):
                execute_db_operation("DB cancellato.", "delete_db",
                                     modulo_scelto, base_chroma_path)
                st.rerun()

        if st.button("💬 Nuova conversazione", use_container_width=True):
            st.session_state.messages = []
            st.session_state.chat_engine = None
            st.session_state.response_count = 0
            st.session_state.log_path = init_session_log(cfg.LOGS_DIR)
            st.rerun()
            
    st.divider()

    # Mantenimento e Admin
    with st.expander("🔧 Manutenzione"):
        if st.button("🧹 Rimuovi UUID orfani", use_container_width=True):
            if not validate_admin_user(st.session_state.admin_user):
                st.error("Operazione riservata ad admin.")
                st.stop()
            n = cleanup_orphan_collections(base_chroma_path, base_docs_dir)
            actor = st.session_state.admin_user["username"]
            append_audit(cfg.AUDIT_FILE, "cleanup_orphans", actor, {"removed_count": n})
            st.success(f"Rimossi {n} elementi orfani." if n > 0 else "Nessun elemento orfano.")
            
        if os.path.exists(cfg.LOGS_DIR):
            n_logs = len([f for f in os.listdir(cfg.LOGS_DIR) if f.endswith(".json")])
            st.caption(f"📁 {n_logs} sessioni in /logs")

    with st.expander("🛠️ Admin documenti"):
        if render_admin_auth_section(cfg):
            # ... (logica upload documenti - in app.py originale era qui)
            # Per ora lasciamo vuoto o inseriamo il commento come era.
            pass
        render_user_management_section(cfg)

    # Dashboard KPI
    render_dashboard_in_sidebar(cfg, st.session_state, modulo_scelto)

    # Help panel
    render_help_panel()

    # Manuale
    with st.expander("📖 Manuale utente", expanded=False):
        st.markdown(
            "Guida completa all'uso di Ermes:\n"
            "- Come fare domande\n"
            "- Caricare documenti\n"
            "- Pannello amministrativo\n"
            "- FAQ e risoluzione problemi\n"
            "- Integrazione Teams/Slack\n\n"
            "Il manuale è disponibile nel file `docs/MANUALE_UTENTE.md`."
        )
        try:
            with open("docs/MANUALE_UTENTE.md", encoding="utf-8") as f:
                manual_content = f.read()
            st.download_button(
                "📥 Scarica manuale (.md)",
                manual_content,
                "ERMES_MANUALE_UTENTE.md",
                use_container_width=True,
            )
        except (FileNotFoundError, OSError):
            st.caption("File manuale non trovato")

    if st.session_state.get("messages"):
        from core.utils import build_log_txt
        from datetime import datetime
        st.download_button("📥 Scarica conversazione", build_log_txt(st.session_state.messages), 
                           f"log_{int(datetime.now().timestamp())}.txt", use_container_width=True)

    return modulo_scelto, mod_cfg, files
