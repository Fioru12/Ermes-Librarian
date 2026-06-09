"""
chat_ui.py
Helper UI per rendering storico chat.
"""
import html

import streamlit as st


def render_response_summary(mode: str, source_count: int, has_errors: bool, is_generated: bool) -> None:
    mode_label = "Catalogo" if mode != "generazione" else "Bozza AI"
    status_label = "Da rivedere" if has_errors or is_generated else "Pronta alla verifica"
    next_step = (
        "Controlla sintassi, logica e casi limite prima dei test."
        if is_generated
        else "Confronta fonti e risultato prima di riutilizzare la risposta."
    )
    tone_class = "warn" if has_errors or is_generated else "ok"
    st.markdown(
        f'<div class="ws-response-summary {tone_class}">'
        f'<div class="ws-response-summary-top">'
        f'<span class="ws-response-chip">{html.escape(mode_label)}</span>'
        f'<span class="ws-response-chip">{source_count} fonti</span>'
        f'<span class="ws-response-chip">{html.escape(status_label)}</span>'
        f'</div>'
        f'<div class="ws-response-summary-text">{html.escape(next_step)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_sources_block(sources: list, expanded: bool = True) -> None:
    if not sources:
        return
    with st.expander(f"📚 Fonti ({len(sources)})", expanded=expanded):
        for s in sources:
            source = s.get("source", "—")
            score = s.get("score", 0.0)
            text = s.get("text", "")
            st.markdown(
                f'<div class="ws-source-node">'
                f'<div class="ws-source-header">'
                f'<span class="ws-source-file">📄 {html.escape(source)}</span>'
                f'<span class="ws-source-score">{score:.3f}</span>'
                f'</div>'
                f'<div class="ws-source-text">{html.escape(text)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_prompt_counter(text: str, prompt_max_chars: int) -> None:
    char_pct = len(text) / prompt_max_chars
    cls = "ok" if char_pct < 0.7 else ("warn" if char_pct < 0.9 else "danger")
    st.markdown(
        f'<div class="ws-prompt-counter {cls}">'
        f'{len(text)}/{prompt_max_chars} car.</div>',
        unsafe_allow_html=True,
    )


def render_history_messages(
    messages: list,
    modulo_scelto: str,
    prompt_max_chars: int,
    is_fallback_fn,
    canonical_fallback: str,
    display_formula_fn,
    render_confidence_badge_fn,
    modules: dict | None = None,
) -> None:
    _mod = modules.get(modulo_scelto) if modules else None
    has_formula = _mod is not None and _mod.has_formula_only()
    for msg in messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.markdown(
                    f'<div class="ws-resp-header">'
                    f'<span class="ws-resp-num">Risposta #{msg.get("resp_num", "")}</span>'
                    f'<span class="ws-timer">{msg.get("elapsed", 0):.1f}s'
                    f' · {msg.get("model", "")}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if msg.get("sources"):
                    render_confidence_badge_fn(msg["sources"])
                render_response_summary(
                    msg.get("mode", "retrieval"),
                    len(msg.get("sources", [])),
                    bool(msg.get("errors")),
                    msg.get("mode") == "generazione",
                )

                if has_formula:
                    if is_fallback_fn(msg["content"]):
                        st.info(canonical_fallback)
                    else:
                        display_formula_fn(
                            msg["content"],
                            msg.get("exp", ""),
                            resp_num=msg.get("resp_num", 0),
                            expanded=False,
                        )
                else:
                    st.markdown(
                        '<div style="white-space:pre-wrap;word-break:break-word;">'
                        + html.escape(msg["content"]) + "</div>",
                        unsafe_allow_html=True,
                    )

                for e in msg.get("errors", []):
                    st.markdown(
                        f'<div class="ws-err">{html.escape(str(e))}</div>',
                        unsafe_allow_html=True,
                    )

                if msg.get("sources"):
                    render_sources_block(msg["sources"], expanded=False)
            else:
                st.markdown(html.escape(msg["content"]))
                render_prompt_counter(msg["content"], prompt_max_chars)


def render_confidence_badge(sources: list[dict[str, str | float]]) -> None:
    if not sources:
        return
    from core.rag_engine import score_to_confidence
    top_score = max((s.get("score", 0.0) for s in sources), default=0.0)
    level = score_to_confidence(top_score)
    icons = {"alta": "\u2705", "media": "\u26a0\ufe0f", "bassa": "\U0001f534"}
    labels = {"alta": "Confidenza alta", "media": "Confidenza media", "bassa": "Confidenza bassa"}
    st.markdown(
        f'<span class="ws-confidence-badge {level}">'
        f'{icons[level]} {labels[level]} \u00b7 {top_score:.2f}</span>',
        unsafe_allow_html=True,
    )


def display_formula(code: str, exp: str, resp_num: int, expanded: bool = True) -> None:
    header = ""
    body = ""
    if exp:
        lines = exp.splitlines()
        idx = 0
        for i, line in enumerate(lines):
            if line.strip():
                header = line.strip()
                idx = i
                break
        rest_lines = lines[idx + 1:]
        body = "\n".join(ln for ln in rest_lines if ln.strip()).strip()

    if header and code:
        from ui.theme import render_formula_block
        render_formula_block(header, code)
    elif code:
        st.code(code, language="text")

    if body:
        st.markdown(body)

    if code:
        from ui.theme import render_copy_button
        render_copy_button(code, key=f"copy_{resp_num}")


def render_memory_banner(entry: dict, resp_num: int) -> None:
    ts = entry.get("timestamp", "")[:19].replace("T", " ")
    model = entry.get("model_id", "?")
    score = entry.get("score", 0.0)
    st.markdown(
        f'<div class="ws-memory-banner">'
        f'<span>🧠 Risposta dalla cronologia ({ts} · {model})</span>'
        f'<span class="ws-memory-score">similarità: {score:.2f}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_gen(gen_ph, elapsed_s: float, chars: int,
               tokens: int, preview: str = "", timeout: bool = False,
               model_id: str = "") -> None:
    preview_html = (
        f'{html.escape(preview)}\u25ae'
        if preview else ""
    )
    timeout_html = (
        f'<div class="ws-timeout-warn">\u23f3 Attesa prolungata ({elapsed_s:.0f}s). '
        f'Il modello sta ancora elaborando.</div>'
        if timeout else ""
    )
    gen_ph.markdown(
        f'<div class="ws-generating">'
        f'<div class="ws-generating-header">'
        f'<div class="ws-generating-dot"></div>'
        f'<span class="ws-generating-label">Generazione in corso...</span>'
        f'<span class="ws-generating-model">{model_id}</span>'
        f'</div>'
        f'<div class="ws-progress-bar"><div class="ws-progress-fill"></div></div>'
        f'<div class="ws-generating-stats">'
        f'<span>\u23f1\ufe0f {elapsed_s:.1f}s</span>'
        f'<span>\u270f\ufe0f {chars} car.</span>'
        f'<span>\U0001f522 {tokens} token</span>'
        f'</div>'
        f'<div class="ws-generating-preview">{preview_html}</div>'
        f'{timeout_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
