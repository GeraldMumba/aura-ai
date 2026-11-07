from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist",
    ".dart_tool", ".gradle", "target", "htmlcov",
}
ALLOWED_TEXT_EXTENSIONS = {
    ".py", ".pyw", ".txt", ".md", ".rst", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".html", ".htm", ".css", ".js", ".ts",
    ".jsx", ".tsx", ".dart", ".java", ".c", ".cpp", ".h", ".hpp",
    ".sql", ".sh", ".bash", ".xml", ".csv",
}
SENSITIVE_NAMES = {
    ".env", ".env.local", ".env.production", "credentials",
    "credentials.json", "secrets.json", "id_rsa", "id_ed25519",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|private[_-]?key|client[_-]?secret)\b"
)


def _validate_directory(root: str | Path) -> Path:
    requested = Path(root).expanduser()
    if requested.is_symlink():
        raise ValueError("Symbolic-link directories are not supported.")
    path = requested.resolve()
    if not path.exists() or not path.is_dir():
        raise ValueError("Directory does not exist or is not a directory.")
    return path


def _walk_files(root: Path, include_excluded: bool = False):
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if not (current_path / name).is_symlink()
            and (include_excluded or name not in DEFAULT_EXCLUDED_DIRS)
            and (not name.startswith(".") or name in DEFAULT_EXCLUDED_DIRS)
        ]
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = current_path / filename
            try:
                if not path.is_symlink() and path.is_file():
                    yield path
            except OSError:
                continue


def _metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "extension": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 ** 2), 3),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
    }


def search_files(
    root: str | Path,
    query: str = "",
    extensions: list[str] | None = None,
    max_results: int = 30,
    max_scan: int = 5000,
    include_excluded: bool = False,
) -> dict[str, Any]:
    directory = _validate_directory(root)
    max_results = max(1, min(int(max_results), 100))
    max_scan = max(1, min(int(max_scan), 50000))
    allowed = None
    if extensions:
        allowed = {ext.lower() if ext.startswith(".") else "." + ext.lower() for ext in extensions}
    found, scanned, truncated = [], 0, False
    for path in _walk_files(directory, include_excluded):
        if scanned >= max_scan:
            truncated = True
            break
        scanned += 1
        if query and query.casefold() not in path.name.casefold():
            continue
        if allowed and path.suffix.lower() not in allowed:
            continue
        try:
            found.append(_metadata(path))
        except OSError:
            continue
        if len(found) >= max_results:
            truncated = True
            break
    return {
        "directory": str(directory), "files_found": len(found),
        "files_scanned": scanned, "truncated": truncated, "results": found,
    }


def get_file_info(path: str | Path) -> dict[str, Any]:
    requested = Path(path).expanduser()
    if requested.is_symlink():
        raise ValueError("Symbolic links are not supported.")
    file_path = requested.resolve()
    if not file_path.is_file():
        raise ValueError("File does not exist or is not a regular file.")
    return _metadata(file_path)


def get_largest_files(root: str | Path, limit: int = 10, include_excluded: bool = False) -> list[dict[str, Any]]:
    directory = _validate_directory(root)
    limit = max(1, min(int(limit), 50))
    files = []
    for path in _walk_files(directory, include_excluded):
        try:
            files.append(_metadata(path))
        except OSError:
            continue
    return sorted(files, key=lambda item: item["size_bytes"], reverse=True)[:limit]


def get_directory_size(root: str | Path, include_excluded: bool = False) -> dict[str, Any]:
    directory = _validate_directory(root)
    total, count, skipped = 0, 0, 0
    for path in _walk_files(directory, include_excluded):
        try:
            total += path.stat().st_size
            count += 1
        except OSError:
            skipped += 1
    return {
        "directory": str(directory), "file_count": count,
        "total_bytes": total, "total_mb": round(total / (1024 ** 2), 3),
        "total_gb": round(total / (1024 ** 3), 4), "skipped_files": skipped,
    }


