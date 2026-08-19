"""
admin_ui.py
UI helper per autenticazione admin e gestione utenti.
"""
import time

import streamlit as st

from core.governance import append_audit, authenticate_user, create_or_update_user, list_users
from core.input_validator import validate_user_input


def _init_admin_lockout():
    """Inizializza il dizionario lockout se non esiste."""
    if "_admin_lockout" not in st.session_state:
        st.session_state._admin_lockout = {}  # {username: (timestamp, count)}


def _check_admin_lockout(username: str, max_attempts: int = 5, lockout_mins: int = 15) -> bool:
    """
    Verifica se l'utente è in lockout dopo fallimenti ripetuti.
    Ritorna True se il login è permesso, False se lockato.
    """
    _init_admin_lockout()

    now = time.time()
    lockout_seconds = lockout_mins * 60

    if username in st.session_state._admin_lockout:
        ts, count = st.session_state._admin_lockout[username]
        if now - ts < lockout_seconds:
            # Ancora in lockout
            if count >= max_attempts:
                remaining = int(lockout_seconds - (now - ts))
                st.error(f"🔒 Account bloccato. Riprova tra {remaining} secondi.")
                return False
            # Non lockato ancora, ma incrementa contatore
            st.session_state._admin_lockout[username] = (ts, count + 1)
        else:
            # Lockout scaduto, reset
            st.session_state._admin_lockout[username] = (now, 0)
    else:
        # Primo tentativo
        st.session_state._admin_lockout[username] = (now, 0)

    return True


def _reset_admin_lockout(username: str):
    """Resetta il lockout quando il login ha successo."""
    if "_admin_lockout" in st.session_state and username in st.session_state._admin_lockout:
        st.session_state._admin_lockout.pop(username, None)


def render_admin_auth_section(cfg) -> bool:
    """
    Rende la sezione login/logout admin.
    Ritorna True se il pannello admin e' sbloccato.
    """
    if not cfg.ADMIN_PASSWORD:
        st.error(
            "🔒 Pannello admin protetto: imposta ERMES_ADMIN_PASSWORD "
            "come variabile d'ambiente o nel file .env per abilitare l'accesso."
        )
        return False

    if st.session_state.admin_user is None:
        st.caption("Accesso richiesto (ruolo admin).")
        adm_user = st.text_input(
            "Utente admin",
            value=cfg.ADMIN_USERNAME,
            key="adm_user",
            label_visibility="visible",
            autocomplete="username"
        )
        adm_pwd = st.text_input(
            "Password admin",
            type="password",
            key="adm_pwd",
            label_visibility="visible",
            autocomplete="current-password"
        )
        if st.button("Login admin", use_container_width=True):
            # SECURITY: Verifica lockout prima di tentare autenticazione
            if not _check_admin_lockout(adm_user.strip()):
                return False

            user = authenticate_user(cfg.USERS_FILE, adm_user.strip(), adm_pwd)
            if user and user.get("role") == "admin":
                st.session_state.admin_user = user
                st.session_state.admin_unlocked = True
                _reset_admin_lockout(adm_user.strip())
                append_audit(cfg.AUDIT_FILE, "admin_login_ok", user["username"])
                st.success(f"Login OK: {user['username']}")
            else:
                append_audit(cfg.AUDIT_FILE, "admin_login_fail", adm_user.strip() or "unknown")
                st.error("Credenziali non valide o ruolo non autorizzato.")
        return bool(st.session_state.admin_unlocked)

    current_admin = st.session_state.admin_user["username"]
    st.success(f"Connesso come admin: {current_admin}")
    def _logout_callback():
        append_audit(cfg.AUDIT_FILE, "admin_logout", current_admin)
        st.session_state.admin_user = None
        st.session_state.admin_unlocked = False

    st.button("Logout admin", use_container_width=True, on_click=_logout_callback)
    return True


def render_user_management_section(cfg) -> None:
    """Rende la sezione creazione/aggiornamento utenti."""
    st.markdown("---")
    st.caption("Gestione utenti (solo admin)")
    with st.expander("👤 Utenti", expanded=False):
        users = list_users(cfg.USERS_FILE)
        if users:
            for u in users:
                st.write(f"- {u['username']} · ruolo={u['role']} · attivo={u['active']}")
        else:
            st.write("Nessun utente configurato.")

        new_user = st.text_input("Username", key="new_user", label_visibility="visible", autocomplete="username")
        new_role = st.selectbox("Ruolo", ["viewer", "admin"], key="new_role", label_visibility="visible")
        new_pwd = st.text_input("Password", type="password", key="new_pwd", label_visibility="visible", autocomplete="new-password")
        is_active = st.checkbox("Utente attivo", value=True, key="new_active", label_visibility="visible")
        if st.button("Crea/Aggiorna utente", use_container_width=True):
            # Validazione input
            valid, reason = validate_user_input(new_user.strip(), new_pwd, new_role)
            if not valid:
                st.error(f"❌ Input non valido: {reason}")
                return

            create_or_update_user(
                cfg.USERS_FILE,
                username=new_user.strip(),
                role=new_role,
                password=new_pwd,
                active=is_active,
            )
            actor = (st.session_state.admin_user or {}).get("username", "anonymous")
            append_audit(
                cfg.AUDIT_FILE,
                "user_upsert",
                actor,
                {"username": new_user.strip(), "role": new_role, "active": is_active},
            )
            st.success(f"Utente {new_user.strip()} aggiornato.")
