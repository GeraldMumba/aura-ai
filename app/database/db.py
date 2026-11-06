from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get(
    "AURA_DATA_DIR",
    str(Path.home() / ".local" / "share" / "aura-ai"),
)).expanduser()
DB_PATH = APP_DIR / "aura.db"


def get_connection() -> sqlite3.Connection:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'New conversation',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, id);
            """
        )


def create_conversation(title: str = "New conversation") -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO conversations(title) VALUES (?)",
            (title[:100],),
        )
        return int(cursor.lastrowid)


def add_message(conversation_id: int, role: str, content: str) -> int:
    if role not in {"user", "assistant", "system"}:
        raise ValueError("Unsupported message role")
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO messages(conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content),
        )
        connection.execute(
            "UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (conversation_id,),
        )
        return int(cursor.lastrowid)


def get_messages(conversation_id: int, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT role, content, created_at FROM messages
               WHERE conversation_id=? ORDER BY id DESC LIMIT ?""",
            (conversation_id, limit),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def list_conversations(limit: int = 30) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT id, title, created_at, updated_at
               FROM conversations ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_conversation_title(conversation_id: int, title: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE conversations SET title=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (title[:100], conversation_id),
        )
