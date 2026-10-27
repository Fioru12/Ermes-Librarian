"""Search and question answering over one library or several (federated), plain and streamed."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
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


_NO_PASSAGE = "Nessun passaggio corrispondente recuperato."
_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


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


@dataclass
class _Scope:
    """Cio' che distingue una domanda a una biblioteca da una federata.

    Tutto il resto — riscrittura, recupero, verifica, quarantena, risposta,
    metriche, audit, conversazione — e' lo stesso percorso.
    """

    library_id: str  # chiave per metriche, analytics e conversazione
    library: dict  # {"id", "name"} riportato nella risposta
    assistant_mode: str
    assistant_provider: str | None  # None: la federata non lo riporta
    abstain_answer: str
    abstain_fallback_reason: str
    default_rerank_mode: str
    audit_event: str
    audit_target: dict
    federated: bool = False

    @classmethod
    def for_library(cls, library: dict) -> _Scope:
        return cls(
            library_id=library["id"],
            library={"id": library["id"], "name": library["name"]},
            assistant_mode=library["assistant_mode"],
            assistant_provider=library.get("assistant_provider", ""),
            abstain_answer=(
                "Non ho trovato evidenza sufficiente nella biblioteca selezionata. "
                "Prova con parole più specifiche oppure carica il documento pertinente."
            ),
            abstain_fallback_reason=_NO_PASSAGE,
            default_rerank_mode="unknown",
            audit_event="library_answer",
            audit_target={"library_id": library["id"]},
        )

    @classmethod
    def federated_over(cls, library_ids: list[str]) -> _Scope:
        return cls(
            library_id="federated",
            library={"id": "federated", "name": "Ricerca Federata Multi-Biblioteca"},
            assistant_mode="evidence_only",
            assistant_provider=None,
            abstain_answer="Non ho trovato evidenza sufficiente nelle biblioteche selezionate. Prova con termini più specifici.",
            abstain_fallback_reason="Nessun passaggio corrispondente recuperato nelle biblioteche interrogate.",
            default_rerank_mode="federated_rrf",
            audit_event="federated_library_answer",
            audit_target={"target_libraries": library_ids or "all_accessible"},
            federated=True,
        )

    def assistant_fields(self) -> dict:
        if self.assistant_provider is None:
            return {"assistant_mode": self.assistant_mode}
        return {"assistant_mode": self.assistant_mode, "assistant_provider": self.assistant_provider}


@dataclass
class _Turn:
    """Una domanda in corso: lo stato che serve per chiuderla in uno dei due modi."""

    actor: dict
    conversation_id: str | None
    original_question: str
    rewrite: Any  # core.question_rewriter.Riscrittura
    started: float = field(default_factory=time.perf_counter)

    @classmethod
    def start(
        cls, question: str, history: list[dict] | None, actor: dict, conversation_id: str | None, span=None
    ) -> _Turn:
        """Riscrive la domanda di raffinamento in forma autonoma. Da qui in poi
        `turn.question` e' la domanda che si cerca; la storia non serve piu'."""
        from core.metrics import record_rewrite_outcome
        from core.question_rewriter import rewrite_with_history

        started = time.perf_counter()
        riscrittura = rewrite_with_history(question, history)
        if span is not None:
            span.set_metadata("rewritten", riscrittura.rewritten)
            span.set_metadata("reason", riscrittura.reason)
        record_rewrite_outcome(riscrittura.reason)
        return cls(actor, conversation_id, question, riscrittura, started)

    @property
    def question(self) -> str:
        return str(self.rewrite.question)

    def conversation_meta(self) -> dict:
        return {
            "question_original": self.original_question,
            "question_rewritten_to": self.rewrite.question if self.rewrite.rewritten else None,
            "rewrite": self.rewrite.reason,
        }

    def _latency_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000.0

    def _payload(self, scope: _Scope, answer: str, status: str, evidence: dict, citations: list, meta: dict) -> dict:
        return {
            "library": scope.library,
            "question": self.question,
            "answer": answer,
            "status": status,
            "evidence": evidence,
            "citations": citations,
            "meta": scope.assistant_fields()
            | meta
            | {"conversation": self.conversation_meta(), "created_at": datetime.now(UTC).isoformat()},
        }

    def _remember(self, scope: _Scope, answer: str, citations: list) -> None:
        _record_conversation_messages(
            conversation_id=self.conversation_id,
            library_id=scope.library_id,
            username=self.actor.get("username", ""),
            question=self.original_question,
            answer=answer,
            citations=citations,
        )

    def abstained(self, scope: _Scope, retrieval_profile: dict, evidence_verified: bool) -> dict:
        """Nessuna fonte sopravvissuta: si dice, non si inventa."""
        from core.analytics import record_query_event
        from core.metrics import rag_question_recorded

        latency_ms = self._latency_ms()
        rag_question_recorded(scope.library_id, "abstained", result_count=0)
        answer_id = record_query_event(
            query=self.question,
            library_id=scope.library_id,
            actor=self.actor.get("username", "anonymous"),
            result_count=0,
            latency_ms=latency_ms,
            coverage="insufficient_evidence",
            assistant_mode=scope.assistant_mode,
            fallback_reason=scope.abstain_fallback_reason,
        )
        payload = {"answer_id": answer_id} | self._payload(
            scope,
            scope.abstain_answer,
            "abstained",
            {"coverage": "insufficient_evidence", "reason": _NO_PASSAGE},
            [],
            {"retrieval_profile": retrieval_profile, "evidence_verified": evidence_verified},
        )
        self._remember(scope, scope.abstain_answer, [])
        return payload

    def answered(
        self,
        scope: _Scope,
        citations: list[dict],
        formatted_citations: list[dict],
        answer: str,
        coverage: str,
        reason: str | None,
        suspicious: int,
        retrieval_profile: dict,
        evidence_verified: bool,
    ) -> dict:
        from core.analytics import record_query_event
        from core.metrics import rag_question_recorded, record_rerank_mode

        latency_ms = self._latency_ms()
        rag_question_recorded(
            scope.library_id,
            "answered" if coverage == "supported" else "abstained",
            result_count=len(citations),
        )
        record_rerank_mode(citations[0].get("rerank_mode", scope.default_rerank_mode))
        answer_id = record_query_event(
            query=self.question,
            library_id=scope.library_id,
            actor=self.actor.get("username", "anonymous"),
            result_count=len(citations),
            latency_ms=latency_ms,
            coverage=coverage,
            assistant_mode=scope.assistant_mode,
            fallback_reason=reason,
        )
        append_audit(
            cfg.AUDIT_FILE,
            scope.audit_event,
            self.actor["username"],
            scope.audit_target
            | {
                # Chi legge il log deve capire cosa il sistema ha davvero cercato:
                # con la memoria conversazionale la domanda recuperata puo' non
                # essere quella scritta dall'utente.
                "question_rewritten": self.rewrite.rewritten,
                "injection_suspected_citations": suspicious,
            }
            | (scope.assistant_fields() if not scope.federated else {})
            | {
                "retrieval_profile": retrieval_profile["mode"],
                "citation_count": len(citations),
                "coverage": coverage,
            },
        )
        payload = {"answer_id": answer_id} | self._payload(
            scope,
            answer,
            "answered" if coverage == "supported" else "abstained",
            {"coverage": coverage, "reason": reason},
            formatted_citations,
            # evidence_verified e' False quando la verifica e' disattivata
            # oppure non e' stata eseguibile: chi legge deve poter distinguere
            # "controllato" da "non controllato", invece di presumere il primo.
            {"retrieval_profile": retrieval_profile, "evidence_verified": evidence_verified},
        )
        self._remember(scope, answer, formatted_citations)
        return payload


def _retrieve(search: Callable[[str], tuple[list[dict], dict]], question: str, hyde_mode: str | None):
    """Recupero con i ripieghi: varianti della domanda, poi HyDE.

    `search(query)` interroga una biblioteca o piu'. `hyde_mode` None spegne
    HyDE (la federata non lo usa: non ha una modalita' assistente unica).
    """
    from core.metrics import rag_retrieval_timer

    with rag_retrieval_timer():
        citations, retrieval_profile = search(question)
    if not citations:
        from core.query_expander import expand_query

        for variant in expand_query(question)[1:]:
            citations, retrieval_profile = search(variant)
            if citations:
                break
    if not citations and hyde_mode is not None and cfg.HYDE_ENABLED:
        from core.hyde import generate_hypothetical_document

        hyde_passage = generate_hypothetical_document(question, mode=hyde_mode)
        if hyde_passage and hyde_passage != question:
            citations, retrieval_profile = search(hyde_passage)
    return citations, retrieval_profile


def _library_search(store: LibraryStore, library_id: str, top_k: int, actor: dict):
    return lambda query: store.search_with_profile(library_id, query, limit=top_k, actor=actor)


def _with_tabular_evidence(store: LibraryStore, library_id: str, question: str, citations: list[dict]) -> list[dict]:
    from core.tabular_router import enrich_with_tabular_evidence

    tabular_citations = enrich_with_tabular_evidence(library_id, question, store=store, limit=2)
    return tabular_citations + list(citations) if tabular_citations else citations


def _quarantine(citations: list[dict]) -> tuple[list[dict], int]:
    """Le citazioni tornano all'utente marcate se contengono istruzioni rivolte
    al modello: la fonte esiste e va mostrata, ma il suo testo non e' stato
    passato all'LLM. L'utente deve poter verificare che la quarantena ha
    funzionato invece di vedere la citazione sparire nel nulla."""
    from core.injection_guard import quarantine_citations
    from core.metrics import record_injection_flagged

    citations, suspicious = quarantine_citations(citations)
    if suspicious:
        record_injection_flagged(suspicious)
    return citations, suspicious


def _format_citations(citations: list[dict], federated: bool = False) -> list[dict]:
    formatted = []
    for index, item in enumerate(citations, start=1):
        extra = {"excerpt": item["excerpt"], "marker": index, "relevance_score": item["relevance_score"]}
        if federated:
            extra |= {"library_id": item.get("library_id", ""), "library_name": item.get("library_name", "")}
        # La fonte esiste e si mostra; se contiene istruzioni rivolte al
        # modello, chi legge deve sapere che il suo testo non e' stato usato
        # per rispondere.
        extra["injection_suspected"] = bool(item.get("injection_suspected", False))
        formatted.append(item["citation"] | extra)
    return formatted


def _compose(scope: _Scope, question: str, citations: list[dict]) -> tuple[str, str, str | None]:
    return answer_from_evidence(
        question,
        citations,
        mode=scope.assistant_mode,
        provider_name=scope.assistant_provider or "",
    )


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
    guarantee. The streamed variants below walk the same steps through the
    same helpers.

    `history` sono gli ultimi scambi mandati dal client. Servono a una cosa
    sola: riscrivere una domanda di raffinamento in forma autonoma PRIMA del
    recupero. Da quel punto in poi la domanda e' quella riscritta e tutto
    il resto — recupero, verifica, citazioni, astensione — la tratta come una
    domanda nuova. La storia non entra mai nel prompt di risposta.
    """
    from core.evidence_verifier import verify_citations
    from core.rag_tracer import trace_rag_query

    with trace_rag_query(
        query=question,
        library_id=library_id,
        username=actor.get("username", ""),
        conversation_id=conversation_id,
    ) as tracer:
        with tracer.span("query_expansion", original_query=question) as s_exp:
            turn = _Turn.start(question, history, actor, conversation_id, span=s_exp)
        question = turn.question
        try:
            library = store.get_library(library_id, actor)
            with tracer.span("retrieval", limit=top_k) as s_ret:
                citations, retrieval_profile = _retrieve(
                    _library_search(store, library_id, top_k, actor), question, library.get("assistant_mode")
                )
                s_ret.set_metadata("citations_count", len(citations))
        except (LibraryNotFoundError, LibraryAccessError) as error:
            raise HTTPException(status_code=404, detail="Biblioteca non trovata") from error

        with tracer.span("evidence_verification", citations_in=len(citations)) as s_ver:
            citations, evidence_verified = verify_citations(
                question, citations, library["assistant_mode"], library.get("assistant_provider", "")
            )
            s_ver.set_metadata("citations_out", len(citations))
            s_ver.set_metadata("evidence_verified", evidence_verified)

        citations = _with_tabular_evidence(store, library_id, question, citations)

    scope = _Scope.for_library(library)
    if not citations:
        return turn.abstained(scope, retrieval_profile, evidence_verified) | {"trace": tracer.export_summary()}

    with tracer.span("reranking", candidate_citations=len(citations)) as s_rerank:
        citations, suspicious = _quarantine(citations)
        s_rerank.set_metadata("clean_citations", len(citations))
        s_rerank.set_metadata("suspicious_count", suspicious)

    with tracer.span("llm_generation", mode=scope.assistant_mode) as s_llm:
        answer, coverage, reason = _compose(scope, question, citations)
        s_llm.set_metadata("coverage", coverage)

    result = turn.answered(
        scope,
        citations,
        _format_citations(citations),
        answer,
        coverage,
        reason,
        suspicious,
        retrieval_profile,
        evidence_verified,
    )
    return result | {"trace": tracer.export_summary()}


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
    turn = _Turn.start(question, history, actor, conversation_id)
    try:
        library = store.get_library(library_id, actor)
    except (LibraryNotFoundError, LibraryAccessError):
        yield _sse("error", {"detail": "Biblioteca non trovata"})
        return
    yield from _stream_answer(
        turn,
        _Scope.for_library(library),
        _library_search(store, library_id, top_k, actor),
        hyde_mode=library.get("assistant_mode"),
        tabular=lambda question, citations: _with_tabular_evidence(store, library_id, question, citations),
    )


def _answer_federated_question_stream(
    store: LibraryStore,
    library_ids: list[str],
    question: str,
    top_k: int,
    actor: dict,
    history: list[dict] | None = None,
    conversation_id: str | None = None,
):
    turn = _Turn.start(question, history, actor, conversation_id)
    yield from _stream_answer(
        turn,
        _Scope.federated_over(library_ids),
        lambda query: store.search_federated(query=query, library_ids=library_ids, limit=top_k, actor=actor),
        hyde_mode=None,
        tabular=None,
    )


def _stream_answer(
    turn: _Turn,
    scope: _Scope,
    search: Callable[[str], tuple[list[dict], dict]],
    hyde_mode: str | None,
    tabular: Callable[[str, list[dict]], list[dict]] | None,
):
    """Gli stessi passi di `_answer_question`, annunciati come eventi SSE."""
    from core.evidence_verifier import verify_citations

    question = turn.question
    yield _sse("status", {"step": "retrieving", "question": question})
    citations, retrieval_profile = _retrieve(search, question, hyde_mode)

    yield _sse("status", {"step": "verifying"})
    citations, evidence_verified = verify_citations(
        question, citations, scope.assistant_mode, scope.assistant_provider or ""
    )
    if tabular is not None:
        citations = tabular(question, citations)

    if not citations:
        yield _sse("done", turn.abstained(scope, retrieval_profile, evidence_verified))
        return

    citations, suspicious = _quarantine(citations)
    formatted_citations = _format_citations(citations, federated=scope.federated)
    yield _sse("citations", {"citations": formatted_citations})
    yield _sse("status", {"step": "composing"})

    answer, coverage, reason = _compose(scope, question, citations)
    yield _sse("answer", {"chunk": answer})

    yield _sse(
        "done",
        turn.answered(
            scope,
            citations,
            formatted_citations,
            answer,
            coverage,
            reason,
            suspicious,
            retrieval_profile,
            evidence_verified,
        ),
    )


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
        headers=_SSE_HEADERS,
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
        headers=_SSE_HEADERS,
    )
