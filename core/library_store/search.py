"""Keyword, semantic and federated search over library chunks."""

from __future__ import annotations

import json
import logging
import math
import re

from config import cfg
from core.library_embeddings import cosine_similarity, embed_texts, min_semantic_score
from core.library_store.base import StoreBase
from core.library_store.common import (
    _MAX_KEYWORD_CANDIDATES,
    _MAX_SQL_VARIABILI,
    _QUERY_STOPWORDS,
    LibraryAccessError,
    LibraryNotFoundError,
)
from core.query_expander import expand_query
from core.search_cache import get_search_cache

_logger = logging.getLogger(__name__)


class SearchMixin(StoreBase):
    def _keyword_candidates(self, connection, library_id: str, query: str, hidden: set[str]) -> set[str]:
        """Trova i chunk_id candidati via keyword search (FTS5 su SQLite, tsvector su Postgres)."""
        tokens = [
            self._search_token(token)
            for token in re.findall(r"[\wÀ-ÿ]{3,}", query.lower())
            if token not in _QUERY_STOPWORDS
        ]
        if not tokens:
            for token in re.findall(r"[\wÀ-ÿ]{2,}", query.lower()):
                if token not in _QUERY_STOPWORDS:
                    clean = re.sub(r"[^\wÀ-ÿ]", "", token)
                    if clean:
                        tokens.append(clean)
        if not tokens:
            return set()

        # Il ranking finale e' calcolato in Python su ogni candidato: con una
        # parola presente quasi ovunque erano decine di migliaia di righe, e
        # 3,2 s a 50.000 passaggi (evaluation/archive_scale.py). Il database
        # ordina gia' per rilevanza full-text, quindi si prendono solo i primi,
        # piu' quanti potrebbero essere scartati come nascosti.
        tetto = _MAX_KEYWORD_CANDIDATES + len(hidden)

        if self._is_postgres:
            # Stessa semantica del ramo SQLite: la frase intera OPPURE uno
            # qualunque dei token (prefisso). Fino al 18 settembre 2026 la
            # frase era scritta con le virgolette di FTS5 — sintassi che
            # tsquery non ha ("syntax error in tsquery", primo run reale su
            # Postgres) — e i token erano in AND: con l'espansione dei
            # sinonimi (sei token per "sicurezza") non trovava mai niente.
            # `phraseto_tsquery` gestisce la frase da solo; i token sono
            # \w puri, quindi `|` fra prefissi e' una tsquery valida.
            clean_phrase = re.sub(r"[^\wÀ-ÿ\s]", " ", query).strip()
            clean_tokens = [re.sub(r"[^\wÀ-ÿ]", "", t) for t in tokens]
            token_query = " | ".join(f"{t}:*" for t in clean_tokens if t)
            rows = connection.execute(
                """
                SELECT c.id AS chunk_id, c.document_id AS document_id FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.library_id = ?
                  AND (c.search_tsv @@ to_tsquery('simple', ?)
                       OR (? <> '' AND c.search_tsv @@ phraseto_tsquery('simple', ?)))
                ORDER BY ts_rank(c.search_tsv, to_tsquery('simple', ?)) DESC
                LIMIT ?
                """,
                (
                    library_id,
                    token_query,
                    clean_phrase if len(clean_phrase.split()) > 1 else "",
                    clean_phrase,
                    token_query,
                    tetto,
                ),
            ).fetchall()
        else:
            # SQLite: FTS5
            fts_query_parts = []
            clean_phrase = re.sub(r"[^\wÀ-ÿ\s]", " ", query).strip()
            phrase_words = clean_phrase.split()
            if len(phrase_words) > 1:
                fts_query_parts.append('"' + " ".join(phrase_words) + '"')
            for token in tokens:
                clean_token = re.sub(r"[^\wÀ-ÿ]", "", token)
                if len(clean_token) >= 3:
                    fts_query_parts.append(f"{clean_token}*")
            fts_match_query = " OR ".join(fts_query_parts)
            if not fts_match_query:
                return set()
            rows = connection.execute(
                "SELECT chunk_id, document_id FROM document_chunks_fts "
                "WHERE document_chunks_fts MATCH ? AND library_id = ? "
                "ORDER BY bm25(document_chunks_fts) LIMIT ?",
                (fts_match_query, library_id, tetto),
            ).fetchall()

        # Il confronto era fra chunk_id e l'insieme `hidden`, che contiene id
        # di documento: non filtrava mai niente. Innocuo finche' il filtro vero
        # restava a valle, sbagliato da leggere e da ereditare.
        return {row["chunk_id"] for row in rows if row["document_id"] not in hidden}

    def search_documents(self, library_id: str, query: str, limit: int = 20) -> list[dict]:
        """Return only the result list for callers that do not need retrieval metadata."""
        results, _ = self.search_with_profile(library_id, query, limit)
        return results

    def search_with_profile(
        self, library_id: str, query: str, limit: int = 20, actor: dict | None = None
    ) -> tuple[list[dict], dict]:
        """Retrieve chunks with a truthful local retrieval profile."""
        library = self.get_library(library_id, actor)
        normalized = query.strip()
        if not normalized:
            return [], {"mode": "keyword", "semantic_indexed_chunks": 0, "semantic_used": False}

        # Check semantic cache (invalidated when doc_count changes).
        # Lo scope = username: con ACL attive utenti diversi devono vedere
        # risultati diversi, quindi la cache è partizionata per utente per
        # evitare leak/falsi negativi tra chi ha permessi differenti.
        cache = get_search_cache()
        doc_count = library.get("document_count", 0)
        scope = actor.get("username", "") if actor else ""
        # Letta da get_library, quindi prima della ricerca: vedi
        # SemanticSearchCache.put().
        generation = library.get("cache_generation", 0)
        cached = cache.get(library_id, normalized, doc_count, scope, generation=generation)
        if cached is not None:
            return cached

        with self._connection() as connection:
            hidden = self._hidden_document_ids(connection, library, actor)

            if self._is_postgres:
                emb_filter = "(c.embedding_json IS NOT NULL AND c.embedding_json::text <> 'null')"
            else:
                emb_filter = "c.embedding_json <> ''"

            row = connection.execute(
                f"SELECT COUNT(c.id) AS count FROM document_chunks c JOIN documents d ON d.id = c.document_id WHERE d.library_id = ? AND {emb_filter}",  # nosec B608
                (library_id,),
            ).fetchone()
            indexed_count = row.get("count", 0) if isinstance(row, dict) else row[0]

            query_embeddings = embed_texts([normalized]) if indexed_count else []
            query_embedding = query_embeddings[0] if query_embeddings else []
            semantic_used = bool(query_embedding and indexed_count)

            tokens = [
                self._search_token(t)
                for t in re.findall(r"[\wÀ-ÿ]{3,}", normalized.lower())
                if t not in _QUERY_STOPWORDS
            ]
            candidate_chunk_ids = self._keyword_candidates(connection, library_id, normalized, hidden)

            for eq in expand_query(normalized)[1:]:
                candidate_chunk_ids.update(self._keyword_candidates(connection, library_id, eq, hidden))

            if semantic_used:
                emb_rows = connection.execute(
                    f"SELECT c.id FROM document_chunks c JOIN documents d ON d.id = c.document_id WHERE d.library_id = ? AND {emb_filter}",  # nosec B608
                    (library_id,),
                ).fetchall()
                for r in emb_rows:
                    cid = r.get("id") if isinstance(r, dict) else r[0]
                    if cid:
                        candidate_chunk_ids.add(str(cid))

            if not candidate_chunk_ids and not semantic_used:
                return [], {"mode": "keyword", "semantic_indexed_chunks": indexed_count, "semantic_used": False}

            if candidate_chunk_ids:
                # A blocchi, e non in un unico IN (...): la query usava un
                # segnaposto per ogni candidato, e SQLite ne accetta al massimo
                # 32766. Su un archivio grande una parola comune supera quel
                # numero e la ricerca NON rallenta, fallisce con
                # "too many SQL variables". Misurato: 50.000 passaggi bastano
                # (evaluation/archive_scale.py).
                #
                # 900 e' sotto il limite storico di 999 delle build piu'
                # vecchie, quindi la correzione vale anche li'.
                elenco = list(candidate_chunk_ids)
                rows = []
                for primo in range(0, len(elenco), _MAX_SQL_VARIABILI):
                    blocco = elenco[primo : primo + _MAX_SQL_VARIABILI]
                    placeholders = ",".join("?" for _ in blocco)
                    rows.extend(
                        connection.execute(
                            f"SELECT documents.id AS document_id, documents.filename, documents.version, documents.content_hash, document_chunks.id AS chunk_id, document_chunks.ordinal, document_chunks.text AS excerpt, document_chunks.source_locator, document_chunks.embedding_json FROM document_chunks JOIN documents ON documents.id = document_chunks.document_id WHERE document_chunks.id IN ({placeholders}) AND documents.library_id = ? ORDER BY documents.created_at DESC, document_chunks.ordinal ASC",  # nosec B608
                            (*blocco, library_id),
                        ).fetchall()
                    )
            else:
                rows = []

        def _get(row, key):
            if isinstance(row, dict):
                return row.get(key)
            keys = [
                "document_id",
                "filename",
                "version",
                "content_hash",
                "chunk_id",
                "ordinal",
                "excerpt",
                "source_locator",
                "embedding_json",
            ]
            return row[keys.index(key)]

        rows = [r for r in rows if _get(r, "document_id") not in hidden]

        # Pesatura per rarita' del termine, calcolata sui candidati gia'
        # caricati: nessuno schema nuovo, nessuna cache da invalidare.
        #
        # Prima ogni termine valeva 10 punti, raro o comunissimo che fosse. Con
        # sedici passaggi non si notava; con testo vero attorno, l'astensione
        # passava da 1.000 a 0.333 (evaluation/scale_check.py).
        #
        # NOTA su una spiegazione sbagliata, scritta qui in un primo momento e
        # corretta il 10 settembre 2026: si diceva che la colpa fosse di
        # collisioni dello stemmer, "casa" contro "casi". E' falso — lo stemmer
        # taglia solo a/e finali oltre i quattro caratteri, quindi non tocca
        # nessuna delle due. Verificando quali termini producevano davvero la
        # corrispondenza sono risultati "sempre", "senza" e "mai": parole vuote
        # sopravvissute a _QUERY_STOPWORDS, piu' una polisemia reale ("codice"
        # etico contro "codice" sorgente).
        #
        # Un termine presente in quasi tutti i candidati non distingue niente e
        # ora pesa quasi zero; uno presente in pochi pesa quasi uno.
        preparati = []
        frequenza_documentale: dict[str, int] = {}
        termini_distinti = set(tokens)
        for row in rows:
            haystack = f"{_get(row, 'filename')} {_get(row, 'excerpt')}".lower()
            haystack_tokens = {self._search_token(t) for t in re.findall(r"[\wÀ-ÿ]{3,}", haystack)}
            preparati.append((row, haystack, haystack_tokens))
            for termine in termini_distinti:
                if termine in haystack_tokens:
                    frequenza_documentale[termine] = frequenza_documentale.get(termine, 0) + 1

        candidati = len(preparati)
        normalizzatore = math.log(1 + candidati) if candidati > 1 else 1.0

        def _peso(termine: str) -> float:
            df = frequenza_documentale.get(termine, 0)
            if df <= 0:
                return 0.0
            if candidati <= 1:
                return 1.0
            return math.log(1 + candidati / df) / normalizzatore

        ranked = []
        for row, haystack, haystack_tokens in preparati:
            filename, excerpt = _get(row, "filename"), _get(row, "excerpt")
            document_id = _get(row, "document_id")
            version = _get(row, "version")
            content_hash = _get(row, "content_hash")
            chunk_id = _get(row, "chunk_id")
            source_locator = _get(row, "source_locator")
            embedding_json = _get(row, "embedding_json")
            ordinal = _get(row, "ordinal")
            phrase_score = 100 if normalized.lower() in haystack else 0
            token_score = 10 * sum(_peso(t) for t in tokens if t in haystack_tokens)
            semantic_score = 0.0
            if query_embedding and embedding_json:
                try:
                    emb = json.loads(embedding_json) if isinstance(embedding_json, str) else embedding_json
                    semantic_score = max(0.0, cosine_similarity(query_embedding, emb))
                except (TypeError, ValueError):
                    semantic_score = 0.0
            if phrase_score or token_score or semantic_score >= min_semantic_score():
                ranked.append(
                    (
                        phrase_score + token_score + (semantic_score * 40),
                        {
                            "document_id": document_id,
                            "filename": filename,
                            "version": version,
                            "content_hash": content_hash,
                            "chunk_id": chunk_id,
                            "ordinal": ordinal,
                            "excerpt": excerpt,
                            "source_locator": source_locator,
                        },
                    )
                )
        ranked.sort(key=lambda item: (-item[0], item[1]["ordinal"]))
        target_limit = max(1, min(limit, 50))
        candidate_pool_size = (
            max(target_limit * 3, 20)
            if getattr(cfg, "RERANKER_ENABLED", True)
            else target_limit
        )
        results = [
            {
                **d,
                "relevance_score": round(s, 4),
                "citation": {
                    "document_id": d["document_id"],
                    "filename": d["filename"],
                    "version": d["version"],
                    "content_hash": f"sha256:{d['content_hash']}",
                    "chunk_id": d["chunk_id"],
                    "locator": d["source_locator"] or f"Passaggio {d['ordinal'] + 1}",
                },
            }
            for s, d in ranked[:candidate_pool_size]
        ]
        if getattr(cfg, "RERANKER_ENABLED", True) and results:
            from core.reranker import rerank_candidates

            results = rerank_candidates(query=normalized, candidates=results, limit=target_limit)
        else:
            results = results[:target_limit]
        profile = {
            "mode": "hybrid_local" if semantic_used else "keyword",
            "semantic_indexed_chunks": indexed_count,
            "semantic_used": semantic_used,
        }
        # Store in semantic cache (per-user scope, come sopra)
        cache.put(library_id, normalized, doc_count, results, profile, scope, generation=generation)
        return results, profile

    def search_federated(
        self,
        query: str,
        library_ids: list[str] | None = None,
        limit: int = 20,
        actor: dict | None = None,
    ) -> tuple[list[dict], dict]:
        """Performs cross-library federated semantic and keyword search.

        Discovers accessible libraries, executes multi-library retrieval,
        normalizes relevance scores, tags library provenance, and deduplicates
        overlapping chunks.
        """
        normalized = query.strip()
        if not normalized:
            return [], {
                "mode": "federated",
                "libraries_searched": 0,
                "libraries_matched": 0,
                "total_candidates": 0,
            }

        target_libraries: list[dict] = []
        if library_ids:
            for lid in library_ids:
                try:
                    lib = self.get_library(lid, actor=actor)
                    target_libraries.append(lib)
                except (LibraryNotFoundError, LibraryAccessError):
                    continue
        else:
            target_libraries = self.list_libraries(actor=actor)

        if not target_libraries:
            return [], {
                "mode": "federated",
                "libraries_searched": 0,
                "libraries_matched": 0,
                "total_candidates": 0,
            }

        all_citations: list[dict] = []
        libraries_with_matches: set[str] = set()

        for lib in target_libraries:
            lib_id = lib["id"]
            lib_name = lib["name"]
            try:
                citations, _ = self.search_with_profile(lib_id, normalized, limit=limit, actor=actor)
                for item in citations:
                    citation_copy = dict(item)
                    citation_dict = dict(citation_copy.get("citation", {}))
                    citation_dict["library_id"] = lib_id
                    citation_dict["library_name"] = lib_name
                    citation_copy["citation"] = citation_dict
                    citation_copy["library_id"] = lib_id
                    citation_copy["library_name"] = lib_name
                    all_citations.append(citation_copy)
                    libraries_with_matches.add(lib_id)
            except Exception as e:
                _logger.warning("Errore ricerca federata per libreria %s (%s): %s", lib_id, lib_name, e)

        # Deduplication based on content hash & ordinal or normalized excerpt
        seen_keys: set[str] = set()
        deduped_citations: list[dict] = []

        for item in sorted(all_citations, key=lambda x: x.get("relevance_score", 0.0), reverse=True):
            cit = item.get("citation", {})
            dedup_key = f"{cit.get('content_hash', '')}_{cit.get('document_id', '')}_{cit.get('chunk_id', '')}"
            if not cit.get("content_hash"):
                excerpt_snip = (item.get("excerpt", "") or "")[:100].strip().lower()
                dedup_key = f"{cit.get('filename', '')}_{excerpt_snip}"

            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            deduped_citations.append(item)

        final_citations = deduped_citations[:limit]
        profile = {
            "mode": "federated",
            "libraries_searched": len(target_libraries),
            "libraries_matched": len(libraries_with_matches),
            "total_candidates": len(all_citations),
        }
        return final_citations, profile
