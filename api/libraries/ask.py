"""Search and question answering over one library or several (federated), plain and streamed."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import _verify_api_key, rate_limited
from api.libraries.common import get_library_store
from config import cfg
from core.evidence_assistant import answer_from_evidence
from core.governance import append_audit
from core.library_store import (
    LibraryAccessError,
    LibraryNotFoundError,
    LibraryStore,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/libraries", tags=["Libraries"])


class ConversationTurn(BaseModel):
    """Una domanda precedente, mandata dal client. Il server non conserva la
    conversazione, e le risposte non vengono ne' inviate ne' usate: vedi
    core/question_rewriter.py per il perche'."""

    question: str = Field(min_length=1, max_length=2000)


class AskLibraryRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)
    conversation_id: str | None = Field(default=None, max_length=100)
    # Gli ultimi scambi, per riscrivere una domanda di raffinamento in forma
    # autonoma prima del recupero. Al massimo tre: oltre, la conversazione
    # pesa piu' della domanda e la riscrittura peggiora.
    history: list[ConversationTurn] = Field(default_factory=list, max_length=3)


class AskFederatedRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    library_ids: list[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=5, ge=1, le=20)
    conversation_id: str | None = Field(default=None, max_length=100)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=3)


class FederatedSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    library_ids: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=10, ge=1, le=50)


