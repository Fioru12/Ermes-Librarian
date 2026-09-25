"""Gruppi provisionati via SCIM 2.0 (risorsa /scim/v2/Groups).

Perche' esiste
--------------
L'accesso per gruppo c'era gia': un gruppo mappato su una biblioteca
(core/governance.py, set_oidc_group_mapping) concede viewer o editor ai suoi
membri. Ma i gruppi arrivavano solo dal claim `groups` del token OIDC: un
utente provisionato da SCIM che entrava con password o chiave API non ne
aveva nessuno, e l'identity provider non poteva sincronizzare le
appartenenze — l'unico modo per togliere l'accesso a chi cambia reparto era
modificarlo a mano in Ermes.

Qui l'identity provider (Entra ID, Okta) crea i gruppi e ne gestisce i
membri; `effective_groups()` unisce questi gruppi a quelli del token, e le
mappature esistenti gruppo -> biblioteca valgono per entrambi.

Il nome che conta e' `displayName`: e' quello che l'amministratore usa nelle
mappature, ed e' unico. L'`id` SCIM e' generato qui e serve solo al
protocollo.

Sull'archivio condiviso, come sessioni e tentativi di accesso: con piu'
repliche, togliere un utente da un gruppo deve valere su tutte.
"""

from __future__ import annotations

import datetime
import uuid

import config
from core.shared_backend import SharedTableStore


class ScimGroupStore(SharedTableStore):
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS scim_groups (
        id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS scim_group_members (
        group_id TEXT NOT NULL,
        username TEXT NOT NULL,
        PRIMARY KEY (group_id, username)
    )
    """

    _INDEXES = ("CREATE INDEX IF NOT EXISTS scim_group_members_by_user ON scim_group_members(username)",)

    # -- lettura -----------------------------------------------------------

    def get(self, group_id: str) -> dict | None:
        backend = self._connection()
        row = backend.execute_one("SELECT id, display_name, created_at FROM scim_groups WHERE id = ?", (group_id,))
        if row is None:
            return None
        return {**row, "members": self._members(group_id)}

    def find_by_display_name(self, display_name: str) -> dict | None:
        row = self._connection().execute_one("SELECT id FROM scim_groups WHERE display_name = ?", (display_name,))
        return self.get(row["id"]) if row else None

    def all(self) -> list[dict]:
        rows = self._connection().execute("SELECT id FROM scim_groups ORDER BY display_name")
        return [group for row in rows if (group := self.get(row["id"])) is not None]

    def _members(self, group_id: str) -> list[str]:
        rows = self._connection().execute(
            "SELECT username FROM scim_group_members WHERE group_id = ? ORDER BY username", (group_id,)
        )
        return [row["username"] for row in rows]

    def groups_for_user(self, username: str) -> list[str]:
        rows = self._connection().execute(
            """
            SELECT g.display_name FROM scim_groups g
            JOIN scim_group_members m ON m.group_id = g.id
            WHERE m.username = ?
            """,
            (username,),
        )
        return sorted(row["display_name"] for row in rows)

    # -- scrittura ---------------------------------------------------------

    def create(self, display_name: str, members: list[str]) -> dict:
        group_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.UTC).isoformat()
        self._connection().execute_write(
            "INSERT INTO scim_groups (id, display_name, created_at) VALUES (?, ?, ?)",
            (group_id, display_name, now),
        )
        self.add_members(group_id, members)
        return self.get(group_id) or {}

    def rename(self, group_id: str, display_name: str) -> None:
        self._connection().execute_write(
            "UPDATE scim_groups SET display_name = ? WHERE id = ?", (display_name, group_id)
        )

    def add_members(self, group_id: str, usernames: list[str]) -> None:
        if not usernames:
            return
        self._connection().executemany(
            """
            INSERT INTO scim_group_members (group_id, username) VALUES (?, ?)
            ON CONFLICT (group_id, username) DO NOTHING
            """,
            [(group_id, username) for username in dict.fromkeys(usernames)],
        )

    def remove_members(self, group_id: str, usernames: list[str]) -> None:
        if not usernames:
            return
        self._connection().executemany(
            "DELETE FROM scim_group_members WHERE group_id = ? AND username = ?",
            [(group_id, username) for username in usernames],
        )

    def replace_members(self, group_id: str, usernames: list[str]) -> None:
        self._connection().execute_write("DELETE FROM scim_group_members WHERE group_id = ?", (group_id,))
        self.add_members(group_id, usernames)

    def delete(self, group_id: str) -> bool:
        backend = self._connection()
        backend.execute_write("DELETE FROM scim_group_members WHERE group_id = ?", (group_id,))
        return backend.execute_write("DELETE FROM scim_groups WHERE id = ?", (group_id,)) > 0

    def remove_user_everywhere(self, username: str) -> None:
        """Da chiamare quando l'utente viene eliminato."""
        self._connection().execute_write("DELETE FROM scim_group_members WHERE username = ?", (username,))

    def clear(self) -> None:
        backend = self._connection()
        backend.execute_write("DELETE FROM scim_group_members")
        backend.execute_write("DELETE FROM scim_groups")


scim_group_store = ScimGroupStore()


def effective_groups(actor: dict | None) -> list[str]:
    """Gruppi dell'utente: quelli del token OIDC piu' quelli provisionati via SCIM.

    I gruppi del token valgono solo per identita' OIDC (un token locale non
    porta claim verificati). Quelli SCIM valgono per qualunque via d'accesso,
    perche' li ha stabiliti l'identity provider, non il client.
    """
    if not actor or not actor.get("username"):
        return []
    groups: set[str] = set()
    if actor.get("provider") == "oidc":
        groups.update(str(g) for g in actor.get("groups") or [] if g)
    if config.cfg.SCIM_ENABLED:
        groups.update(scim_group_store.groups_for_user(str(actor["username"])))
    return sorted(groups)