def read_text_file(path: str | Path, start_line: int = 1, end_line: int | None = None) -> dict[str, Any]:
    requested = Path(path).expanduser()
    if requested.is_symlink():
        raise ValueError("Symbolic links are not supported.")
    file_path = requested.resolve()
    if not file_path.is_file():
        raise ValueError("File does not exist or is not a regular file.")
    if file_path.name.lower() in SENSITIVE_NAMES or file_path.suffix.lower() in SENSITIVE_SUFFIXES:
        raise ValueError("Reading this sensitive file is not permitted.")
    if file_path.suffix.lower() not in ALLOWED_TEXT_EXTENSIONS:
        raise ValueError("This file type is not supported for text reading.")
    if file_path.stat().st_size > 512 * 1024:
        raise ValueError("File is too large. Maximum supported size is 512 KB.")
    content = file_path.read_text(encoding="utf-8", errors="replace")
    if "\x00" in content:
        raise ValueError("This appears to be a binary file.")
    lines = content.splitlines()
    start_line = max(1, int(start_line))
    if start_line > 1_000_000:
        raise ValueError("Requested line number is too large.")
    end_line = min(len(lines), start_line + 399) if end_line is None else min(len(lines), int(end_line))
    if end_line < start_line:
        raise ValueError("End line cannot be before start line.")
    selected = lines[start_line - 1:end_line]
    safe_lines = [
        "[REDACTED: possible secret]" if SECRET_PATTERN.search(line) and re.search(r"[:=]", line) else line
        for line in selected
    ]
    return {
        "name": file_path.name, "path": str(file_path), "total_lines": len(lines),
        "start_line": start_line,
        "end_line": start_line + len(selected) - 1 if selected else start_line,
        "content": "\n".join(f"{start_line + index}: {line}" for index, line in enumerate(safe_lines)),
        "truncated": end_line < len(lines),
    }


def search_file_contents(root, query, extensions=None, max_results=12, max_scan=1500, context_lines=2):
    """Search supported text files and return bounded, line-numbered excerpts."""
    directory = _validate_directory(root)
    query = str(query).strip()
    if len(query) < 2:
        raise ValueError("Search query must contain at least two characters.")
    if len(query) > 200:
        raise ValueError("Search query is too long (maximum 200 characters).")
    max_results = max(1, min(int(max_results), 30))
    max_scan = max(1, min(int(max_scan), 10000))
    context_lines = max(0, min(int(context_lines), 4))
    allowed = ALLOWED_TEXT_EXTENSIONS
    if extensions:
        requested = {ext.lower() if ext.startswith(".") else "." + ext.lower() for ext in extensions}
        allowed = allowed.intersection(requested)
    matches, scanned, truncated = [], 0, False
    needle = query.casefold()
    for path in _walk_files(directory):
        if path.suffix.lower() not in allowed:
            continue
        if path.name.lower() in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
            continue
        if scanned >= max_scan:
            truncated = True
            break
        scanned += 1
        try:
            if path.stat().st_size > 512 * 1024:
                continue
            content = path.read_text(encoding="utf-8", errors="replace")
            if "\x00" in content:
                continue
        except (OSError, UnicodeError):
            continue
        lines = content.splitlines()
        for index, line in enumerate(lines):
            if needle not in line.casefold():
                continue
            start, end = max(0, index - context_lines), min(len(lines), index + context_lines + 1)
            excerpt = []
            for line_index in range(start, end):
                selected = lines[line_index]
                if SECRET_PATTERN.search(selected) and re.search(r"[:=]", selected):
                    selected = "[REDACTED: possible secret]"
                excerpt.append(f"{line_index + 1}: {selected[:500]}")
            matches.append({"path": str(path), "line": index + 1, "excerpt": "\n".join(excerpt)})
            if len(matches) >= max_results:
                truncated = True
                break
        if len(matches) >= max_results:
            break
    return {
        "directory": str(directory), "query": query, "files_scanned": scanned,
        "matches_found": len(matches), "truncated": truncated, "results": matches,
    }
