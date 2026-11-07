from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from app.files.file_tools import (
    ALLOWED_TEXT_EXTENSIONS,
    DEFAULT_EXCLUDED_DIRS,
    SENSITIVE_NAMES,
    SENSITIVE_SUFFIXES,
)

MANIFEST_NAMES = {
    "pyproject.toml", "requirements.txt", "Pipfile", "setup.py",
    "package.json", "pubspec.yaml", "Cargo.toml", "go.mod",
    "pom.xml", "build.gradle", "composer.json",
}
MAX_FILES = 10000
MAX_MANIFEST_BYTES = 128 * 1024

LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".pyw": "Python", ".js": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".dart": "Dart", ".java": "Java", ".kt": "Kotlin",
    ".c": "C", ".h": "C/C++", ".cpp": "C++", ".hpp": "C++",
    ".cs": "C#", ".go": "Go", ".rs": "Rust", ".php": "PHP",
    ".rb": "Ruby", ".swift": "Swift", ".html": "HTML",
    ".css": "CSS", ".sql": "SQL", ".sh": "Shell",
}


def _safe_root(root: str | Path) -> Path:
    requested = Path(root).expanduser()
    if requested.is_symlink():
        raise ValueError("Symbolic-link workspaces are not supported.")
    resolved = requested.resolve()
    if not resolved.is_dir():
        raise ValueError("Workspace does not exist or is not a directory.")
    return resolved


def _walk_project_files(root: Path, max_files: int):
    count = 0
    truncated = False
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name not in DEFAULT_EXCLUDED_DIRS
            and not name.startswith(".")
            and not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = current_path / filename
            if filename.startswith(".") or path.is_symlink():
                continue
            if filename.lower() in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
                continue
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            if count >= max_files:
                truncated = True
                return
            count += 1
            yield path
    return


def _manifest_frameworks(root: Path, files: list[Path]) -> list[str]:
    names = {path.name.lower() for path in files}
    frameworks: set[str] = set()
    if "manage.py" in names or any(path.name == "django" for path in root.iterdir() if path.is_dir()):
        frameworks.add("Django")
    if "pubspec.yaml" in names:
        frameworks.add("Flutter / Dart")
    if "package.json" in names:
        frameworks.add("Node.js")
        package = next((p for p in files if p.name == "package.json"), None)
        if package:
            try:
                if package.stat().st_size <= MAX_MANIFEST_BYTES:
                    data = json.loads(package.read_text(encoding="utf-8"))
                    dependencies = {
                        **data.get("dependencies", {}),
                        **data.get("devDependencies", {}),
                    }
                    for dependency, label in (
                        ("react", "React"), ("next", "Next.js"),
                        ("vue", "Vue"), ("express", "Express"),
                        ("vite", "Vite"), ("@angular/core", "Angular"),
                    ):
                        if dependency in dependencies:
                            frameworks.add(label)
            except (OSError, UnicodeError, ValueError, TypeError):
                pass
    if "pyproject.toml" in names or "requirements.txt" in names or "pipfile" in names:
        frameworks.add("Python project")
        text = ""
        manifest = next((p for p in files if p.name in {"pyproject.toml", "requirements.txt", "Pipfile"}), None)
        if manifest:
            try:
                if manifest.stat().st_size <= MAX_MANIFEST_BYTES:
                    text = manifest.read_text(encoding="utf-8", errors="ignore").lower()
            except OSError:
                pass
        for dependency, label in (
            ("fastapi", "FastAPI"), ("flask", "Flask"),
            ("django", "Django"), ("pyside6", "PySide6"),
        ):
            if dependency in text:
                frameworks.add(label)
    if "cargo.toml" in names:
        frameworks.add("Rust / Cargo")
    if "go.mod" in names:
        frameworks.add("Go modules")
    if "pom.xml" in names or "build.gradle" in names:
        frameworks.add("Java build")
    return sorted(frameworks)


def analyze_project(root: str | Path, max_files: int = MAX_FILES) -> dict[str, Any]:
    """Build a bounded, read-only project overview without sending files to an AI."""
    directory = _safe_root(root)
    max_files = max(1, min(int(max_files), MAX_FILES))
    files: list[Path] = []
    total_bytes = 0
    extension_counts: Counter[str] = Counter()
    for path in _walk_project_files(directory, max_files):
        files.append(path)
        extension_counts[path.suffix.lower() or "[no extension]"] += 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            pass

    language_counts: Counter[str] = Counter()
    for extension, count in extension_counts.items():
        language = LANGUAGE_BY_EXTENSION.get(extension)
        if language:
            language_counts[language] += count

    frameworks = _manifest_frameworks(directory, files)
    largest = []
    for path in files:
        try:
            largest.append((path.stat().st_size, path.relative_to(directory).as_posix()))
        except OSError:
            continue
    largest.sort(reverse=True)
    return {
        "root": str(directory),
        "files_scanned": len(files),
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "languages": dict(language_counts.most_common()),
        "extensions": dict(extension_counts.most_common(12)),
        "frameworks": frameworks,
        "largest_files": [
            {"path": name, "size_bytes": size}
            for size, name in largest[:5]
        ],
        "truncated": len(files) >= max_files,
    }


def format_project_report(report: dict[str, Any]) -> str:
    languages = report.get("languages", {})
    extensions = report.get("extensions", {})
    frameworks = report.get("frameworks", [])
    largest = report.get("largest_files", [])
    lines = [
        f"PROJECT: {report['root']}",
        f"Files scanned: {report['files_scanned']}",
        f"Approximate source/file size: {report['total_size_mb']} MB",
        "",
        "LANGUAGES:",
    ]
    lines.extend(f"  • {name}: {count} files" for name, count in languages.items())
    if not languages:
        lines.append("  • No recognized source languages found")
    lines.extend(["", "FRAMEWORKS / PROJECT TYPES:"])
    lines.extend(f"  • {name}" for name in frameworks)
    if not frameworks:
        lines.append("  • No known framework manifest detected")
    lines.extend(["", "COMMON FILE TYPES:"])
    lines.extend(f"  • {extension}: {count}" for extension, count in extensions.items())
    lines.extend(["", "LARGEST FILES:"])
    lines.extend(f"  • {name} ({size / 1024:.1f} KB)" for name, size in
                 ((item["path"], item["size_bytes"]) for item in largest))
    if not largest:
        lines.append("  • None")
    if report.get("truncated"):
        lines.extend(["", "Note: Scan reached its file limit; this report may be incomplete."])
    lines.extend([
        "",
        "This report is metadata-only. File contents have not been sent to Ollama.",
    ])
    return "\n".join(lines)
