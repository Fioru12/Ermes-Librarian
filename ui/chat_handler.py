"""
chat_handler.py
Gestione del flusso chat: validazione prompt, rate limiting, streaming response.
Riduce il carico di app.py spostando qui la logica di interazione.
"""
import html
import logging
import queue
import threading
from datetime import datetime

import streamlit as st

_logger = logging.getLogger(__name__)


def submit_user_message(prompt: str, modulo_scelto: str, prompt_max_chars: int, log_path: str):
    if len(prompt) > prompt_max_chars:
        st.warning(
            f"⚠️ Prompt troppo lungo ({len(prompt)} car., max {prompt_max_chars}). "
            "Riducilo per evitare overflow del contesto."
        )
        st.stop()

    limiter = _get_limiter()
    session_id = st.session_state.get("_session_id", "anonymous")
    if "_session_id" not in st.session_state:
        import secrets
        st.session_state["_session_id"] = secrets.token_hex(16)
        session_id = st.session_state["_session_id"]

    allowed, reason = limiter.check_request_rate(session_id)
    if not allowed:
        st.warning(f"⚠️ {reason}. Attendi un momento prima di riprovare.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    _logger.info("User query in %s mode: %s (length: %d)",
                 st.session_state.modalita_operativa, modulo_scelto, len(prompt))
    from core.utils import append_to_log
    append_to_log(log_path, modulo_scelto, "user", prompt)

    with st.chat_message("user"):
        st.markdown(html.escape(prompt))
        from ui.chat_ui import render_prompt_counter
        render_prompt_counter(prompt, prompt_max_chars)


def _get_limiter():
    from core.rate_limiter import get_rate_limiter
    return get_rate_limiter()


def stream_response(
    prompt: str,
    modulo_scelto: str,
    index,
    model_id: str,
    modalita: str,
    timeout_sec: int,
    typing_timeout_sec: int,
    log_path: str,
):
    """Gestisce il flusso streaming + rendering della risposta."""
    
    # --- INTEGRAZIONE BUSINESS ASSISTANT ---
    if modalita == "generazione":
        from core.business_assistant import BusinessAssistant
        assistant = BusinessAssistant()
        clarification = assistant.check_needs_clarification(prompt)
        if clarification:
            st.markdown(f"🤖 **Assistant:** {clarification}")
            st.session_state.messages.append({"role": "assistant", "content": clarification})
            return

    if modalita == "analisi":
        return _stream_analisi_response(prompt, modulo_scelto, model_id, log_path)

    if not st.session_state.chat_engine:
        st.markdown(
            f'<div class="ws-warn">⚠️ Nessun documento trovato per '
            f'<b>{html.escape(modulo_scelto)}</b>.<br>'
            f'Aggiungi file in <code>/documenti/{html.escape(modulo_scelto)}/</code> '
            f'e clicca <b>Aggiorna</b>.</div>',
            unsafe_allow_html=True,
        )
        return

    # --- MEMORIA: check risposta cache ---
    if st.session_state.get("memoria_attiva", True):
        from core.memory import recall as mem_recall
        mem_entry = mem_recall(prompt, modulo_scelto)
        if mem_entry and mem_entry.get("answer"):
            st.session_state.response_count += 1
            resp_num = st.session_state.response_count
            from ui.chat_ui import render_memory_banner
            render_memory_banner(mem_entry, resp_num)
            from modules.winsarp import parse_response
            from ui.chat_ui import render_confidence_badge, render_response_summary, render_sources_block
            from ui.welcome_ui import render_feedback_buttons

            sources = mem_entry.get("sources", [])
            elapsed = 0.0
            full_response = mem_entry["answer"]

            parsed = parse_response(full_response, modulo_scelto)
            render_response_summary(modalita, len(sources), bool(parsed.get("errors")),
                                    modalita == "generazione")

            if sources:
                render_confidence_badge(sources)

            _mod = st.session_state.modules.get(modulo_scelto)
            has_formula = _mod is not None and _mod.has_formula_only()
            if has_formula:
                if parsed["has_split"] and parsed["code"]:
                    from ui.chat_ui import display_formula
                    display_formula(parsed["code"], parsed.get("exp", ""), resp_num=resp_num, expanded=True)
                    for e in parsed["errors"]:
                        st.markdown(f'<div class="ws-err">⚠️ {html.escape(str(e))}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div style="white-space:pre-wrap;word-break:break-word;">' +
                        html.escape(full_response) + "</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div style="white-space:pre-wrap;word-break:break-word;">' +
                    html.escape(full_response) + "</div>",
                    unsafe_allow_html=True,
                )

            if sources:
                render_sources_block(sources, expanded=False)

            render_feedback_buttons(resp_num)

            content_to_save = parsed["code"] if parsed["has_split"] else full_response
            st.session_state.messages.append({
                "role": "assistant", "content": content_to_save,
                "exp": parsed.get("exp", ""), "errors": parsed.get("errors", []),
                "sources": sources, "elapsed": elapsed, "resp_num": resp_num,
                "model": mem_entry.get("model_id", model_id), "mode": modalita,
            })
            from core.utils import append_to_log
            append_to_log(log_path, modulo_scelto, "assistant", content_to_save,
                          parsed.get("errors", []), elapsed)
            return

    st.session_state.response_count += 1
    resp_num = st.session_state.response_count
    gen_ph = st.empty()

    from ui.chat_ui import render_gen
    render_gen(gen_ph, 0, 0, 0, model_id=model_id)

    full_response, elapsed, streaming_resp = _do_stream(
        prompt, gen_ph, model_id, timeout_sec, typing_timeout_sec,
    )

    from core.rag_engine import get_source_nodes, is_low_confidence
    from modules.winsarp import FALLBACK_PHRASES, is_fallback

    sources = get_source_nodes(modulo_scelto, model_id, index, prompt) if index is not None else []

    low_conf = is_low_confidence(sources)
    fallback = is_fallback(full_response)
    fallback_text = FALLBACK_PHRASES[0]

    _mod = st.session_state.modules.get(modulo_scelto)
    is_winsarp = _mod is not None and _mod.has_formula_only()

    if modalita == "generazione":
        _render_success_response(full_response, sources, elapsed, resp_num,
                                 modalita, modulo_scelto, log_path, model_id,
                                 original_prompt=prompt)
    elif is_winsarp and (fallback or low_conf):
        _render_fallback_response(full_response, fallback_text,
                                  low_conf, fallback, sources, elapsed, resp_num,
                                  modalita, log_path, modulo_scelto)
    else:
        _render_success_response(full_response, sources, elapsed, resp_num,
                                 modalita, modulo_scelto, log_path, model_id,
                                 original_prompt=prompt)

    if st.session_state.get("memoria_attiva", True) and not fallback:
        from core.memory import remember as mem_remember
        mem_remember(prompt, full_response, modulo_scelto, model_id, sources)


