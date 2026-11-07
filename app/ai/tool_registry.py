from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.desktop.tools import (
    get_cpu_info, get_disk_info, get_memory_info, get_system_overview,
    get_top_processes,
)
from app.files.file_tools import (
    get_directory_size, get_file_info, get_largest_files,
    read_text_file, search_file_contents, search_files,
)
from app.files.project_index_store import build_project_index, search_project_index
from app.files.python_symbols import analyze_python_project

HOME = Path.home().resolve()

TOOLS = [
    {"type": "function", "function": {"name": "get_memory_info", "description": "Get RAM and swap usage.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_cpu_info", "description": "Get CPU usage and processor information.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_disk_info", "description": "Get disk storage information.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_system_overview", "description": "Get a summary of CPU, memory and disk usage.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_top_processes", "description": "List processes using the most RAM.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "search_files", "description": "Search filenames in a directory under the user's home directory.", "parameters": {"type": "object", "properties": {"root": {"type": "string"}, "query": {"type": "string"}, "extensions": {"type": "array", "items": {"type": "string"}}, "max_results": {"type": "integer"}}, "required": ["root"]}}},
    {"type": "function", "function": {"name": "get_file_info", "description": "Get metadata about a file under the user's home directory.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "get_largest_files", "description": "Find the largest files in a directory under the user's home directory.", "parameters": {"type": "object", "properties": {"root": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["root"]}}},
    {"type": "function", "function": {"name": "get_directory_size", "description": "Calculate storage usage for a directory under the user's home directory.", "parameters": {"type": "object", "properties": {"root": {"type": "string"}}, "required": ["root"]}}},
    {"type": "function", "function": {"name": "search_file_contents", "description": "Search supported source files directly and return bounded line-numbered excerpts.", "parameters": {"type": "object", "properties": {"root": {"type": "string"}, "query": {"type": "string"}, "extensions": {"type": "array", "items": {"type": "string"}}, "max_results": {"type": "integer"}, "max_scan": {"type": "integer"}, "context_lines": {"type": "integer"}}, "required": ["root", "query"]}}},
    {"type": "function", "function": {"name": "read_text_file", "description": "Read a supported text file under the user's home directory. Sensitive files are blocked.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "build_project_index", "description": "Build or refresh a local searchable cache of a project’s supported source files. Use this before searching the project index if it has not been built or after files change. Sensitive files are excluded and likely secret assignments are redacted.", "parameters": {"type": "object", "properties": {"root": {"type": "string"}, "max_files": {"type": "integer"}}, "required": ["root"]}}},
    {"type": "function", "function": {"name": "search_project_index", "description": "Search the previously built local project index and return compact line-numbered code excerpts. Build or refresh the index first when needed.", "parameters": {"type": "object", "properties": {"root": {"type": "string"}, "query": {"type": "string"}, "max_results": {"type": "integer"}, "context_lines": {"type": "integer"}}, "required": ["root", "query"]}}},
    {"type": "function", "function": {"name": "analyze_python_project", "description": "Statically inspect Python files in a project to list classes, functions, imports, line ranges and possible call relationships. Does not execute project code. Call relationships are approximate.", "parameters": {"type": "object", "properties": {"root": {"type": "string"}, "max_files": {"type": "integer"}}, "required": ["root"]}}},
]

FUNCTIONS = {
    "get_memory_info": get_memory_info,
    "get_cpu_info": get_cpu_info,
    "get_disk_info": get_disk_info,
    "get_system_overview": get_system_overview,
    "get_top_processes": get_top_processes,
    "search_files": search_files,
    "get_file_info": get_file_info,
    "get_largest_files": get_largest_files,
    "get_directory_size": get_directory_size,
    "read_text_file": read_text_file,
    "search_file_contents": search_file_contents,
    "build_project_index": build_project_index,
    "search_project_index": search_project_index,
    "analyze_python_project": analyze_python_project,
}

ARGUMENTS = {
    "get_memory_info": set(),
    "get_cpu_info": set(),
    "get_disk_info": set(),
    "get_system_overview": set(),
    "get_top_processes": {"limit"},
    "search_files": {"root", "query", "extensions", "max_results"},
    "get_file_info": {"path"},
    "get_largest_files": {"root", "limit"},
    "get_directory_size": {"root"},
    "read_text_file": {"path", "start_line", "end_line"},
    "search_file_contents": {"root", "query", "extensions", "max_results", "max_scan", "context_lines"},
    "build_project_index": {"root", "max_files"},
    "search_project_index": {"root", "query", "max_results", "context_lines"},
    "analyze_python_project": {"root", "max_files"},
}


def safe_path(value: str) -> str:
    requested = Path(value).expanduser()
    if requested.is_symlink():
        raise ValueError("Symbolic-link paths are not permitted.")
    resolved = requested.resolve()
    try:
        resolved.relative_to(HOME)
    except ValueError as exc:
        raise ValueError("Access outside your home directory is not permitted.") from exc
    return str(resolved)


def execute_tool(name: str, arguments: dict[str, Any] | str | None = None) -> str:
    if name not in FUNCTIONS:
        raise ValueError(f"Tool not permitted: {name}")
    if arguments is None:
        arguments = {}
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object.")
    unexpected = set(arguments) - ARGUMENTS[name]
    if unexpected:
        raise ValueError(f"Unsupported arguments: {', '.join(sorted(unexpected))}")

    args = dict(arguments)
    if "root" in args:
        args["root"] = safe_path(args["root"])
    if "path" in args:
        args["path"] = safe_path(args["path"])
    result = FUNCTIONS[name](**args)
    return json.dumps(result, ensure_ascii=False, indent=2)
