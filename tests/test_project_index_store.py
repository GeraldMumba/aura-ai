from pathlib import Path

import pytest

from app.files.project_index_store import (
    build_project_index,
    get_project_index_status,
    search_project_index,
)


def test_build_and_search_project_index(tmp_path: Path, monkeypatch):
    from app.database import db

    monkeypatch.setattr(db, "APP_DIR", tmp_path / "data")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data" / "test.db")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.py").write_text(
        "class AuraAgent:\n    def answer(self):\n        return 'project intelligence'\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("TOKEN=do-not-index", encoding="utf-8")

    built = build_project_index(tmp_path)
    found = search_project_index(tmp_path, "project intelligence")

    assert built["files_indexed"] == 1
    assert found["matches_found"] == 1
    assert found["results"][0]["relative_path"] == "src/agent.py"
    assert "3:         return 'project intelligence'" in found["results"][0]["excerpt"]


def test_project_index_redacts_secret_assignments(tmp_path: Path, monkeypatch):
    from app.database import db

    monkeypatch.setattr(db, "APP_DIR", tmp_path / "data")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data" / "test.db")
    (tmp_path / "settings.py").write_text(
        "api_key = 'private-value'\nprint('safe')\n", encoding="utf-8"
    )

    build_project_index(tmp_path)
    result = search_project_index(tmp_path, "api_key")

    assert result["matches_found"] == 0
    assert "private-value" not in str(result)


def test_project_index_refresh_removes_deleted_files(tmp_path: Path, monkeypatch):
    from app.database import db

    monkeypatch.setattr(db, "APP_DIR", tmp_path / "data")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data" / "test.db")
    source = tmp_path / "module.py"
    source.write_text("needle_value = 1", encoding="utf-8")
    build_project_index(tmp_path)
    source.unlink()
    refreshed = build_project_index(tmp_path)

    assert refreshed["files_indexed"] == 0
    assert search_project_index(tmp_path, "needle_value")["matches_found"] == 0
    assert get_project_index_status(tmp_path)["indexed_files"] == 0


def test_project_index_rejects_short_queries(tmp_path: Path, monkeypatch):
    from app.database import db

    monkeypatch.setattr(db, "APP_DIR", tmp_path / "data")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "data" / "test.db")
    build_project_index(tmp_path)
    with pytest.raises(ValueError, match="at least two"):
        search_project_index(tmp_path, "x")
