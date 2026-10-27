"""Base class of the library store: database access, access rules, libraries and members."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.database_backend import SqliteBackend
from core.library_store.common import LibraryAccessError, LibraryNotFoundError, _resolve_backend
from core.library_store.schema import initialize_sqlite_schema


class StoreBase:
    """Infrastructure, library access rules and library/member management."""

    def __init__(self, database_path: str | Path | None = None, database_url: str | None = None) -> None:
        self._lock = threading.RLock()
        self._backend = _resolve_backend(database_path, database_url)
        self._is_postgres = self._backend.__class__.__name__ == "PostgresBackend"
        self._initialize()

    @property
    def database_path(self) -> Path:
        if isinstance(self._backend, SqliteBackend):
            return Path(self._backend._path)
        return Path(".")

    def _exec(self, sql: str, params: tuple | dict | None = None) -> list[dict]:
        """Esegui una query SELECT e ritorna tutte le righe."""
        return self._backend.execute(sql, params)

    def _exec_one(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        """Esegui una query SELECT e ritorna la prima riga."""
        return self._backend.execute_one(sql, params)

    def _exec_write(self, sql: str, params: tuple | dict | None = None) -> int:
        """Esegui INSERT/UPDATE/DELETE e ritorna il rowcount."""
        return self._backend.execute_write(sql, params)

    def _exec_returning(self, sql: str, params: tuple | dict | None = None) -> dict | None:
        """Esegui INSERT/UPDATE/DELETE ... RETURNING e ritorna la riga."""
        return self._backend.execute_returning(sql, params)

    @contextmanager
    def _connection(self):
        """Context manager legacy: delega al backend transaction().

        Mantiene la signature storica per i pochi chiamatori che fanno
        `with self._connection() as connection: connection.execute(...)`.
        SQLite: restituisce la connessione cruda (sqlite3.Row, accesso per nome).
        Postgres: restituisce un adapter dict-based.
        """
        with self._backend.transaction() as connection:
            yield connection

    def _initialize(self) -> None:
        if self._is_postgres:
            self._initialize_postgres()
        else:
            self._initialize_sqlite()

    def _initialize_postgres(self) -> None:
        """Inizializza lo schema PostgreSQL usando il DDL di postgres_backend."""
        from core.postgres_backend import POSTGRES_SCHEMA

        self._backend.execute_script(POSTGRES_SCHEMA)

    def _initialize_sqlite(self) -> None:
        """Inizializza lo schema SQLite (comportamento storico)."""
        with self._lock, self._connection() as connection:
            initialize_sqlite_schema(connection)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _row(row: sqlite3.Row | dict | Any) -> dict:
        return dict(row)

    @staticmethod
    def _search_token(token: str) -> str:
        """Small deterministic Italian-friendly normalization for MVP search.

        It deliberately is not a linguistic model; trimming a terminal ``a``/
        ``e`` avoids missing obvious feminine singular/plural forms such as
        ``richiesta`` / ``richieste`` while semantic retrieval remains an
        optional later ranking signal.

        Found in review: trimming *any* trailing vowel (the original ``in
        "aeiou"`` check) collapsed unrelated words that merely happen to end
        in different vowels onto the same stem — ``lavora`` (verb, "works")
        and ``lavoro`` (noun, "job") both became ``lavor``, causing a
        false-positive match on an abstention query that should have found
        nothing. Restricting the trim to ``a``/``e`` keeps the one pairing
        this heuristic is actually meant for (feminine singular/plural) while
        no longer touching ``-o``/``-i``/``-u`` endings, which is where the
        verb/noun collisions come from.
        """
        normalized = token.lower()
        return normalized[:-1] if len(normalized) > 4 and normalized[-1] in "ae" else normalized

    @staticmethod
    def _can_access(library: dict, actor: dict | None, write: bool = False, member_role: str | None = None) -> bool:
        if actor is None:
            return True
        if actor.get("role") == "admin":
            return True
        if library.get("owner_id") == actor.get("username"):
            return True
        if member_role in {"editor", "manager"}:
            return True
        if member_role in {"viewer", "reviewer"} and not write:
            return True
        return library.get("visibility") == "shared" and not write


    def _membership_roles(self, username: str) -> dict[str, str]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT library_id, role FROM library_members WHERE username = ?", (username,)
            ).fetchall()
        return {row["library_id"]: row["role"] for row in rows}

    def _membership_role(self, library_id: str, username: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT role FROM library_members WHERE library_id = ? AND username = ?", (library_id, username)
            ).fetchone()
        return row["role"] if row else None

    @staticmethod
    def _effective_member_role(
        direct_role: str | None, library_id: str, actor: dict | None, groups: list[str] | None = None
    ) -> str | None:
        """Ruolo efficace = max(membership diretta, gruppi mappati).

        I gruppi vengono dal token OIDC e dal provisioning SCIM
        (core/scim_groups.py::effective_groups). Non possono mai degradare una
        membership esplicita: se il proprietario ha dato editor a un utente,
        resta editor anche se il suo gruppo mappa solo viewer. Il valore admin
        non deriva mai dai gruppi (solo dai ruoli del token o da account
        espliciti). `groups` si passa gia' calcolato quando si valutano molte
        biblioteche per lo stesso utente, per non rileggerli a ogni biblioteca.
        """
        if actor is None:
            return direct_role
        if groups is None:
            from core.scim_groups import effective_groups

            groups = effective_groups(actor)
        if not groups:
            return direct_role
        from core.governance import resolve_oidc_group_role

        group_role = resolve_oidc_group_role(groups, library_id)
        if group_role is None:
            return direct_role
        hierarchy = {"manager": 4, "editor": 3, "reviewer": 2, "viewer": 1}
        d_rank = hierarchy.get(direct_role or "", 0)
        g_rank = hierarchy.get(group_role or "", 0)
        return direct_role if d_rank >= g_rank else group_role

    @staticmethod
    def _can_manage_members(library: dict, actor: dict | None, member_role: str | None = None) -> bool:
        if not actor:
            return False
        if actor.get("role") == "admin" or library.get("owner_id") == actor.get("username"):
            return True
        effective = member_role or library.get("access_role")
        return effective == "manager"

    @classmethod
    def _access_role(cls, library: dict, actor: dict | None, member_role: str | None = None) -> str:
        """Return the effective library role without trusting the client UI."""
        if actor is None:
            return "system"
        if actor.get("role") == "admin":
            return "admin"
        if library.get("owner_id") == actor.get("username"):
            return "owner"
        if member_role in {"viewer", "reviewer", "editor", "manager"}:
            return member_role
        return "viewer" if library.get("visibility") == "shared" else "none"


    def list_libraries(self, actor: dict | None = None) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT libraries.*, COUNT(documents.id) AS document_count
                FROM libraries
                LEFT JOIN documents ON documents.library_id = libraries.id
                GROUP BY libraries.id
                ORDER BY libraries.created_at DESC
                """
            ).fetchall()
        memberships = self._membership_roles(actor["username"]) if actor and actor.get("role") != "admin" else {}
        # Propagazione ACL: le biblioteche raggiungibili SOLO via gruppi (token
        # OIDC o provisioning SCIM) appaiono nell'elenco anche senza
        # membership diretta.
        group_roles: dict[str, str] = {}
        groups: list[str] = []
        if actor and actor.get("role") != "admin":
            from core.governance import oidc_group_roles_for_user
            from core.scim_groups import effective_groups

            groups = effective_groups(actor)
            group_roles = oidc_group_roles_for_user(groups)
        visible: list[dict] = []
        for row in rows:
            library = self._row(row)
            member_role = memberships.get(library["id"])
            effective_role = self._effective_member_role(member_role, library["id"], actor, groups=groups)
            if group_roles.get(library["id"]) and effective_role is None:
                effective_role = group_roles[library["id"]]
            if self._can_access(library, actor, member_role=member_role) or (
                effective_role is not None and library["id"] in group_roles
            ):
                library["access_role"] = self._access_role(library, actor, effective_role)
                visible.append(library)
        return visible

    def create_library(
        self, name: str, description: str = "", visibility: str = "private", owner_id: str = "system"
    ) -> dict:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Il nome della biblioteca è obbligatorio.")
        if len(normalized_name) > 120:
            raise ValueError("Il nome della biblioteca può contenere al massimo 120 caratteri.")
        if visibility not in {"private", "shared"}:
            raise ValueError("La visibilità deve essere 'private' o 'shared'.")

        now = self._timestamp()
        library = {
            "id": str(uuid.uuid4()),
            "name": normalized_name,
            "description": description.strip()[:500],
            "visibility": visibility,
            # Cloud generation is opt-in per library, even if an instance has
            # credentials configured for it.
            "assistant_mode": "evidence_only",
            "assistant_provider": "",
            "owner_id": owner_id,
            "created_at": now,
            "updated_at": now,
            "document_count": 0,
        }
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO libraries (id, name, description, visibility, assistant_mode, assistant_provider, owner_id, created_at, updated_at)
                VALUES (:id, :name, :description, :visibility, :assistant_mode, :assistant_provider, :owner_id, :created_at, :updated_at)
                """,
                library,
            )
        return library

    def set_assistant_mode(self, library_id: str, mode: str) -> dict:
        """Backward-compatible shortcut for a policy without named provider."""
        return self.set_assistant_policy(library_id, mode)

    def set_assistant_policy(self, library_id: str, mode: str, provider_name: str = "") -> dict:
        """Persist one explicit per-library generation and egress policy."""
        if mode not in {"evidence_only", "local_ollama", "approved_openrouter", "approved_provider"}:
            raise ValueError("Modalita assistente non valida.")
        provider_name = provider_name.strip()
        if mode == "approved_provider" and not provider_name:
            raise ValueError("Seleziona un provider approvato.")
        if mode != "approved_provider":
            provider_name = ""
        now = self._timestamp()
        with self._lock, self._connection() as connection:
            updated = connection.execute(
                "UPDATE libraries SET assistant_mode = ?, assistant_provider = ?, updated_at = ? WHERE id = ?",
                (mode, provider_name, now, library_id),
            ).rowcount
        if not updated:
            raise LibraryNotFoundError(library_id)
        return self.get_library(library_id)

    def get_library(self, library_id: str, actor: dict | None = None, write: bool = False) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT libraries.*, COUNT(documents.id) AS document_count,
                       COALESCE(
                           (SELECT g.generation FROM search_cache_generations g WHERE g.library_id = libraries.id), 0
                       ) AS cache_generation
                FROM libraries
                LEFT JOIN documents ON documents.library_id = libraries.id
                WHERE libraries.id = ?
                GROUP BY libraries.id
                """,
                (library_id,),
            ).fetchone()
        if row is None:
            raise LibraryNotFoundError(library_id)
        library = self._row(row)
        member_role = (
            self._membership_role(library_id, actor["username"]) if actor and actor.get("role") != "admin" else None
        )
        member_role = self._effective_member_role(member_role, library_id, actor)
        if not self._can_access(library, actor, write, member_role):
            raise LibraryAccessError(library_id)
        library["access_role"] = self._access_role(library, actor, member_role)
        return library

    def list_library_members(self, library_id: str) -> list[dict]:
        library = self.get_library(library_id)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT username, role, created_at, updated_at FROM library_members WHERE library_id = ? ORDER BY username",
                (library_id,),
            ).fetchall()
        return [
            {
                "username": library["owner_id"],
                "role": "owner",
                "created_at": library["created_at"],
                "updated_at": library["updated_at"],
            },
            *[self._row(row) for row in rows],
        ]

    def set_library_member(self, library_id: str, username: str, role: str) -> dict:
        self.get_library(library_id)
        normalized_username = username.strip()
        if not normalized_username:
            raise ValueError("Utente collaboratore obbligatorio")
        if role not in {"viewer", "reviewer", "editor", "manager"}:
            raise ValueError("Ruolo collaboratore non valido")
        library = self.get_library(library_id)
        if normalized_username == library["owner_id"]:
            raise ValueError("Il proprietario non puo essere aggiunto come collaboratore")
        now = self._timestamp()
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO library_members (library_id, username, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(library_id, username) DO UPDATE SET role = excluded.role, updated_at = excluded.updated_at
                """,
                (library_id, normalized_username, role, now, now),
            )
        return {"username": normalized_username, "role": role}

    def remove_library_member(self, library_id: str, username: str) -> bool:
        with self._lock, self._connection() as connection:
            deleted = connection.execute(
                "DELETE FROM library_members WHERE library_id = ? AND username = ?", (library_id, username.strip())
            ).rowcount
        return bool(deleted)

    def can_manage_library_members(self, library_id: str, actor: dict | None) -> bool:
        library = self.get_library(library_id, actor)
        return self._can_manage_members(library, actor, library.get("access_role"))

    @staticmethod
    def _bump_cache_generation(connection, library_id: str) -> None:
        """Da chiamare dentro la transazione che modifica documenti o permessi.

        Invalida la cache di ricerca su tutte le repliche, non solo su quella
        che serve la richiesta: vedi core/search_cache.py. Nella stessa
        transazione, quindi senza connessioni ne' commit in piu'.
        """
        connection.execute(
            """
            INSERT INTO search_cache_generations (library_id, generation) VALUES (?, 1)
            ON CONFLICT (library_id) DO UPDATE SET generation = search_cache_generations.generation + 1
            """,
            (library_id,),
        )

    @staticmethod
    def _actor_bypasses_document_acl(library: dict, actor: dict | None) -> bool:
        """Admin e proprietario vedono sempre tutto; None e' il sistema."""
        return actor is None or actor.get("role") == "admin" or library.get("owner_id") == actor.get("username")

    def _hidden_document_ids(self, connection: sqlite3.Connection, library: dict, actor: dict | None) -> set[str]:
        if self._actor_bypasses_document_acl(library, actor):
            return set()
        rows = connection.execute(
            """
            SELECT DISTINCT d.id
            FROM documents d
            JOIN document_acls a ON a.document_id = d.id
            WHERE d.library_id = ?
              AND d.id NOT IN (SELECT document_id FROM document_acls WHERE username = ?)
            """,
            (library["id"], actor["username"] if actor else ""),
        ).fetchall()
        return {row["id"] for row in rows}


    def _library_owner(self, library_id: str) -> str:
        with self._connection() as connection:
            row = connection.execute("SELECT owner_id FROM libraries WHERE id = ?", (library_id,)).fetchone()
        return row["owner_id"] if row else ""
