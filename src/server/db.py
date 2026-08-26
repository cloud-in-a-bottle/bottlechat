import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Chat history is small and every statement here is a point lookup or a short scan, so a single
# shared connection behind a lock is simpler (and faster) than a pool.  WAL keeps the streaming
# writer from blocking readers in other tabs.
_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chats (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    model       TEXT,
    effort      TEXT NOT NULL DEFAULT 'off',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chats_updated_at ON chats (updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    chat_id     TEXT NOT NULL REFERENCES chats (id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    reasoning   TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'complete',
    model       TEXT,
    effort      TEXT,
    error       TEXT,
    usage_json  TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (chat_id, seq)
);
CREATE INDEX IF NOT EXISTS messages_chat ON messages (chat_id, seq);

CREATE TABLE IF NOT EXISTS shares (
    token       TEXT PRIMARY KEY,
    chat_id     TEXT NOT NULL UNIQUE REFERENCES chats (id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

-- Search index over message text, kept in sync by the triggers below.  A plain (not
-- external-content) FTS5 table: it stores its own copy, which costs a little space and buys
-- snippet() without a join back to `messages`.  Reasoning is indexed too, so a chat is findable
-- by something the model only said while thinking.
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5 (
    content,
    reasoning,
    chat_id UNINDEXED,
    message_id UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts (rowid, content, reasoning, chat_id, message_id)
    VALUES (new.rowid, new.content, new.reasoning, new.chat_id, new.id);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE OF content, reasoning ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.rowid;
    INSERT INTO messages_fts (rowid, content, reasoning, chat_id, message_id)
    VALUES (new.rowid, new.content, new.reasoning, new.chat_id, new.id);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.rowid;
END;

-- Chat titles are searchable too, so "that rust thread-pool chat" finds the chat even when the
-- phrase only ever appeared in the title.
CREATE VIRTUAL TABLE IF NOT EXISTS chats_fts USING fts5 (
    title,
    chat_id UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chats_fts_insert AFTER INSERT ON chats BEGIN
    INSERT INTO chats_fts (rowid, title, chat_id) VALUES (new.rowid, new.title, new.id);
END;
CREATE TRIGGER IF NOT EXISTS chats_fts_update AFTER UPDATE OF title ON chats BEGIN
    DELETE FROM chats_fts WHERE rowid = old.rowid;
    INSERT INTO chats_fts (rowid, title, chat_id) VALUES (new.rowid, new.title, new.id);
END;
CREATE TRIGGER IF NOT EXISTS chats_fts_delete AFTER DELETE ON chats BEGIN
    DELETE FROM chats_fts WHERE rowid = old.rowid;
END;
"""


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        """Serialized access to the shared connection.  Not reentrant."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN")
            try:
                yield cur
            except BaseException:
                cur.execute("ROLLBACK")
                raise
            else:
                cur.execute("COMMIT")
            finally:
                cur.close()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
