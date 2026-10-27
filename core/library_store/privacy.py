"""Personal data held by the store (GDPR access and erasure)."""

from __future__ import annotations

from core.library_store.base import StoreBase


class PrivacyMixin(StoreBase):
    # ------------------------------------------------------------------
    # Dati riferibili a una persona (GDPR: accesso e cancellazione)
    # ------------------------------------------------------------------

    def user_footprint(self, username: str) -> dict:
        """Tutto cio' che in questo archivio fa riferimento a un nome utente.

        Serve al diritto di accesso (art. 15) e a decidere cosa cancellare o
        anonimizzare (art. 17). I documenti non registrano chi li ha caricati,
        quindi non compaiono: non sono dati personali di chi li ha caricati.
        Usa i wrapper del backend, cosi' vale anche su PostgreSQL.
        """
        return {
            "owned_libraries": self._exec(
                "SELECT id, name, visibility, created_at FROM libraries WHERE owner_id = ? ORDER BY created_at",
                (username,),
            ),
            "memberships": self._exec(
                "SELECT library_id, role, created_at FROM library_members WHERE username = ? ORDER BY created_at",
                (username,),
            ),
            "document_acls": self._exec(
                "SELECT document_id, created_at FROM document_acls WHERE username = ? ORDER BY created_at",
                (username,),
            ),
            "chat_integrations_created": self._exec(
                "SELECT id, library_id, platform, created_at FROM chat_integrations WHERE created_by = ?",
                (username,),
            ),
            "import_sources_created": self._exec(
                "SELECT id, library_id, path, created_at FROM import_sources WHERE created_by = ?",
                (username,),
            ),
        }

    def erase_user(self, username: str, reassign_to: str) -> dict:
        """Cancella o anonimizza ogni riferimento a `username`.

        Cancellare le biblioteche di cui la persona e' proprietaria non e'
        cancellare i suoi dati: sono documenti dell'organizzazione, che
        continuano a servire ad altri. La proprieta' passa a `reassign_to`
        (l'amministratore che esegue l'operazione), e lo stesso vale per le
        integrazioni e le sorgenti che aveva registrato. Appartenenze e ACL
        sono invece diritti personali, e vengono rimossi.
        """
        with self._lock:
            return {
                "libraries_reassigned": self._exec_write(
                    "UPDATE libraries SET owner_id = ? WHERE owner_id = ?", (reassign_to, username)
                ),
                "memberships_removed": self._exec_write("DELETE FROM library_members WHERE username = ?", (username,)),
                "document_acls_removed": self._exec_write("DELETE FROM document_acls WHERE username = ?", (username,)),
                "chat_integrations_reassigned": self._exec_write(
                    "UPDATE chat_integrations SET created_by = ? WHERE created_by = ?", (reassign_to, username)
                ),
                "import_sources_reassigned": self._exec_write(
                    "UPDATE import_sources SET created_by = ? WHERE created_by = ?", (reassign_to, username)
                ),
            }
