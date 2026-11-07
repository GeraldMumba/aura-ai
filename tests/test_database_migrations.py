import sqlite3

from app.database import db


def test_change_tables_migrate_legacy_schemas_without_dropping_data(tmp_path, monkeypatch):
    database_file = tmp_path / "legacy-aura.db"
    monkeypatch.setattr(db, "APP_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", database_file)

    with sqlite3.connect(database_file) as connection:
        connection.executescript("""
            CREATE TABLE pending_changes (
                id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT
            );
            INSERT INTO pending_changes(id, action, details, created_at)
            VALUES ('old-1', 'edit', 'legacy proposal', '2026-01-01');

            CREATE TABLE change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                details TEXT
            );
            INSERT INTO change_history(action, details)
            VALUES ('legacy-action', 'legacy history');
        """)

    db.initialize_change_tables()

    with db.get_connection() as connection:
        pending_columns = {
            row["name"] for row in connection.execute(
                "PRAGMA table_info(pending_changes)"
            )
        }
        history_columns = {
            row["name"] for row in connection.execute(
                "PRAGMA table_info(change_history)"
            )
        }
        assert {"id", "workspace_root", "proposal_json", "created_at"} <= pending_columns
        assert {
            "id", "workspace_root", "change_id", "action",
            "status", "details_json", "created_at",
        } <= history_columns

        legacy_pending = connection.execute(
            "SELECT action, details FROM pending_changes_legacy WHERE id='old-1'"
        ).fetchone()
        legacy_history = connection.execute(
            "SELECT action, details FROM change_history_legacy"
        ).fetchone()

    assert legacy_pending["action"] == "edit"
    assert legacy_pending["details"] == "legacy proposal"
    assert legacy_history["action"] == "legacy-action"
