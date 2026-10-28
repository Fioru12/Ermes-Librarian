"""Importazione di un documento arrivato da un connettore, con i permessi dell'origine.

Prima del 28 ottobre 2026 lo stesso ciclo era scritto quattro volte (sync
completa e incrementale dell'API, e le due dello scheduler) e nessuna delle
quattro guardava chi potesse vedere il file sull'origine: un documento che
su SharePoint vedevano in tre diventava visibile a tutta la biblioteca.

Regole dei permessi
-------------------
- ``RemoteDocument.allowed_principals is None``: il connettore non sa (o
  l'origine dice "tutti", come un link aperto all'organizzazione). Il
  documento segue le regole della biblioteca, come un caricamento manuale.
- Altrimenti e' l'elenco di chi lo vede sull'origine (email, ``DOMINIO\\utente``
  o nomi utente). Diventa la allow-list per documento gia' esistente
  (``document_acls``): un nome si abbina a un utente Ermes senza distinguere
  maiuscole, e ``DOMINIO\\utente`` vale ``utente``. Chi non e' ancora un
  utente Ermes resta nell'elenco: e' cosi' che gli utenti SSO, creati al
  primo accesso, ritrovano i loro documenti.
- Elenco vuoto o permessi illeggibili: il documento resta visibile solo al
  proprietario della biblioteca e agli amministratori. Un permesso che non si
  riesce a tradurre chiude, non apre.
- I permessi si scrivono nella stessa transazione del documento: non c'e'
  un istante in cui un file riservato e' aperto a tutta la biblioteca.
- Un file gia' importato (stesso contenuto) riceve comunque i permessi
  attuali: un accesso tolto sull'origine sparisce alla sincronizzazione
  successiva anche se il file non e' cambiato.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from core.connectors.base import RemoteDocument
from core.document_parser import extract_source_units
from core.library_store import LibraryStore, storage_relative_path

_logger = logging.getLogger(__name__)


def _known_usernames() -> dict[str, str]:
    """Nomi degli account locali, per restituire la grafia esatta di Ermes."""
    try:
        from config import cfg
        from core.governance import list_users

        return {str(u["username"]).lower(): str(u["username"]) for u in list_users(cfg.USERS_FILE) if u.get("username")}
    except Exception as error:  # l'elenco serve solo alla grafia: senza, si usa il nome dell'origine
        _logger.warning("Elenco utenti non leggibile per i permessi dei connettori: %s", error)
        return {}


def resolve_principals(principals: tuple[str, ...] | list[str], known: dict[str, str]) -> list[str]:
    """Traduce i nomi dell'origine in nomi utente Ermes."""
    resolved = set()
    for principal in principals:
        name = str(principal or "").strip()
        if "\\" in name:
            name = name.rsplit("\\", 1)[1]
        if name:
            resolved.add(known.get(name.lower(), name))
    return sorted(resolved)


def source_allow_list(store: LibraryStore, library_id: str, document: RemoteDocument) -> list[str] | None:
    """La allow-list per il documento, None se segue le regole della biblioteca."""
    if document.allowed_principals is None:
        return None
    users = resolve_principals(document.allowed_principals, _known_usernames())
    if users:
        return users
    _logger.warning(
        "Permessi di %s non traducibili: visibile solo al proprietario della biblioteca e agli amministratori",
        document.name,
    )
    owner = str(store.get_library(library_id).get("owner_id", "") or "")
    # Il proprietario vede comunque i documenti della sua biblioteca: basta
    # che l'elenco non sia vuoto, perche' un elenco vuoto toglie il vincolo.
    return [owner or "-"]


def import_remote_document(
    store: LibraryStore,
    library_id: str,
    document: RemoteDocument,
    hash_index: dict[str, str],
    storage_provider: Any,
) -> str:
    """Importa un documento remoto. Restituisce "imported" o "duplicate".

    `hash_index` (impronta del contenuto -> id del documento) viene aggiornato,
    cosi' lo stesso file presente due volte nella stessa sincronizzazione
    viene importato una volta sola.
    """
    allow_list = source_allow_list(store, library_id, document)
    digest = hashlib.sha256(document.content).hexdigest()
    existing = hash_index.get(digest)
    if existing:
        if allow_list is not None:
            store.set_document_acl(library_id, existing, allow_list)
        return "duplicate"

    units = extract_source_units(document.name, document.content)
    chunks = [(unit.text, unit.locator) for unit in units]
    if not chunks or not chunks[0][0]:
        chunks = [(document.name, "Titolo")]

    stored_rel = storage_relative_path(library_id, f"{digest[:12]}_{document.name}")
    storage_provider.save(stored_rel, document.content)
    created = store.add_document(
        library_id=library_id,
        filename=document.name,
        media_type=document.media_type,
        content=document.content,
        storage_path=stored_rel,
        status="ready",
        chunks=chunks,
        allowed_usernames=allow_list,
    )
    hash_index[digest] = created["id"]
    return "imported"
