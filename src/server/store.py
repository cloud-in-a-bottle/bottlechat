import html
import json
import re
import secrets
from datetime import UTC
from datetime import datetime
from sqlite3 import Row

import attr

from server.db import Database
from server.models import Chat
from server.models import ChatSummary
from server.models import Effort
from server.models import Message
from server.models import MessageStatus
from server.models import Role
from server.models import Settings
from server.models import ShareLink
from server.models import Usage

_DEFAULT_TITLE = "New chat"
_WORD = re.compile(r"[\w'-]+", re.UNICODE)

# fts5's snippet() wraps matches in whatever delimiters you give it but leaves the surrounding
# message text exactly as stored — so asking it for "<mark>" directly would hand the client raw
# model output to render as HTML.  Ask for private-use sentinels instead, escape the whole
# snippet, then turn the sentinels into the only markup that can come out of this.
_HIT_OPEN = "\ue000"
_HIT_CLOSE = "\ue001"


def _safe_snippet(raw: str | None) -> str | None:
    if raw is None:
        return None
    return html.escape(raw).replace(_HIT_OPEN, "<mark>").replace(_HIT_CLOSE, "</mark>")


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id() -> str:
    return secrets.token_urlsafe(9)


def new_share_token() -> str:
    return secrets.token_urlsafe(24)


def _fts_query(text: str) -> str | None:
    """Turn free text into an FTS5 MATCH expression, treating the trailing word as a prefix.

    Everything is quoted, so FTS operators the user types are matched literally instead of
    blowing up the query.
    """
    words = _WORD.findall(text)
    if not words:
        return None
    quoted = [f'"{w}"' for w in words[:-1]]
    quoted.append(f'"{words[-1]}"*')
    return " ".join(quoted)


def _usage_from_json(raw: str | None) -> Usage | None:
    if not raw:
        return None
    data = json.loads(raw)
    return Usage(
        prompt_tokens=data.get("prompt_tokens"),
        completion_tokens=data.get("completion_tokens"),
        reasoning_tokens=data.get("reasoning_tokens"),
    )


