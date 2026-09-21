"""Persistenza delle conversazioni chat su archivio condiviso.

Permette sessioni multi-conversazione persistenti per ciascun utente,
compatibili sia con SQLite sia con PostgreSQL grazie a `SharedTableStore`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from core.shared_backend import SharedTableStore

_logger = logging.getLogger(__name__)

_CONVERSATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_conversations (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    library_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);
"""

_CONVERSATIONS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_chat_conversations_user ON chat_conversations(username, library_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_conv ON chat_messages(conversation_id, created_at ASC)",
)


class ConversationStore(SharedTableStore):
    """Gestione conversazioni e cronologia messaggi."""

    _SCHEMA = _CONVERSATIONS_SCHEMA
    _INDEXES = _CONVERSATIONS_INDEXES

    def create_conversation(
        self,
        username: str,
        library_id: str,
        title: str = "Nuova conversazione",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        cid = conversation_id or uuid.uuid4().hex
        now = time.time()
        backend = self._connection()
        backend.execute_write(
            "INSERT INTO chat_conversations (id, username, library_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cid, str(username), str(library_id), str(title).strip() or "Nuova conversazione", now, now),
        )
        backend.commit()
        return {
            "id": cid,
            "username": username,
            "library_id": library_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }

    def list_conversations(
        self,
        username: str,
        library_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        backend = self._connection()
        if library_id:
            rows = backend.execute(
                "SELECT id, username, library_id, title, created_at, updated_at "
                "FROM chat_conversations "
                "WHERE username = ? AND library_id = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (str(username), str(library_id), max(1, int(limit))),
            )
        else:
            rows = backend.execute(
                "SELECT id, username, library_id, title, created_at, updated_at "
                "FROM chat_conversations "
                "WHERE username = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (str(username), max(1, int(limit))),
            )
        return [
            {
                "id": str(r["id"]),
                "username": str(r["username"]),
                "library_id": str(r["library_id"]),
                "title": str(r["title"]),
                "created_at": float(r["created_at"]),
                "updated_at": float(r["updated_at"]),
            }
            for r in rows
        ]

    def get_conversation(
        self,
        conversation_id: str,
        username: str | None = None,
    ) -> dict[str, Any] | None:
        backend = self._connection()
        if username:
            row = backend.execute_one(
                "SELECT id, username, library_id, title, created_at, updated_at "
                "FROM chat_conversations WHERE id = ? AND username = ?",
                (str(conversation_id), str(username)),
            )
        else:
            row = backend.execute_one(
                "SELECT id, username, library_id, title, created_at, updated_at "
                "FROM chat_conversations WHERE id = ?",
                (str(conversation_id),),
            )
        if not row:
            return None

        msg_rows = backend.execute(
            "SELECT id, conversation_id, role, content, citations_json, created_at "
            "FROM chat_messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (str(conversation_id),),
        )

        messages = []
        for m in msg_rows:
            citations = []
            if m["citations_json"]:
                try:
                    citations = json.loads(m["citations_json"])
                except Exception:
                    citations = []
            messages.append(
                {
                    "id": str(m["id"]),
                    "conversation_id": str(m["conversation_id"]),
                    "role": str(m["role"]),
                    "content": str(m["content"]),
                    "citations": citations if isinstance(citations, list) else [],
                    "created_at": float(m["created_at"]),
                }
            )

        return {
            "id": str(row["id"]),
            "username": str(row["username"]),
            "library_id": str(row["library_id"]),
            "title": str(row["title"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "messages": messages,
        }

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        citations: Any = None,
    ) -> dict[str, Any]:
        msg_id = uuid.uuid4().hex
        now = time.time()
        citations_json = json.dumps(citations or [])
        backend = self._connection()
        backend.execute_write(
            "INSERT INTO chat_messages (id, conversation_id, role, content, citations_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, str(conversation_id), str(role), str(content), citations_json, now),
        )
        backend.execute_write(
            "UPDATE chat_conversations SET updated_at = ? WHERE id = ?",
            (now, str(conversation_id)),
        )
        backend.commit()
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "citations": citations or [],
            "created_at": now,
        }

    def update_title(
        self,
        conversation_id: str,
        title: str,
        username: str | None = None,
    ) -> bool:
        backend = self._connection()
        clean_title = str(title).strip()[:100] or "Conversazione"
        if username:
            updated = backend.execute_write(
                "UPDATE chat_conversations SET title = ? WHERE id = ? AND username = ?",
                (clean_title, str(conversation_id), str(username)),
            )
        else:
            updated = backend.execute_write(
                "UPDATE chat_conversations SET title = ? WHERE id = ?",
                (clean_title, str(conversation_id)),
            )
        backend.commit()
        return updated > 0

    def delete_conversation(
        self,
        conversation_id: str,
        username: str | None = None,
    ) -> bool:
        backend = self._connection()
        if username:
            conv = backend.execute_one(
                "SELECT id FROM chat_conversations WHERE id = ? AND username = ?",
                (str(conversation_id), str(username)),
            )
            if not conv:
                return False

        backend.execute_write(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            (str(conversation_id),),
        )
        deleted = backend.execute_write(
            "DELETE FROM chat_conversations WHERE id = ?",
            (str(conversation_id),),
        )
        backend.commit()
        return deleted > 0

    def clear(self) -> None:
        """Svuota tutte le conversazioni (test)."""
        backend = self._connection()
        backend.execute_write("DELETE FROM chat_messages", ())
        backend.execute_write("DELETE FROM chat_conversations", ())
        backend.commit()


conversation_store = ConversationStore()
