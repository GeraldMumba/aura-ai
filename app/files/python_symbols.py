from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.files.project_index_store import _safe_content
from app.files.file_tools import _validate_directory, _walk_files

MAX_PYTHON_FILE_BYTES = 512 * 1024
MAX_PROJECT_FILES = 150
MAX_SYMBOLS = 120
MAX_CALLS_PER_SYMBOL = 10
MAX_TOTAL_CALLS = 160
MAX_IMPORTS_PER_FILE = 30


class _SymbolVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        self.scope: list[str] = []
        module_symbol: dict[str, Any] = {
            "file": relative_path,
            "name": "<module>",
            "qualified_name": "<module>",
            "kind": "module",
            "line": 1,
            "end_line": None,
            "docstring": "",
            "calls": [],
        }
        self.symbols: list[dict[str, Any]] = [module_symbol]
        self.imports: list[dict[str, Any]] = []
        self._symbol_stack: list[dict[str, Any]] = [module_symbol]

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append({
                "module": alias.name,
                "name": alias.asname or alias.name.split(".")[0],
                "line": node.lineno,
            })

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            if alias.name == "*":
                continue
            self.imports.append({
                "module": module,
                "name": alias.asname or alias.name,
                "line": node.lineno,
            })

    def _visit_definition(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, kind: str) -> None:
        qualified_name = ".".join([*self.scope, node.name])
        symbol: dict[str, Any] = {
            "file": self.relative_path,
            "name": node.name,
            "qualified_name": qualified_name,
            "kind": kind,
            "line": node.lineno,
            "end_line": getattr(node, "end_lineno", node.lineno),
            "docstring": (ast.get_docstring(node) or "").strip().splitlines()[0][:240],
            "calls": [],
        }
        self.symbols.append(symbol)
        self._symbol_stack.append(symbol)
        self.scope.append(node.name)
        for child in node.body:
            self.visit(child)
        self.scope.pop()
        self._symbol_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_definition(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_definition(node, "async_function")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definition(node, "class")

    def visit_Call(self, node: ast.Call) -> None:
        if self._symbol_stack:
            expression = ast.unparse(node.func) if hasattr(ast, "unparse") else ""
            symbol = self._symbol_stack[-1]
            if expression and len(symbol["calls"]) < MAX_CALLS_PER_SYMBOL:
                symbol["calls"].append({
                    "expression": expression[:160],
                    "name": expression.rsplit(".", 1)[-1],
                    "line": node.lineno,
                })
        self.generic_visit(node)


def analyze_python_source(source: str, relative_path: str = "<memory>") -> dict[str, Any]:
    """Extract static Python symbols, imports and calls without executing project code."""
    try:
        tree = ast.parse(source, filename=relative_path)
    except (SyntaxError, ValueError, TypeError) as exc:
        return {
            "file": relative_path,
            "parse_error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}",
            "imports": [],
            "symbols": [],
        }

    visitor = _SymbolVisitor(relative_path)
    visitor.visit(tree)
    return {
        "file": relative_path,
        "parse_error": None,
        "imports": visitor.imports[:100],
        "symbols": visitor.symbols[:MAX_SYMBOLS],
    }


def analyze_python_project(root: str | Path, max_files: int = MAX_PROJECT_FILES) -> dict[str, Any]:
    """Build a bounded, static symbol map for Python files in a workspace."""
    directory = _validate_directory(root)
    max_files = max(1, min(int(max_files), MAX_PROJECT_FILES))
    analyses: list[dict[str, Any]] = []
    scanned = 0
    skipped = 0
    truncated = False

    for path in _walk_files(directory):
        if path.suffix.lower() not in {".py", ".pyw"}:
            continue
        if scanned >= max_files:
            truncated = True
            break
        scanned += 1
        try:
            if path.stat().st_size > MAX_PYTHON_FILE_BYTES:
                skipped += 1
                continue
            source = _safe_content(path)
            if source is None:
                skipped += 1
                continue
            relative = path.relative_to(directory).as_posix()
        except (OSError, ValueError):
            skipped += 1
            continue
        analyses.append(analyze_python_source(source, relative))

    all_symbols = [symbol for item in analyses for symbol in item["symbols"]][:MAX_SYMBOLS]
    by_name: dict[str, list[str]] = defaultdict(list)
    for symbol in all_symbols:
        by_name[symbol["name"]].append(f'{symbol["file"]}:{symbol["qualified_name"]}')

    total_calls = 0
    for symbol in all_symbols:
        remaining = max(0, MAX_TOTAL_CALLS - total_calls)
        symbol["calls"] = symbol["calls"][:remaining]
        total_calls += len(symbol["calls"])
        for call in symbol["calls"]:
            candidates = by_name.get(call["name"], [])
            call["candidates"] = candidates[:3]
            call["resolution"] = "unique_candidate" if len(candidates) == 1 else (
                "ambiguous" if candidates else "unresolved"
            )

    return {
        "workspace": str(directory),
        "files_analyzed": len(analyses),
        "files_scanned": scanned,
        "files_skipped": skipped,
        "truncated": truncated,
        "parse_errors": [
            {"file": item["file"], "error": item["parse_error"]}
            for item in analyses if item["parse_error"]
        ],
        "modules": [
            {"file": item["file"], "imports": item["imports"][:MAX_IMPORTS_PER_FILE]}
            for item in analyses[:MAX_PROJECT_FILES] if item["imports"]
        ],
        "symbols": all_symbols[:MAX_SYMBOLS],
        "relationship_note": (
            "Call relationships are static name-based candidates, not guaranteed runtime call paths. "
            "Dynamic dispatch, aliases, decorators and generated code may not be resolved."
        ),
    }
