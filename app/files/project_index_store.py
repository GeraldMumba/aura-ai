from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.database.db import get_connection
from app.files.file_tools import (
    ALLOWED_TEXT_EXTENSIONS,
    SECRET_PATTERN,
    is_sensitive_path,
    _validate_directory,
    _walk_files,
)

MAX_INDEX_FILES = 2000
MAX_INDEX_FILE_BYTES = 512 * 1024
MAX_QUERY_LENGTH = 200


def _safe_content(path: Path) -> str | None:
    if is_sensitive_path(path):
        return None
    if path.suffix.lower() not in ALLOWED_TEXT_EXTENSIONS:
        return None
    try:
        if path.stat().st_size > MAX_INDEX_FILE_BYTES:
            return None
        content = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None
    if "\x00" in content:
        return None
    safe_lines = []
    for line in content.splitlines():
        if SECRET_PATTERN.search(line) and re.search(r"[:=]", line):
            safe_lines.append("[REDACTED: possible secret]")
        else:
            safe_lines.append(line[:2000])
    return "\n".join(safe_lines)


def initialize_project_index() -> None:
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS project_file_index (
                workspace_root TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                modified_ns INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                content TEXT NOT NULL,
                PRIMARY KEY (workspace_root, relative_path)
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_file_workspace
            ON project_file_index(workspace_root)
        """)


def build_project_index(root: str | Path, max_files: int = MAX_INDEX_FILES) -> dict[str, Any]:
    """Refresh a workspace's local, redacted source index in SQLite."""
    directory = _validate_directory(root)
    max_files = max(1, min(int(max_files), MAX_INDEX_FILES))
    workspace = str(directory)
    records: list[tuple[str, int, int, str]] = []
    scanned = 0
    skipped = 0
    truncated = False

    for path in _walk_files(directory):
        if scanned >= max_files:
            truncated = True
            break
        scanned += 1
        content = _safe_content(path)
        if content is None:
            skipped += 1
            continue
        try:
            stat = path.stat()
            relative = path.relative_to(directory).as_posix()
        except (OSError, ValueError):
            skipped += 1
            continue
        records.append((relative, stat.st_mtime_ns, stat.st_size, content))

    initialize_project_index()
    # Replace the workspace snapshot in one transaction, so a failed scan
    # before this point cannot destroy the previous usable index.
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM project_file_index WHERE workspace_root = ?", (workspace,)
        )
        connection.executemany(
            """INSERT INTO project_file_index
               (workspace_root, relative_path, modified_ns, size_bytes, content)
               VALUES (?, ?, ?, ?, ?)""",
            [(workspace, *record) for record in records],
        )

    return {
        "workspace": workspace,
        "files_scanned": scanned,
        "files_indexed": len(records),
        "files_skipped": skipped,
        "truncated": truncated,
    }


def search_project_index(
    root: str | Path,
    query: str,
    max_results: int = 8,
    context_lines: int = 2,
) -> dict[str, Any]:
    """Search the cached index and return compact line-numbered excerpts."""
    directory = _validate_directory(root)
    query = str(query).strip()
    if len(query) < 2:
        raise ValueError("Search query must contain at least two characters.")
    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError("Search query is too long (maximum 200 characters).")
    max_results = max(1, min(int(max_results), 20))
    context_lines = max(0, min(int(context_lines), 3))
    workspace = str(directory)
    initialize_project_index()

    with get_connection() as connection:
        rows = connection.execute(
            """SELECT relative_path, content FROM project_file_index
               WHERE workspace_root = ? ORDER BY relative_path LIMIT 5000""",
            (workspace,),
        ).fetchall()

    needle = query.casefold()
    results = []
    for row in rows:
        lines = row["content"].splitlines()
        for index, line in enumerate(lines):
            if needle not in line.casefold():
                continue
            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)
            excerpt = "\n".join(
                f"{line_no + 1}: {lines[line_no][:500]}"
                for line_no in range(start, end)
            )
            results.append({
                "path": str(directory / row["relative_path"]),
                "relative_path": row["relative_path"],
                "line": index + 1,
                "excerpt": excerpt,
            })
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break

    return {
        "workspace": workspace,
        "query": query,
        "indexed_files": len(rows),
        "matches_found": len(results),
        "results": results,
        "truncated": len(results) >= max_results,
    }


def get_project_index_status(root: str | Path) -> dict[str, Any]:
    directory = _validate_directory(root)
    initialize_project_index()
    with get_connection() as connection:
        row = connection.execute(
            """SELECT COUNT(*) AS files, COALESCE(SUM(size_bytes), 0) AS bytes
               FROM project_file_index WHERE workspace_root = ?""",
            (str(directory),),
        ).fetchone()
    return {
        "workspace": str(directory),
        "indexed_files": int(row["files"]),
        "indexed_size_bytes": int(row["bytes"]),
        "indexed_size_mb": round(int(row["bytes"]) / (1024 * 1024), 2),
    }