def _stream_analisi_response(prompt: str, modulo_scelto: str, model_id: str, log_path: str):
    """Esegue analisi approfondita via AgentRunner."""
    st.session_state.response_count += 1
    resp_num = st.session_state.response_count
    from core.agent_runner import AgentRunner
    from core.knowledge_graph import KnowledgeGraph
    from ui.welcome_ui import render_feedback_buttons

    kg = KnowledgeGraph()
    runner = AgentRunner(kg)
    result = runner.analyze(prompt, model_id)

    stats = runner.kg.stats()
    st.markdown(
        f'<div class="ws-resp-header">'
        f'<span class="ws-resp-num">Analisi #{resp_num}</span>'
        f'<span class="ws-timer">⏱️ {result["time"]}s · {model_id}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"📊 Grafo: {stats['totale_formule']} formule, "
               f"{stats.get('archi', 0)} relazioni")

    if result.get("steps"):
        with st.expander("🔧 Passi eseguiti", expanded=False):
            for s in result["steps"]:
                st.markdown(f"**{s['tool']}**({s['input']})")

    response_text = result.get("response", "Nessuna risposta generata.")
    st.markdown(
        '<div style="white-space:pre-wrap;word-break:break-word;">' +
        html.escape(response_text) + "</div>",
        unsafe_allow_html=True,
    )

    render_feedback_buttons(resp_num)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response_text,
        "exp": "",
        "errors": [],
        "sources": [],
        "elapsed": result["time"],
        "resp_num": resp_num,
        "model": model_id,
        "mode": "analisi",
    })
    from core.utils import append_to_log
    append_to_log(log_path, modulo_scelto, "assistant", response_text, [], result["time"])


