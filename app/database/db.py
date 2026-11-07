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
    # Supply timestamps explicitly so this also works with databases created
    # by older AURA versions whose columns may not have DEFAULT values.
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO conversations(title, created_at, updated_at)
            VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (title[:100],),
        )
        return int(cursor.lastrowid)


def add_message(conversation_id: int, role: str, content: str) -> int:
    if role not in {"user", "assistant", "system"}:
        raise ValueError("Unsupported message role")
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages(conversation_id, role, content, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
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


# Workspace-scoped persistence for safe file-change proposals.
import json as _json
from datetime import datetime as _datetime


def initialize_change_tables():
    """Create the current workspace-scoped tables, preserving legacy tables.

    Older AURA experiments used the same table names with different columns.
    SQLite's CREATE TABLE IF NOT EXISTS does not update those schemas, so
    detect incompatible tables and retain them under legacy names before
    creating the current schema.
    """
    required = {
        "pending_changes": {"id", "workspace_root", "proposal_json", "created_at"},
        "change_history": {
            "id", "workspace_root", "change_id", "action",
            "status", "details_json", "created_at",
        },
    }
    with get_connection() as connection:
        for table, columns in required.items():
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists:
                actual = {
                    row["name"] for row in connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                }
                if not columns.issubset(actual):
                    # Remove known index names before renaming so they can be
                    # recreated against the new table rather than the legacy one.
                    index_name = (
                        "idx_pending_workspace" if table == "pending_changes"
                        else "idx_change_history_workspace"
                    )
                    connection.execute(f"DROP INDEX IF EXISTS {index_name}")
                    legacy = f"{table}_legacy"
                    suffix = 1
                    while connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (legacy,),
                    ).fetchone():
                        suffix += 1
                        legacy = f"{table}_legacy_{suffix}"
                    connection.execute(f"ALTER TABLE {table} RENAME TO {legacy}")

        connection.executescript("""
            CREATE TABLE IF NOT EXISTS pending_changes (
                id TEXT PRIMARY KEY,
                workspace_root TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pending_workspace
                ON pending_changes(workspace_root);
            CREATE TABLE IF NOT EXISTS change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_root TEXT NOT NULL,
                change_id TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_change_history_workspace
                ON change_history(workspace_root, id DESC);
        """)


def _workspace_key(workspace_root):
    return str(Path(workspace_root).expanduser().resolve())


def save_pending_change(workspace_root, proposal):
    key = _workspace_key(workspace_root)
    with get_connection() as connection:
        connection.execute(
            """INSERT OR REPLACE INTO pending_changes
               (id, workspace_root, proposal_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (proposal["id"], key, _json.dumps(proposal, ensure_ascii=False), proposal["created_at"]),
        )


def get_pending_changes(workspace_root):
    key = _workspace_key(workspace_root)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT proposal_json FROM pending_changes WHERE workspace_root=? ORDER BY created_at",
            (key,),
        ).fetchall()
    results = []
    for row in rows:
        try:
            value = _json.loads(row["proposal_json"])
            if isinstance(value, dict):
                results.append(value)
        except (ValueError, TypeError):
            continue
    return results


def delete_pending_change(change_id, workspace_root):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM pending_changes WHERE id=? AND workspace_root=?",
            (change_id, _workspace_key(workspace_root)),
        )
        return cursor.rowcount > 0


def record_change_history(workspace_root, change_id, action, status, details=None):
    timestamp = _datetime.now().isoformat(timespec="seconds")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO change_history
               (workspace_root, change_id, action, status, details_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (_workspace_key(workspace_root), change_id, action, status,
             _json.dumps(details or {}, ensure_ascii=False, default=str), timestamp),
        )


def get_change_history(workspace_root, limit=50):
    limit = max(1, min(int(limit), 500))
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT change_id, action, status, details_json, created_at
               FROM change_history WHERE workspace_root=?
               ORDER BY id DESC LIMIT ?""",
            (_workspace_key(workspace_root), limit),
        ).fetchall()
    result = []
    for row in rows:
        try:
            details = _json.loads(row["details_json"])
        except (ValueError, TypeError):
            details = {}
        result.append({
            "change_id": row["change_id"], "action": row["action"],
            "status": row["status"], "details": details,
            "created_at": row["created_at"],
        })
    return result
