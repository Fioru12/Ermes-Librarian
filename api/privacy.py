"""Diritti dell'interessato: accesso e cancellazione dei dati di un account.

Fino all'11 settembre 2026 il threat model e la tesina dichiaravano questi due
adempimenti come mancanti. Qui ci sono, con una regola chiara su cosa si
cancella, cosa si anonimizza e cosa si conserva — e perche'.

Si cancella: l'account locale, le chiavi API, le sessioni, le appartenenze
alle biblioteche, le ACL sui documenti, gli eventi analitici (che contengono
le domande scritte dalla persona).

Si anonimizza (passa all'amministratore che esegue): la proprieta' delle
biblioteche, le integrazioni di chat e le sorgenti cartella registrate. Non
sono dati personali: sono documenti e configurazioni dell'organizzazione, che
continuano a servire ad altri.

Si conserva, dichiarandolo nella risposta: le voci del log di audit di cui la
persona e' autrice. Il log e' un registro di sicurezza tenuto per obbligo,
ogni voce e' firmata e la firma copre il campo dell'autore: pseudonimizzarlo
renderebbe la voce indistinguibile da una manomessa. E' l'eccezione dell'art.
17(3)(b), e l'esportazione le include perche' il diritto di accesso invece le
copre.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from api.auth import _require_role, _verify_api_key, session_store
from api.libraries import get_library_store
from config import cfg
from core.analytics import erase_user_events, export_user_events
from core.governance import (
    append_audit,
    audit_entries_for,
    delete_user,
    list_api_keys,
    list_users,
    revoke_user_api_key,
)
from core.library_store import LibraryStore

router = APIRouter(prefix="/api/privacy", tags=["Privacy (GDPR)"])


def _account(username: str) -> dict | None:
    return next((u for u in list_users(cfg.USERS_FILE) if u["username"] == username), None)


def _chiavi_api(username: str) -> list[dict]:
    return [
        {chiave: valore for chiave, valore in voce.items() if chiave in ("username", "role", "created_at")}
        for voce in list_api_keys()
        if voce.get("username") == username
    ]


@router.get("/users/{username}/export", summary="Esporta tutti i dati riferibili a un account (art. 15)")
def export_user_data(
    username: str,
    _auth: dict = Depends(_verify_api_key),
    store: LibraryStore = Depends(get_library_store),
):
    # La persona puo' chiedere i propri dati; per quelli altrui serve un
    # amministratore. 404 e non 403 nel secondo caso: non si conferma
    # l'esistenza di un account a chi non puo' vederlo.
    if _auth.get("role") != "admin" and _auth.get("username") != username:
        raise HTTPException(status_code=404, detail="Account non trovato")

    account = _account(username)
    chiavi = _chiavi_api(username)
    impronta = store.user_footprint(username)
    eventi = export_user_events(username)
    audit = audit_entries_for(cfg.AUDIT_FILE, username)
    if not (account or chiavi or eventi or audit or any(impronta.values())):
        raise HTTPException(status_code=404, detail="Account non trovato")

    append_audit(cfg.AUDIT_FILE, "privacy_export", _auth["username"], {"subject": username})
    return {
        "subject": username,
        "exported_at": datetime.now(UTC).isoformat(),
        "account": account,
        "api_keys": chiavi,
        "libraries": impronta,
        "analytics_events": eventi,
        "audit_entries": audit,
        "notes": [
            "Le voci di audit sono incluse per il diritto di accesso ma non vengono cancellate con l'account: "
            "sono un registro di sicurezza conservato per obbligo e firmato per voce (art. 17(3)(b)).",
            "I documenti non registrano chi li ha caricati e non sono dati personali di chi li ha caricati.",
        ],
    }


@router.delete("/users/{username}", summary="Cancella i dati di un account (art. 17)")
def erase_user_data(
    username: str,
    _auth: dict = Depends(_require_role("admin")),
    store: LibraryStore = Depends(get_library_store),
):
    esecutore = str(_auth.get("username", ""))
    if username == esecutore:
        raise HTTPException(status_code=409, detail="Un amministratore non puo' cancellare il proprio account da qui")
    if username == cfg.ADMIN_USERNAME:
        raise HTTPException(
            status_code=409,
            detail="L'account amministrativo configurato in ERMES_ADMIN_USERNAME non si cancella: cambia prima la configurazione",
        )

    esisteva = _account(username) is not None or bool(_chiavi_api(username))
    impronta_prima = store.user_footprint(username)
    if not (esisteva or any(impronta_prima.values()) or export_user_events(username)):
        raise HTTPException(status_code=404, detail="Account non trovato")

    cancellato: dict[str, object] = {
        "account": delete_user(cfg.USERS_FILE, username),
        "api_key": revoke_user_api_key(username),
        "sessions": session_store.delete_for_user(username),
        "analytics_events": erase_user_events(username),
    }
    cancellato.update(store.erase_user(username, reassign_to=esecutore))
    rapporto = {
        "subject": username,
        "erased_at": datetime.now(UTC).isoformat(),
        "erased": cancellato,
        "reassigned_to": esecutore,
        "retained": {
            "audit_entries": len(audit_entries_for(cfg.AUDIT_FILE, username)),
            "reason": "registro di sicurezza conservato per obbligo, firmato per voce (art. 17(3)(b))",
        },
    }

    append_audit(cfg.AUDIT_FILE, "privacy_erase", esecutore, {"subject": username, "report": cancellato})
    return rapporto
