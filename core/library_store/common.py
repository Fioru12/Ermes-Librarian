"""Shared constants, errors and storage-path helpers of the library store."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from config import cfg
from core.database_backend import Backend, SqliteBackend, create_backend

_logger = logging.getLogger(__name__)


def _resolve_backend(database_path: str | Path | None, database_url: str | None = None) -> Backend:
    """Scegli il backend: URL esplicito, altrimenti ERMES_DATABASE_URL, altrimenti il path SQLite.

    `database_url` esiste perche' `cfg` e' un frozen dataclass costruito
    all'import: un test che imposta ERMES_DATABASE_URL nell'ambiente dopo
    l'import non cambia `cfg.DATABASE_URL`, e ottiene SQLite credendo di
    avere Postgres. E' successo per mesi ai test di parita'.
    """
    if database_url:
        esplicito: Backend = create_backend(database_url)
        return esplicito
    if database_path is not None:
        return SqliteBackend(str(database_path))
    backend: Backend = create_backend(cfg.DATABASE_URL)
    return backend

# Massimo numero di segnaposto per interrogazione. SQLite ne accetta 32766
# nelle build recenti e 999 in quelle storiche: 900 e' sotto entrambi.
_MAX_SQL_VARIABILI = 900

# Candidati lessicali per interrogazione, scelti dal ranking full-text del
# database prima del punteggio in Python. Sui corpus di valutazione (fino a
# 404 passaggi) non viene mai raggiunto, quindi i numeri pubblicati non
# cambiano; su un archivio grande taglia la coda dei candidati irrilevanti.
_MAX_KEYWORD_CANDIDATES = 1000


# Common function words must not become the only "evidence" for a RAG answer.
# This compact local-first baseline deliberately keeps a conservative bilingual
# list; a production language analyser can replace it behind this same method.
#
# Le dieci parole in coda sono state aggiunte il 10 settembre 2026 dopo una
# misura. Con un corpus contenente altro testo, alla domanda "un collega lavora
# sempre da casa senza mai venire in sede" il sistema citava un paragrafo
# tecnico qualunque, perche' condivideva "sempre", "senza" e "mai": tre parole
# vuote bastavano a superare la regola di ammissione. Un ampliamento piu' esteso
# (una lista completa di funzionali italiani) e' stato provato e scartato:
# recuperava 0.037 di recall sul corpus grande e ne perdeva 0.125 sulle
# parafrasi di quello pulito.
_QUERY_STOPWORDS = {
    "sempre",
    "mai",
    "senza",
    "succede",
    "anche",
    "ancora",
    "ogni",
    "tutti",
    "deve",
    "essere",
    "a",
    "ad",
    "al",
    "alla",
    "alle",
    "che",
    "chi",
    "come",
    "con",
    "cosa",
    "dei",
    "del",
    "della",
    "delle",
    "di",
    "dove",
    "e",
    "gli",
    "i",
    "il",
    "in",
    "la",
    "le",
    "lo",
    "nei",
    "nelle",
    "per",
    "quali",
    "quando",
    "quale",
    "sono",
    "sul",
    "sulla",
    "the",
    "and",
    "are",
    "before",
    "for",
    "from",
    "how",
    "is",
    "it",
    "of",
    "on",
    "or",
    "to",
    "was",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "your",
    "document",
    "documents",
    "documenti",
    "library",
    "biblioteca",
    "policy",
    "procedure",
}


def storage_relative_path(library_id: str, stored_filename: str) -> str:
    """Location to record for a document, relative to the storage root.

    Absolute paths must never be written: the database would stop being
    portable. A library moved into a container, restored from backup into a
    different directory, or copied to another machine would keep pointing at
    the ingesting machine's filesystem, and every original would become
    unreachable while the rows still looked healthy.
    """
    return f"{library_id}/{stored_filename}"


def resolve_storage_path(stored: str, storage_root: str | Path) -> Path:
    """Resolve a recorded document location against the current storage root.

    Handles three cases: a relative path (what is written now), an absolute
    path that still resolves (same machine, same layout), and an absolute path
    written by another machine — including a Windows path seen from Linux,
    where the whole string is a single POSIX component. The last case is
    re-anchored under the current root by its final two segments, which is the
    `<library_id>/<stored filename>` layout every writer produces.

    The caller must still confirm the result stays inside the storage root:
    this function locates a file, it does not authorise reading it.
    """
    root = Path(storage_root)
    segments = [s for s in stored.replace("\\", "/").split("/") if s not in ("", ".")]
    looks_absolute = stored.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", stored)

    if not looks_absolute:
        return root.joinpath(*segments) if segments else root

    candidate = Path(stored)
    try:
        if candidate.is_file():
            return candidate
    except OSError:
        # Probing a path outside the storage root can fail rather than return
        # False — on Linux, stat() of an unreadable location raises
        # PermissionError. Treat any such failure as "not usable here" and fall
        # through to re-anchoring, instead of letting it reach the caller.
        pass
    if len(segments) >= 2:
        return root / segments[-2] / segments[-1]
    return candidate


class LibraryNotFoundError(KeyError):
    """Raised when a requested library does not exist."""


class LibraryAccessError(PermissionError):
    """Raised when a user cannot access a private library."""
