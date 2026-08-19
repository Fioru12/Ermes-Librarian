"""
theme.py
Gestione tema dark/light tramite CSS template iniettato da Python.
Il CSS vive in ui/theme.css — le variabili colore sono sostituite a runtime.
Zero JavaScript (eccetto render_copy_button per gli appunti).
Zero dipendenza dal config.toml per il tema.
Il toml resta neutro — questo file gestisce tutto.
"""

import html as _html
import re
import string
from pathlib import Path

import streamlit as st

# ============================================================
# PALETTE COLORI
# ============================================================

_DARK = {
    "bg": "#090a0f",           # Background principale - nero/ardesia molto profondo
    "bg2": "#131520",          # Background secondario - card e contenitori
    "bg3": "#1e2235",          # Background terziario - hover e elementi attivi
    "sidebar_bg": "#0d0e15",   # Sidebar - ardesia scurissimo
    "border": "rgba(255, 255, 255, 0.07)",  # Border semitrasparente molto sottile
    "border2": "rgba(255, 255, 255, 0.15)", # Border più visibile
    "text": "#f1f5f9",         # Testo principale - grigio freddo molto chiaro
    "text2": "#cbd5e1",        # Testo secondario - grigio intermedio
    "text3": "#64748b",        # Testo terziario - grigio spento / disattivato
    "blue": "#6366f1",         # Blu primario - indaco moderno
    "blue_bg": "rgba(99, 102, 241, 0.1)",
    "blue_border": "rgba(99, 102, 241, 0.35)",
    "green": "#10b981",        # Verde - smeraldo
    "green_bg": "rgba(16, 185, 129, 0.1)",
    "green_border": "rgba(16, 185, 129, 0.35)",
    "red": "#ef4444",          # Rosso - corallo
    "red_bg": "rgba(239, 68, 68, 0.1)",
    "red_border": "rgba(239, 68, 68, 0.35)",
    "yellow": "#f59e0b",       # Giallo - ambra
    "yellow_bg": "rgba(245, 158, 11, 0.1)",
    "yellow_border": "rgba(245, 158, 11, 0.35)",
    "violet": "#a855f7",       # Viola - purple
    "violet_bg": "rgba(168, 85, 247, 0.1)",
    "violet_border": "rgba(168, 85, 247, 0.35)",
    "shadow": "0 4px 12px rgba(0,0,0,0.5)",
    "shadow_md": "0 8px 24px rgba(0,0,0,0.6)",
    "btn_bg": "#6366f1",
    "btn_border": "#4f46e5",
    "btn_text": "#ffffff",
    "btn_hover_bg": "#818cf8",
    "btn_hover_border": "#6366f1",
    "btn_hover_text": "#ffffff",
}

_LIGHT = {
    "bg": "#f8fafc",           # Background principale - grigio-azzurro chiarissimo
    "bg2": "#ffffff",          # Background secondario - card bianche pulite
    "bg3": "#f1f5f9",          # Background terziario - input e grigi alternativi
    "sidebar_bg": "#f1f5f9",   # Sidebar - grigio morbido
    "border": "#e2e8f0",       # Border sottilissimo per separare
    "border2": "#cbd5e1",      # Border intermedio
    "text": "#0f172a",         # Testo principale - ardesia scuro
    "text2": "#475569",        # Testo secondario - grigio scuro
    "text3": "#94a3b8",        # Testo terziario - grigio chiaro
    "blue": "#4f46e5",         # Blu primario - indaco forte
    "blue_bg": "rgba(79, 70, 229, 0.07)",
    "blue_border": "rgba(79, 70, 229, 0.25)",
    "green": "#059669",        # Verde forte su sfondo chiaro
    "green_bg": "rgba(5, 150, 105, 0.07)",
    "green_border": "rgba(5, 150, 105, 0.25)",
    "red": "#dc2626",          # Rosso forte
    "red_bg": "rgba(220, 38, 38, 0.07)",
    "red_border": "rgba(220, 38, 38, 0.25)",
    "yellow": "#d97706",       # Giallo ambra scuro
    "yellow_bg": "rgba(217, 119, 6, 0.07)",
    "yellow_border": "rgba(217, 119, 6, 0.25)",
    "violet": "#7c3aed",       # Viola forte
    "violet_bg": "rgba(124, 58, 237, 0.07)",
    "violet_border": "rgba(124, 58, 237, 0.25)",
    "shadow": "0 2px 8px rgba(0,0,0,0.04)",
    "shadow_md": "0 6px 18px rgba(0,0,0,0.07)",
    "btn_bg": "#4f46e5",
    "btn_border": "#4338ca",
    "btn_text": "#ffffff",
    "btn_hover_bg": "#6366f1",
    "btn_hover_border": "#4f46e5",
    "btn_hover_text": "#ffffff",
}