def _do_stream(prompt, gen_ph, model_id, timeout_sec, typing_timeout_sec):
    full_response = ""
    elapsed = 0.0
    token_count = 0
    timeout_shown = False
    streaming_resp = None
    t_start = datetime.now()
    producer_thread = None
    stop_producer_event = None

    try:
        streaming_resp = st.session_state.chat_engine.stream_chat(prompt)
        token_queue = queue.Queue()
        stop_producer_event = threading.Event()

        def _producer(resp, stop_event):
            try:
                for tok in resp.response_gen:
                    if stop_event.is_set():
                        break
                    token_queue.put(tok)
            except Exception as ex:
                token_queue.put(ex)
            finally:
                token_queue.put(None)

        producer_thread = threading.Thread(
            target=_producer,
            args=(streaming_resp, stop_producer_event),
            daemon=True
        )
        producer_thread.start()

        while True:
            try:
                item = token_queue.get(timeout=timeout_sec)
            except queue.Empty:
                stop_producer_event.set()
                gen_ph.empty()
                st.markdown(
                    f'<div class="ws-err">❌ Il modello non risponde da '
                    f'{timeout_sec}s. Riprova o riavvia Ollama '
                    f'(<code>ollama serve</code>).</div>',
                    unsafe_allow_html=True,
                )
                st.stop()

            if item is None:
                break
            if isinstance(item, Exception):
                raise item

            full_response += item
            token_count += 1
            elapsed = (datetime.now() - t_start).total_seconds()

            if elapsed > typing_timeout_sec and not timeout_shown:
                timeout_shown = True

            if token_count % 3 == 0:
                preview = html.escape(full_response[-120:])
                from ui.chat_ui import render_gen
                render_gen(gen_ph, elapsed, len(full_response), token_count,
                           preview, timeout_shown, model_id=model_id)

        elapsed = (datetime.now() - t_start).total_seconds()
        gen_ph.empty()

    except Exception as e:
        if stop_producer_event:
            stop_producer_event.set()
        gen_ph.empty()
        err = str(e)
        if "connection" in err.lower() or "refused" in err.lower():
            st.markdown(
                '<div class="ws-err">❌ Ollama non raggiungibile. '
                'Verifica: <code>ollama serve</code></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="ws-err">❌ Errore: {html.escape(err)}</div>',
                unsafe_allow_html=True,
            )
        st.stop()

    return full_response, elapsed, streaming_resp


def _render_fallback_response(full_response, fallback_text, low_conf, fallback,
                               sources, elapsed, resp_num, modalita, log_path, modulo_scelto):
    st.info("📭 " + fallback_text)
    if low_conf and not fallback:
        st.caption(
            "Confidenza bassa: i documenti non contengono informazioni sufficienti. "
            "Prova a riformulare o verifica i documenti indicizzati."
        )
    else:
        st.caption(
            "Nessuna formula nel catalogo corrisponde alla richiesta. "
            "Prova a riformulare o verifica i documenti indicizzati."
        )
    st.session_state.messages.append({
        "role": "assistant", "content": fallback_text,
        "exp": "", "errors": [], "sources": sources,
        "elapsed": elapsed, "resp_num": resp_num,
        "model": st.session_state.model_id, "mode": modalita,
    })
    _logger.info("Fallback response in %s mode: %s (elapsed: %.2fs)",
                 modalita, modulo_scelto, elapsed)
    from core.utils import append_to_log
    append_to_log(log_path, modulo_scelto, "assistant", fallback_text, [], elapsed)


def _retry_fix_formula(original_prompt, code, errors, model_id):
    """Richiama il LLM per correggere errori di validazione. Max 2 tentativi."""
    import httpx

    from core.rag_engine import _ollama_url
    from modules.winsarp import parse_response
    url = _ollama_url() + "/api/generate"
    fix_prompt = (
        "L'utente ha chiesto: \"{prompt}\"\n\n"
        "Hai generato questo codice WinSarp:\n```\n{code}\n```\n\n"
        "ERRORI DI VALIDAZIONE:\n{errors}\n\n"
        "Correggi il codice per risolvere TUTTI gli errori sopra.\n"
        "Ritorna SOLO il codice corretto, senza spiegazioni, dentro un blocco ```."
    )
    for attempt in range(2):
        err_text = "\n".join(f"- {e}" for e in errors)
        prompt = fix_prompt.format(prompt=original_prompt, code=code, errors=err_text)
        payload = {
            "model": model_id,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 1024},
        }
        try:
            resp = httpx.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            new_answer = resp.json().get("response", "")
            if not new_answer:
                break
            parsed = parse_response(new_answer, "WinSarp")
            if parsed.get("code") and not parsed.get("errors"):
                return new_answer, parsed
            code = parsed.get("code", code)
            errors = parsed.get("errors", errors)
        except Exception:
            break
    return None, None