def _chat_from_row(row: Row) -> Chat:
    return Chat(
        id=row["id"],
        title=row["title"],
        model=row["model"],
        effort=Effort(row["effort"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _message_from_row(row: Row) -> Message:
    return Message(
        id=row["id"],
        chat_id=row["chat_id"],
        seq=row["seq"],
        role=Role(row["role"]),
        content=row["content"],
        reasoning=row["reasoning"],
        status=MessageStatus(row["status"]),
        model=row["model"],
        effort=Effort(row["effort"]) if row["effort"] else None,
        error=row["error"],
        usage=_usage_from_json(row["usage_json"]),
        created_at=row["created_at"],
    )


class Store:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ─── chats ───

    def create_chat(self, model: str | None, effort: Effort) -> Chat:
        chat = Chat(
            id=new_id(),
            title=_DEFAULT_TITLE,
            model=model,
            effort=effort,
            created_at=now(),
            updated_at=now(),
        )
        with self._db.cursor() as cur:
            cur.execute(
                "INSERT INTO chats (id, title, model, effort, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chat.id, chat.title, chat.model, chat.effort.value, chat.created_at, chat.updated_at),
            )
        return chat

    def get_chat(self, chat_id: str) -> Chat | None:
        with self._db.cursor() as cur:
            row = cur.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        return _chat_from_row(row) if row else None

    def update_chat(
        self,
        chat_id: str,
        *,
        title: str | None = None,
        model: str | None = None,
        effort: Effort | None = None,
        touch: bool = True,
    ) -> None:
        sets: list[str] = []
        params: list[str] = []
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if model is not None:
            sets.append("model = ?")
            params.append(model)
        if effort is not None:
            sets.append("effort = ?")
            params.append(effort.value)
        if touch:
            sets.append("updated_at = ?")
            params.append(now())
        if not sets:
            return
        params.append(chat_id)
        with self._db.cursor() as cur:
            cur.execute(f"UPDATE chats SET {', '.join(sets)} WHERE id = ?", params)

    def delete_chat(self, chat_id: str) -> bool:
        with self._db.cursor() as cur:
            cur.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            return cur.rowcount > 0

    def list_chats(self, limit: int, offset: int) -> list[ChatSummary]:
        with self._db.cursor() as cur:
            rows = cur.execute(
                "SELECT id, title, updated_at FROM chats ORDER BY updated_at DESC, rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [ChatSummary(id=r["id"], title=r["title"], updated_at=r["updated_at"]) for r in rows]

    def search_chats(self, query: str, limit: int) -> list[ChatSummary]:
        """Chats whose title or any message matches ``query``, newest first, with a snippet."""
        match = _fts_query(query)
        if match is None:
            return []
        with self._db.cursor() as cur:
            rows = cur.execute(
                """
                WITH hits AS (
                    SELECT chat_id, snippet(messages_fts, -1, ?, ?, '…', 12) AS snippet, rank
                      FROM messages_fts WHERE messages_fts MATCH ?
                    UNION ALL
                    SELECT chat_id, NULL AS snippet, rank FROM chats_fts WHERE chats_fts MATCH ?
                )
                SELECT c.id, c.title, c.updated_at,
                       (SELECT h.snippet FROM hits h
                         WHERE h.chat_id = c.id AND h.snippet IS NOT NULL
                         ORDER BY h.rank LIMIT 1) AS snippet
                  FROM chats c
                 WHERE c.id IN (SELECT chat_id FROM hits)
                 ORDER BY c.updated_at DESC, c.rowid DESC
                 LIMIT ?
                """,
                (_HIT_OPEN, _HIT_CLOSE, match, match, limit),
            ).fetchall()
        return [
            ChatSummary(id=r["id"], title=r["title"], updated_at=r["updated_at"], snippet=_safe_snippet(r["snippet"]))
            for r in rows
        ]

    # ─── messages ───

    def get_messages(self, chat_id: str) -> list[Message]:
        with self._db.cursor() as cur:
            rows = cur.execute("SELECT * FROM messages WHERE chat_id = ? ORDER BY seq", (chat_id,)).fetchall()
        return [_message_from_row(r) for r in rows]

    def get_message(self, message_id: str) -> Message | None:
        with self._db.cursor() as cur:
            row = cur.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return _message_from_row(row) if row else None

    def append_message(
        self,
        chat_id: str,
        role: Role,
        *,
        content: str = "",
        status: MessageStatus = MessageStatus.COMPLETE,
        model: str | None = None,
        effort: Effort | None = None,
    ) -> Message:
        message = Message(
            id=new_id(),
            chat_id=chat_id,
            seq=0,
            role=role,
            content=content,
            reasoning="",
            status=status,
            model=model,
            effort=effort,
            error=None,
            usage=None,
            created_at=now(),
        )
        with self._db.transaction() as cur:
            row = cur.execute("SELECT COALESCE(MAX(seq), -1) + 1 AS seq FROM messages WHERE chat_id = ?", (chat_id,))
            seq = int(row.fetchone()["seq"])
            cur.execute(
                """INSERT INTO messages (id, chat_id, seq, role, content, reasoning, status, model, effort, created_at)
                   VALUES (?, ?, ?, ?, ?, '', ?, ?, ?, ?)""",
                (
                    message.id,
                    chat_id,
                    seq,
                    role.value,
                    content,
                    status.value,
                    model,
                    effort.value if effort else None,
                    message.created_at,
                ),
            )
            cur.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (message.created_at, chat_id))
        return attr.evolve(message, seq=seq)

    def save_message_progress(self, message_id: str, content: str, reasoning: str) -> None:
        with self._db.cursor() as cur:
            cur.execute(
                "UPDATE messages SET content = ?, reasoning = ? WHERE id = ?",
                (content, reasoning, message_id),
            )

    def finish_message(
        self,
        message_id: str,
        *,
        content: str,
        reasoning: str,
        status: MessageStatus,
        error: str | None,
        usage: Usage | None,
    ) -> None:
        usage_json = (
            json.dumps(
                {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "reasoning_tokens": usage.reasoning_tokens,
                }
            )
            if usage
            else None
        )
        with self._db.transaction() as cur:
            cur.execute(
                "UPDATE messages SET content = ?, reasoning = ?, status = ?, error = ?, usage_json = ? WHERE id = ?",
                (content, reasoning, status.value, error, usage_json, message_id),
            )
            cur.execute(
                "UPDATE chats SET updated_at = ? WHERE id = (SELECT chat_id FROM messages WHERE id = ?)",
                (now(), message_id),
            )

    def reset_message_for_retry(self, message_id: str, model: str, effort: Effort) -> None:
        with self._db.cursor() as cur:
            cur.execute(
                """UPDATE messages
                      SET content = '', reasoning = '', status = ?, error = NULL, usage_json = NULL,
                          model = ?, effort = ?
                    WHERE id = ?""",
                (MessageStatus.STREAMING.value, model, effort.value, message_id),
            )

    def mark_streaming_as_interrupted(self) -> int:
        """Called at startup: no run survives a restart, so nothing may stay in 'streaming'."""
        with self._db.cursor() as cur:
            cur.execute(
                "UPDATE messages SET status = ? WHERE status = ?",
                (MessageStatus.INTERRUPTED.value, MessageStatus.STREAMING.value),
            )
            return cur.rowcount

    # ─── shares ───

    def get_share_for_chat(self, chat_id: str) -> ShareLink | None:
        with self._db.cursor() as cur:
            row = cur.execute("SELECT * FROM shares WHERE chat_id = ?", (chat_id,)).fetchone()
        return ShareLink(token=row["token"], chat_id=row["chat_id"], created_at=row["created_at"]) if row else None

    def create_share(self, chat_id: str) -> ShareLink:
        existing = self.get_share_for_chat(chat_id)
        if existing:
            return existing
        share = ShareLink(token=new_share_token(), chat_id=chat_id, created_at=now())
        with self._db.cursor() as cur:
            cur.execute(
                "INSERT INTO shares (token, chat_id, created_at) VALUES (?, ?, ?)",
                (share.token, share.chat_id, share.created_at),
            )
        return share

    def revoke_share(self, chat_id: str) -> bool:
        with self._db.cursor() as cur:
            cur.execute("DELETE FROM shares WHERE chat_id = ?", (chat_id,))
            return cur.rowcount > 0

    def chat_for_share_token(self, token: str) -> Chat | None:
        with self._db.cursor() as cur:
            row = cur.execute(
                "SELECT c.* FROM chats c JOIN shares s ON s.chat_id = c.id WHERE s.token = ?",
                (token,),
            ).fetchone()
        return _chat_from_row(row) if row else None

    # ─── settings ───

    def get_settings(self) -> Settings:
        with self._db.cursor() as cur:
            rows = cur.execute("SELECT key, value FROM settings").fetchall()
        values = {r["key"]: r["value"] for r in rows}
        raw_effort = values.get("effort", Effort.OFF.value)
        return Settings(
            model=values.get("model"),
            effort=Effort(raw_effort) if raw_effort in set(Effort) else Effort.OFF,
        )

    def save_settings(self, *, model: str | None, effort: Effort) -> None:
        with self._db.transaction() as cur:
            if model is not None:
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('model', ?)", (model,))
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('effort', ?)", (effort.value,))