@router.get("/{library_id}/search", dependencies=[Depends(rate_limited)])
def search_library(
    library_id: str,
    q: str = "",
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    if len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Inserisci almeno 2 caratteri per cercare")
    try:
        store.get_library(library_id, _auth)
        items, retrieval_profile = store.search_with_profile(library_id, q, actor=_auth)
        return {"items": items, "retrieval_profile": retrieval_profile}
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error


def _record_conversation_messages(
    conversation_id: str | None,
    library_id: str,
    username: str,
    question: str,
    answer: Any,
    citations: Any = None,
) -> None:
    if not conversation_id:
        return
    try:
        from core.conversation_store import conversation_store

        conv = conversation_store.get_conversation(conversation_id, username=username)
        if not conv:
            conversation_store.create_conversation(
                username=username,
                library_id=library_id,
                title=question[:40].strip() or "Conversazione",
                conversation_id=conversation_id,
            )
        conversation_store.add_message(conversation_id, role="user", content=question)
        conversation_store.add_message(
            conversation_id,
            role="assistant",
            content=answer,
            citations=citations or [],
        )
    except Exception as err:
        _logger.warning("Errore nel salvataggio della conversazione %s: %s", conversation_id, err)


def _answer_question(
    store: LibraryStore,
    library_id: str,
    question: str,
    top_k: int,
    actor: dict,
    history: list[dict] | None = None,
    conversation_id: str | None = None,
) -> dict:
    """Evidence-first assistant baseline, intentionally abstaining without sources.

    Shared by the HTTP `/ask` endpoint and the chat webhooks (Slack/Teams):
    both must go through the same access checks and the same evidence-only
    guarantee, so this is the only place that logic is allowed to live.

    `history` sono gli ultimi scambi mandati dal client. Servono a una cosa
    sola: riscrivere una domanda di raffinamento in forma autonoma PRIMA del
    recupero. Da quel punto in poi `question` e' la domanda riscritta e tutto
    il resto — recupero, verifica, citazioni, astensione — la tratta come una
    domanda nuova. La storia non entra mai nel prompt di risposta.
    """
    import time

    from core.question_rewriter import rewrite_with_history
    from core.rag_tracer import trace_rag_query

    t0 = time.perf_counter()
    domanda_originale = question

    with trace_rag_query(
        query=question,
        library_id=library_id,
        username=actor.get("username", ""),
        conversation_id=conversation_id,
    ) as tracer:
        with tracer.span("query_expansion", original_query=question) as s_exp:
            riscrittura = rewrite_with_history(question, history)
            question = riscrittura.question
            s_exp.set_metadata("rewritten", riscrittura.rewritten)
            s_exp.set_metadata("reason", riscrittura.reason)

        from core.metrics import record_rewrite_outcome

        record_rewrite_outcome(riscrittura.reason)
        conversazione = {
            "question_original": domanda_originale,
            "question_rewritten_to": riscrittura.question if riscrittura.rewritten else None,
            "rewrite": riscrittura.reason,
        }
        try:
            library = store.get_library(library_id, actor)
            from core.metrics import rag_retrieval_timer

            with tracer.span("retrieval", limit=top_k) as s_ret:
                with rag_retrieval_timer():
                    citations, retrieval_profile = store.search_with_profile(
                        library_id, question, limit=top_k, actor=actor
                    )
                if not citations:
                    from core.query_expander import expand_query

                    expanded_queries = expand_query(question)
                    for eq in expanded_queries[1:]:
                        citations, retrieval_profile = store.search_with_profile(
                            library_id, eq, limit=top_k, actor=actor
                        )
                        if citations:
                            break
                if not citations and cfg.HYDE_ENABLED:
                    from core.hyde import generate_hypothetical_document

                    hyde_passage = generate_hypothetical_document(question, mode=library.get("assistant_mode"))
                    if hyde_passage and hyde_passage != question:
                        citations, retrieval_profile = store.search_with_profile(
                            library_id, hyde_passage, limit=top_k, actor=actor
                        )
                s_ret.set_metadata("citations_count", len(citations))
        except (LibraryNotFoundError, LibraryAccessError) as error:
            raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error

        from core.evidence_verifier import verify_citations

        with tracer.span("evidence_verification", citations_in=len(citations)) as s_ver:
            citations, evidence_verified = verify_citations(question, citations)
            s_ver.set_metadata("citations_out", len(citations))
            s_ver.set_metadata("evidence_verified", evidence_verified)

        from core.tabular_router import enrich_with_tabular_evidence

        tabular_citations = enrich_with_tabular_evidence(library_id, question, store=store, limit=2)
        if tabular_citations:
            citations = tabular_citations + list(citations)

    if not citations:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        from core.analytics import record_query_event
        from core.metrics import rag_question_recorded

        rag_question_recorded(library_id, "abstained", result_count=0)
        ans_id = record_query_event(
            query=question,
            library_id=library_id,
            actor=actor.get("username", "anonymous"),
            result_count=0,
            latency_ms=latency_ms,
            coverage="insufficient_evidence",
            assistant_mode=library["assistant_mode"],
            fallback_reason="Nessun passaggio corrispondente recuperato.",
        )
        ans_text = "Non ho trovato evidenza sufficiente nella biblioteca selezionata. Prova con parole più specifiche oppure carica il documento pertinente."
        _record_conversation_messages(
            conversation_id=conversation_id,
            library_id=library_id,
            username=actor.get("username", ""),
            question=domanda_originale,
            answer=ans_text,
            citations=[],
        )
        return {
            "answer_id": ans_id,
            "library": {"id": library["id"], "name": library["name"]},
            "question": question,
            "answer": ans_text,
            "status": "abstained",
            "evidence": {"coverage": "insufficient_evidence", "reason": "Nessun passaggio corrispondente recuperato."},
            "citations": [],
            "meta": {
                "assistant_mode": library["assistant_mode"],
                "assistant_provider": library.get("assistant_provider", ""),
                "retrieval_profile": retrieval_profile,
                "evidence_verified": evidence_verified,
                "conversation": conversazione,
                "created_at": datetime.now(UTC).isoformat(),
            },
            "trace": tracer.export_summary(),
        }
    # Le citazioni tornano all'utente marcate se contengono istruzioni rivolte
    # al modello: la fonte esiste e va mostrata, ma il suo testo non e' stato
    # passato all'LLM. L'utente deve poter verificare che la quarantena ha
    # funzionato invece di vedere la citazione sparire nel nulla.
    from core.injection_guard import quarantine_citations
    from core.metrics import record_injection_flagged

    with tracer.span("reranking", candidate_citations=len(citations)) as s_rerank:
        citations, sospette = quarantine_citations(citations)
        if sospette:
            record_injection_flagged(sospette)
        s_rerank.set_metadata("clean_citations", len(citations))
        s_rerank.set_metadata("suspicious_count", sospette)

    with tracer.span("llm_generation", mode=library["assistant_mode"]) as s_llm:
        answer, coverage, reason = answer_from_evidence(
            question,
            citations,
            mode=library["assistant_mode"],
            provider_name=library.get("assistant_provider", ""),
        )
        s_llm.set_metadata("coverage", coverage)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    from core.analytics import record_query_event
    from core.metrics import rag_question_recorded, record_rerank_mode

    rag_question_recorded(
        library_id,
        "answered" if coverage == "supported" else "abstained",
        result_count=len(citations),
    )
    record_rerank_mode(citations[0].get("rerank_mode", "unknown"))
    ans_id = record_query_event(
        query=question,
        library_id=library_id,
        actor=actor.get("username", "anonymous"),
        result_count=len(citations),
        latency_ms=latency_ms,
        coverage=coverage,
        assistant_mode=library["assistant_mode"],
        fallback_reason=reason,
    )
    append_audit(
        cfg.AUDIT_FILE,
        "library_answer",
        actor["username"],
        {
            "library_id": library_id,
            # Chi legge il log deve capire cosa il sistema ha davvero cercato:
            # con la memoria conversazionale la domanda recuperata puo' non
            # essere quella scritta dall'utente.
            "question_rewritten": riscrittura.rewritten,
            "injection_suspected_citations": sospette,
            "assistant_mode": library["assistant_mode"],
            "assistant_provider": library.get("assistant_provider", ""),
            "retrieval_profile": retrieval_profile["mode"],
            "citation_count": len(citations),
            "coverage": coverage,
        },
    )
    result_payload = {
        "answer_id": ans_id,
        "library": {"id": library["id"], "name": library["name"]},
        "question": question,
        "answer": answer,
        "status": "answered" if coverage == "supported" else "abstained",
        "evidence": {"coverage": coverage, "reason": reason},
        "citations": [
            item["citation"]
            | {
                "excerpt": item["excerpt"],
                "marker": index,
                "relevance_score": item["relevance_score"],
                # La fonte esiste e si mostra; se contiene istruzioni rivolte
                # al modello, chi legge deve sapere che il suo testo non e'
                # stato usato per rispondere.
                "injection_suspected": bool(item.get("injection_suspected", False)),
            }
            for index, item in enumerate(citations, start=1)
        ],
        "meta": {
            "assistant_mode": library["assistant_mode"],
            "assistant_provider": library.get("assistant_provider", ""),
            "retrieval_profile": retrieval_profile,
            # False quando la verifica e' disattivata oppure non e' stata
            # eseguibile: chi legge deve poter distinguere "controllato" da
            # "non controllato", invece di presumere il primo.
            "evidence_verified": evidence_verified,
            "conversation": conversazione,
            "created_at": datetime.now(UTC).isoformat(),
        },
        "trace": tracer.export_summary(),
    }

    _record_conversation_messages(
        conversation_id=conversation_id,
        library_id=library_id,
        username=actor.get("username", ""),
        question=domanda_originale,
        answer=answer,
        citations=result_payload["citations"],
    )

    return result_payload


@router.post("/{library_id}/ask", dependencies=[Depends(rate_limited)])
def ask_library(
    library_id: str,
    request: AskLibraryRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    return _answer_question(
        store,
        library_id,
        request.question,
        request.top_k,
        _auth,
        history=[turno.model_dump() for turno in request.history],
        conversation_id=request.conversation_id,
    )


def _answer_question_stream(
    store: LibraryStore,
    library_id: str,
    question: str,
    top_k: int,
    actor: dict,
    history: list[dict] | None = None,
    conversation_id: str | None = None,
):
    import json
    import time

    from core.question_rewriter import rewrite_with_history

    t0 = time.perf_counter()
    domanda_originale = question
    riscrittura = rewrite_with_history(question, history)
    question = riscrittura.question
    from core.metrics import record_rewrite_outcome

    record_rewrite_outcome(riscrittura.reason)
    conversazione = {
        "question_original": domanda_originale,
        "question_rewritten_to": riscrittura.question if riscrittura.rewritten else None,
        "rewrite": riscrittura.reason,
    }

    try:
        library = store.get_library(library_id, actor)
    except (LibraryNotFoundError, LibraryAccessError):
        yield f"event: error\ndata: {json.dumps({'detail': 'Biblioteca non trovata'})}\n\n"
        return

    yield f"event: status\ndata: {json.dumps({'step': 'retrieving', 'question': question})}\n\n"

    from core.metrics import rag_retrieval_timer

    with rag_retrieval_timer():
        citations, retrieval_profile = store.search_with_profile(library_id, question, limit=top_k, actor=actor)
    if not citations:
        from core.query_expander import expand_query

        expanded_queries = expand_query(question)
        for eq in expanded_queries[1:]:
            citations, retrieval_profile = store.search_with_profile(library_id, eq, limit=top_k, actor=actor)
            if citations:
                break
    if not citations and cfg.HYDE_ENABLED:
        from core.hyde import generate_hypothetical_document

        hyde_passage = generate_hypothetical_document(question, mode=library.get("assistant_mode"))
        if hyde_passage and hyde_passage != question:
            citations, retrieval_profile = store.search_with_profile(library_id, hyde_passage, limit=top_k, actor=actor)

    yield f"event: status\ndata: {json.dumps({'step': 'verifying'})}\n\n"

    from core.evidence_verifier import verify_citations

    citations, evidence_verified = verify_citations(question, citations)

    from core.tabular_router import enrich_with_tabular_evidence

    tabular_citations = enrich_with_tabular_evidence(library_id, question, store=store, limit=2)
    if tabular_citations:
        citations = tabular_citations + list(citations)

    if not citations:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        from core.analytics import record_query_event
        from core.metrics import rag_question_recorded

        rag_question_recorded(library_id, "abstained", result_count=0)
        ans_id = record_query_event(
            query=question,
            library_id=library_id,
            actor=actor.get("username", "anonymous"),
            result_count=0,
            latency_ms=latency_ms,
            coverage="insufficient_evidence",
            assistant_mode=library["assistant_mode"],
            fallback_reason="Nessun passaggio corrispondente recuperato.",
        )
        abstained_payload = {
            "answer_id": ans_id,
            "library": {"id": library["id"], "name": library["name"]},
            "question": question,
            "answer": "Non ho trovato evidenza sufficiente nella biblioteca selezionata. Prova con parole più specifiche oppure carica il documento pertinente.",
            "status": "abstained",
            "evidence": {"coverage": "insufficient_evidence", "reason": "Nessun passaggio corrispondente recuperato."},
            "citations": [],
            "meta": {
                "assistant_mode": library["assistant_mode"],
                "assistant_provider": library.get("assistant_provider", ""),
                "retrieval_profile": retrieval_profile,
                "evidence_verified": evidence_verified,
                "conversation": conversazione,
                "created_at": datetime.now(UTC).isoformat(),
            },
        }
        _record_conversation_messages(
            conversation_id=conversation_id,
            library_id=library_id,
            username=actor.get("username", ""),
            question=domanda_originale,
            answer=abstained_payload["answer"],
            citations=[],
        )
        yield f"event: done\ndata: {json.dumps(abstained_payload)}\n\n"
        return

    from core.injection_guard import quarantine_citations
    from core.metrics import record_injection_flagged

    citations, sospette = quarantine_citations(citations)
    if sospette:
        record_injection_flagged(sospette)

    formatted_citations = [
        item["citation"]
        | {
            "excerpt": item["excerpt"],
            "marker": index,
            "relevance_score": item["relevance_score"],
            "injection_suspected": bool(item.get("injection_suspected", False)),
        }
        for index, item in enumerate(citations, start=1)
    ]
    yield f"event: citations\ndata: {json.dumps({'citations': formatted_citations})}\n\n"
    yield f"event: status\ndata: {json.dumps({'step': 'composing'})}\n\n"

    answer, coverage, reason = answer_from_evidence(
        question,
        citations,
        mode=library["assistant_mode"],
        provider_name=library.get("assistant_provider", ""),
    )

    yield f"event: answer\ndata: {json.dumps({'chunk': answer})}\n\n"

    latency_ms = (time.perf_counter() - t0) * 1000.0
    from core.analytics import record_query_event
    from core.metrics import rag_question_recorded, record_rerank_mode

    rag_question_recorded(
        library_id,
        "answered" if coverage == "supported" else "abstained",
        result_count=len(citations),
    )
    record_rerank_mode(citations[0].get("rerank_mode", "unknown"))
    ans_id = record_query_event(
        query=question,
        library_id=library_id,
        actor=actor.get("username", "anonymous"),
        result_count=len(citations),
        latency_ms=latency_ms,
        coverage=coverage,
        assistant_mode=library["assistant_mode"],
        fallback_reason=reason,
    )
    append_audit(
        cfg.AUDIT_FILE,
        "library_answer",
        actor["username"],
        {
            "library_id": library_id,
            "question_rewritten": riscrittura.rewritten,
            "injection_suspected_citations": sospette,
            "assistant_mode": library["assistant_mode"],
            "assistant_provider": library.get("assistant_provider", ""),
            "retrieval_profile": retrieval_profile["mode"],
            "citation_count": len(citations),
            "coverage": coverage,
        },
    )

    final_payload = {
        "answer_id": ans_id,
        "library": {"id": library["id"], "name": library["name"]},
        "question": question,
        "answer": answer,
        "status": "answered" if coverage == "supported" else "abstained",
        "evidence": {"coverage": coverage, "reason": reason},
        "citations": formatted_citations,
        "meta": {
            "assistant_mode": library["assistant_mode"],
            "assistant_provider": library.get("assistant_provider", ""),
            "retrieval_profile": retrieval_profile,
            "evidence_verified": evidence_verified,
            "conversation": conversazione,
            "created_at": datetime.now(UTC).isoformat(),
        },
    }

    _record_conversation_messages(
        conversation_id=conversation_id,
        library_id=library_id,
        username=actor.get("username", ""),
        question=domanda_originale,
        answer=answer,
        citations=formatted_citations,
    )

    yield f"event: done\ndata: {json.dumps(final_payload)}\n\n"


def _answer_federated_question_stream(
    store: LibraryStore,
    library_ids: list[str],
    question: str,
    top_k: int,
    actor: dict,
    history: list[dict] | None = None,
    conversation_id: str | None = None,
):
    import json
    import time

    from core.question_rewriter import rewrite_with_history

    t0 = time.perf_counter()
    domanda_originale = question
    riscrittura = rewrite_with_history(question, history)
    question = riscrittura.question
    from core.metrics import record_rewrite_outcome

    record_rewrite_outcome(riscrittura.reason)
    conversazione = {
        "question_original": domanda_originale,
        "question_rewritten_to": riscrittura.question if riscrittura.rewritten else None,
        "rewrite": riscrittura.reason,
    }

    yield f"event: status\ndata: {json.dumps({'step': 'retrieving', 'question': question})}\n\n"

    from core.metrics import rag_retrieval_timer

    with rag_retrieval_timer():
        citations, retrieval_profile = store.search_federated(
            query=question,
            library_ids=library_ids,
            limit=top_k,
            actor=actor,
        )

    if not citations:
        from core.query_expander import expand_query

        expanded_queries = expand_query(question)
        for eq in expanded_queries[1:]:
            citations, retrieval_profile = store.search_federated(
                query=eq,
                library_ids=library_ids,
                limit=top_k,
                actor=actor,
            )
            if citations:
                break

    yield f"event: status\ndata: {json.dumps({'step': 'verifying'})}\n\n"

    from core.evidence_verifier import verify_citations

    citations, evidence_verified = verify_citations(question, citations)

    if not citations:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        from core.analytics import record_query_event
        from core.metrics import rag_question_recorded

        rag_question_recorded("federated", "abstained", result_count=0)
        ans_id = record_query_event(
            query=question,
            library_id="federated",
            actor=actor.get("username", "anonymous"),
            result_count=0,
            latency_ms=latency_ms,
            coverage="insufficient_evidence",
            assistant_mode="evidence_only",
            fallback_reason="Nessun passaggio corrispondente recuperato nelle biblioteche interrogate.",
        )
        abstained_payload = {
            "answer_id": ans_id,
            "library": {"id": "federated", "name": "Ricerca Federata Multi-Biblioteca"},
            "question": question,
            "answer": "Non ho trovato evidenza sufficiente nelle biblioteche selezionate. Prova con termini più specifici.",
            "status": "abstained",
            "evidence": {"coverage": "insufficient_evidence", "reason": "Nessun passaggio corrispondente recuperato."},
            "citations": [],
            "meta": {
                "assistant_mode": "evidence_only",
                "retrieval_profile": retrieval_profile,
                "evidence_verified": evidence_verified,
                "conversation": conversazione,
                "created_at": datetime.now(UTC).isoformat(),
            },
        }
        _record_conversation_messages(
            conversation_id=conversation_id,
            library_id="federated",
            username=actor.get("username", ""),
            question=domanda_originale,
            answer=abstained_payload["answer"],
            citations=[],
        )
        yield f"event: done\ndata: {json.dumps(abstained_payload)}\n\n"
        return

    from core.injection_guard import quarantine_citations
    from core.metrics import record_injection_flagged

    citations, sospette = quarantine_citations(citations)
    if sospette:
        record_injection_flagged(sospette)

    formatted_citations = [
        item["citation"]
        | {
            "excerpt": item["excerpt"],
            "marker": index,
            "relevance_score": item["relevance_score"],
            "library_id": item.get("library_id", ""),
            "library_name": item.get("library_name", ""),
            "injection_suspected": bool(item.get("injection_suspected", False)),
        }
        for index, item in enumerate(citations, start=1)
    ]
    yield f"event: citations\ndata: {json.dumps({'citations': formatted_citations})}\n\n"
    yield f"event: status\ndata: {json.dumps({'step': 'composing'})}\n\n"

    answer, coverage, reason = answer_from_evidence(
        question,
        citations,
        mode="evidence_only",
        provider_name="",
    )

    yield f"event: answer\ndata: {json.dumps({'chunk': answer})}\n\n"

    latency_ms = (time.perf_counter() - t0) * 1000.0
    from core.analytics import record_query_event
    from core.metrics import rag_question_recorded, record_rerank_mode

    rag_question_recorded(
        "federated",
        "answered" if coverage == "supported" else "abstained",
        result_count=len(citations),
    )
    record_rerank_mode(citations[0].get("rerank_mode", "federated_rrf"))
    ans_id = record_query_event(
        query=question,
        library_id="federated",
        actor=actor.get("username", "anonymous"),
        result_count=len(citations),
        latency_ms=latency_ms,
        coverage=coverage,
        assistant_mode="evidence_only",
        fallback_reason=reason,
    )
    append_audit(
        cfg.AUDIT_FILE,
        "federated_library_answer",
        actor["username"],
        {
            "target_libraries": library_ids or "all_accessible",
            "question_rewritten": riscrittura.rewritten,
            "injection_suspected_citations": sospette,
            "retrieval_profile": retrieval_profile["mode"],
            "citation_count": len(citations),
            "coverage": coverage,
        },
    )

    final_payload = {
        "answer_id": ans_id,
        "library": {"id": "federated", "name": "Ricerca Federata Multi-Biblioteca"},
        "question": question,
        "answer": answer,
        "status": "answered" if coverage == "supported" else "abstained",
        "evidence": {"coverage": coverage, "reason": reason},
        "citations": formatted_citations,
        "meta": {
            "assistant_mode": "evidence_only",
            "retrieval_profile": retrieval_profile,
            "evidence_verified": evidence_verified,
            "conversation": conversazione,
            "created_at": datetime.now(UTC).isoformat(),
        },
    }

    _record_conversation_messages(
        conversation_id=conversation_id,
        library_id="federated",
        username=actor.get("username", ""),
        question=domanda_originale,
        answer=answer,
        citations=formatted_citations,
    )

    yield f"event: done\ndata: {json.dumps(final_payload)}\n\n"


@router.post("/federated/search", dependencies=[Depends(rate_limited)])
def search_federated_endpoint(
    request: FederatedSearchRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Esegue una ricerca cross-library federata nelle biblioteche accessibili all'utente."""
    results, profile = store.search_federated(
        query=request.query,
        library_ids=request.library_ids,
        limit=request.limit,
        actor=_auth,
    )
    return {
        "query": request.query,
        "results": results,
        "profile": profile,
    }


@router.post("/federated/ask/stream", dependencies=[Depends(rate_limited)])
def ask_federated_stream(
    request: AskFederatedRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    """Interroga più biblioteche in modalità RAG federata con risposte basate su evidenze cross-library."""
    return StreamingResponse(
        _answer_federated_question_stream(
            store,
            request.library_ids,
            request.question,
            request.top_k,
            _auth,
            history=[turno.model_dump() for turno in request.history],
            conversation_id=request.conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{library_id}/ask/stream", dependencies=[Depends(rate_limited)])
def ask_library_stream(
    library_id: str,
    request: AskLibraryRequest,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    try:
        store.get_library(library_id, _auth)
    except (LibraryNotFoundError, LibraryAccessError) as error:
        raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error

    return StreamingResponse(
        _answer_question_stream(
            store,
            library_id,
            request.question,
            request.top_k,
            _auth,
            history=[turno.model_dump() for turno in request.history],
            conversation_id=request.conversation_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