# ============================================================
# HELPERS
# ============================================================

def _safe_dom_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


# ============================================================
# FUNZIONE PRINCIPALE
# ============================================================

_CSS_FILES = [
    Path(__file__).parent / "theme_base.css",
    Path(__file__).parent / "theme_layout.css",
    Path(__file__).parent / "theme_components.css",
]
_CSS_TEMPLATE: str | None = None


def _load_css() -> str:
    global _CSS_TEMPLATE
    if _CSS_TEMPLATE is None:
        parts = [f.read_text(encoding="utf-8").rstrip("\n\r") for f in _CSS_FILES]
        _CSS_TEMPLATE = "\n".join(parts)
    return _CSS_TEMPLATE


def apply_theme(dark: bool = True):
    """
    Inietta il blocco CSS completo dell'app in base al tema scelto.
    Il CSS vive in ui/theme.css — 32 variabili colore sostituite a runtime.
    Chiamare una volta per rerun, prima di qualsiasi st.markdown().
    """
    global _CSS_TEMPLATE
    _CSS_TEMPLATE = None  # Forza ricaricamento template per includere le nuove righe CSS
    c = _DARK if dark else _LIGHT
    template = _load_css()
    css = string.Template(template).safe_substitute(c)
    # Aggiungo un timestamp per forzare il ricaricamento (Cache Busting)
    from datetime import datetime
    st.markdown(f"<style>{css}</style><!-- v={datetime.now().strftime('%H%M%S')} -->", unsafe_allow_html=True)


# ============================================================
# COPY BUTTON (JS)
# ============================================================
_COPY_JS = """
<script>
function copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        btn.innerText = '✅ Copiato';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerText = '📋 Copia';
            btn.classList.remove('copied');
        }, 2000);
    }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        btn.innerText = '✅ Copiato';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.innerText = '📋 Copia';
            btn.classList.remove('copied');
        }, 2000);
    });
}
</script>
"""


def render_copy_button(code: str, key: str = "copy_btn"):
    """Renderizza un pulsante copia formula."""
    safe_code = _html.escape(code, quote=True)
    html_content = f"""
    <button class="ws-copy-btn" onclick="copyToClipboard('{safe_code}', this)" id="{key}">
        📋 Copia
    </button>
    {_COPY_JS}
    """
    st.markdown(html_content, unsafe_allow_html=True)


def render_formula_block(header: str, code: str):
    """
    Renderizza un blocco formula formattato: header + codice in box.
    """
    safe_header = _html.escape(header)
    safe_code = _html.escape(code)
    st.markdown(
        f'<div class="ws-formula-block">'
        f'<div class="ws-formula-header">'
        f'<span class="ws-formula-name">📐 {safe_header}</span>'
        f'</div>'
        f'<div class="ws-formula-code"><code>{safe_code}</code></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_generation_warning(message: str = "⚠️ <b>FORMULA GENERATA - NON DOCUMENTATA NEL CATALOGO</b><br>Questa formula è stata creata dall'IA e non è presente nel catalogo ufficiale WinSarp. Deve essere validata e testata prima dell'uso in produzione."):
    """
    Renderizza un warning per formule generate con stile centralizzato.

    Args:
        message: Messaggio di warning (default: messaggio standard per formule generate)
    """
    st.markdown(
        f'<div class="ws-warn" style="background-color: rgba(255, 215, 0, 0.2); border: 2px solid rgba(255, 215, 0, 0.6); padding: 15px; border-radius: 8px; margin: 10px 0; color: #ffd700;">'
        f'{message}</div>',
        unsafe_allow_html=True,
    )
