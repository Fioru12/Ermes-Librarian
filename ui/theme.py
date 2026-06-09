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
    "bg": "#0a0e27",           # Background principale - nero profondo
    "bg2": "#151932",          # Background secondario - blu scuro
    "bg3": "#1f2350",          # Background terziario - blu più acceso
    "sidebar_bg": "#0d1138",   # Sidebar - blu navy scuro
    "border": "#2a2f5a",       # Border sottile
    "border2": "#3a4070",      # Border più visibile
    "text": "#f0f2f7",         # Testo principale - bianco freddo (migliorato da #e8eaf6)
    "text2": "#b0b8d1",        # Testo secondario - grigio chiaro (migliorato da #a0a8c0)
    "text3": "#7a8299",        # Testo terziario - grigio (migliorato da #707890)
    "blue": "#6b8cff",         # Blu primario - più brillante (da #6366f1)
    "blue_bg": "rgba(107,140,255,0.15)",    # Background blu
    "blue_border": "rgba(107,140,255,0.5)", # Border blu - più visibile
    "green": "#10d981",        # Verde - più brillante (da #10b981)
    "green_bg": "rgba(16,217,129,0.15)",
    "green_border": "rgba(16,217,129,0.5)",
    "red": "#ff5454",          # Rosso - più brillante (da #ef4444)
    "red_bg": "rgba(255,84,84,0.15)",
    "red_border": "rgba(255,84,84,0.5)",
    "yellow": "#ffd700",       # Giallo - oro brillante (da #f59e0b)
    "yellow_bg": "rgba(255,215,0,0.15)",
    "yellow_border": "rgba(255,215,0,0.5)",
    "violet": "#a78bfa",       # Viola - più brillante (da #8b5cf6)
    "violet_bg": "rgba(167,139,250,0.15)",
    "violet_border": "rgba(167,139,250,0.5)",
    "shadow": "0 2px 8px rgba(0,0,0,0.4)",     # Shadow più evidente
    "shadow_md": "0 4px 16px rgba(0,0,0,0.5)", # Shadow medio più evidente
    "btn_bg": "#6b8cff",       # Button background - blu
    "btn_border": "#8ba4ff",   # Button border - blu chiaro
    "btn_text": "#ffffff",     # Button text - bianco
    "btn_hover_bg": "#8ba4ff", # Button hover - blu chiaro
    "btn_hover_border": "#afc5ff",
    "btn_hover_text": "#ffffff",
}

_LIGHT = {
    "bg": "#ffffff",
    "bg2": "#f0f4fa",          # header/box — leggero
    "bg3": "#e6ecf5",          # card/messaggi — leggero ma distinguibile
    "sidebar_bg": "#f8fafc",   # sidebar — NON toccato
    "border": "#a0aec0",       # bordi più visibili
    "border2": "#718096",      # bordi importanti più marcati
    "text": "#0f172a",
    "text2": "#334155",        # scuro per contrasto
    "text3": "#1e293b",        # ancora più leggibile
    "blue": "#1d4ed8",         # più marcato
    "blue_bg": "#bfdbfe",      # background blu più visibile
    "blue_border": "#3b82f6",
    "green": "#15803d",        # più marcato
    "green_bg": "#bbf7d0",     # background verde più visibile
    "green_border": "#22c55e",
    "red": "#b91c1c",          # più marcato
    "red_bg": "#fecaca",       # background rosso più visibile
    "red_border": "#ef4444",
    "yellow": "#854d0e",       # più marcato su fondo chiaro
    "yellow_bg": "#fde68a",    # background giallo più visibile
    "yellow_border": "#eab308",
    "violet": "#6d28d9",       # più marcato
    "violet_bg": "#ddd6fe",    # background viola più visibile
    "violet_border": "#8b5cf6",
    "shadow": "0 1px 4px rgba(0,0,0,0.18)",     # ombra più presente
    "shadow_md": "0 4px 14px rgba(0,0,0,0.22)", # ombra più presente
    "btn_bg": "#6b8cff",       # bottone blu (stesso di dark)
    "btn_border": "#3b82f6",   # bordo bottone blu
    "btn_text": "#ffffff",     # testo bianco
    "btn_hover_bg": "#8ba4ff",
    "btn_hover_border": "#2563eb",
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