def _render_success_response(full_response, sources, elapsed, resp_num,
                              modalita, modulo_scelto, log_path, model_id,
                              original_prompt=None):
    from core.utils import append_to_log
    from modules.winsarp import parse_response
    from ui.chat_ui import (
        render_confidence_badge,
        render_response_summary,
        render_sources_block,
    )
    from ui.theme import render_generation_warning
    from ui.welcome_ui import render_feedback_buttons

    # Parse + auto-retry BEFORE header (per poter mostrare elapsed_str corretto)
    parsed = parse_response(full_response, modulo_scelto)
    if (modalita == "generazione" and parsed.get("errors")
            and parsed.get("code") and original_prompt):
        new_response, new_parsed = _retry_fix_formula(
            original_prompt, parsed["code"], parsed["errors"], model_id
        )
        if new_response and new_parsed and not new_parsed.get("errors"):
            full_response = new_response
            parsed = new_parsed
            elapsed_str = f"{elapsed:.1f}s + correzione"
        else:
            elapsed_str = f"{elapsed:.1f}s"
    else:
        elapsed_str = f"{elapsed:.1f}s"

    st.markdown(
        f'<div class="ws-resp-header">'
        f'<span class="ws-resp-num">Risposta #{resp_num}</span>'
        f'<span class="ws-timer">⏱️ {elapsed_str} · {model_id}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if sources:
        render_confidence_badge(sources)

    render_response_summary(modalita, len(sources), bool(parsed.get("errors")),
                            modalita == "generazione")

    _mod = st.session_state.modules.get(modulo_scelto)
    has_formula = _mod is not None and _mod.has_formula_only()
    if has_formula:
        if parsed["has_split"] and parsed["code"]:
            if modalita == "generazione":
                render_generation_warning()
                st.caption(
                    "Usala come bozza tecnica: controlla sintassi, logica, casi limite "
                    "e coerenza con le regole aziendali prima di portarla in produzione."
                )

                auto_fixes = parsed.get("auto_fixes", [])
                if auto_fixes:
                    with st.expander("🔧 Correzioni automatiche applicate", expanded=False):
                        for fix in auto_fixes:
                            st.markdown(f"- {html.escape(fix)}")

                validation_errors = parsed.get("errors", [])
                if validation_errors:
                    st.error("❌ Errori di validazione sintassi:")
                    for err in validation_errors:
                        st.markdown(f"- {html.escape(err)}")
                else:
                    st.success("✅ Sintassi WinSarp valida")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Approva e Copia", key=f"approve_{resp_num}", use_container_width=True):
                        st.code(parsed["code"], language="text")
                        st.success("Formula approvata. Puoi copiarla e testarla.")
                with col2:
                    if st.button("🔄 Rigenera", key=f"regen_{resp_num}", use_container_width=True):
                        st.session_state.messages.append({
                            "role": "user", "content": "Rigenera la formula con diverse varianti",
                        })
                        st.rerun()

            from ui.chat_ui import display_formula
            display_formula(parsed["code"], parsed.get("exp", ""), resp_num=resp_num, expanded=True)
            for e in parsed["errors"]:
                st.markdown(f'<div class="ws-err">⚠️ {html.escape(str(e))}</div>', unsafe_allow_html=True)
            if parsed["errors"]:
                st.caption("⚠️ Controlla gli errori prima di usare la formula.")
        else:
            with st.expander("⚠️ Formato non standard — risposta grezza", expanded=True):
                st.write(full_response)
    else:
        st.markdown(
            '<div style="white-space:pre-wrap;word-break:break-word;">' +
            html.escape(full_response) + "</div>",
            unsafe_allow_html=True,
        )

    if sources:
        render_sources_block(sources, expanded=False)

    render_feedback_buttons(resp_num)

    content_to_save = parsed["code"] if parsed["has_split"] else full_response
    st.session_state.messages.append({
        "role": "assistant", "content": content_to_save,
        "exp": parsed.get("exp", ""), "errors": parsed.get("errors", []),
        "sources": sources, "elapsed": elapsed, "resp_num": resp_num,
        "model": st.session_state.model_id, "mode": modalita,
    })
    _logger.info("Response in %s mode: %s (elapsed: %.2fs, sources: %d, errors: %d)",
                 modalita, modulo_scelto, elapsed, len(sources), len(parsed.get("errors", [])))
    append_to_log(log_path, modulo_scelto, "assistant", content_to_save,
                  parsed.get("errors", []), elapsed)
