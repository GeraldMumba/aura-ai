import json
from pathlib import Path

import pytest

from app.ai.tool_registry import execute_tool, safe_path
from app.files.file_tools import read_text_file, search_files


def test_search_files_finds_source_file(tmp_path: Path):
    (tmp_path / "sample.py").write_text("print('hello')", encoding="utf-8")
    result = search_files(tmp_path, query="sample")
    assert result["files_found"] == 1
    assert result["results"][0]["name"] == "sample.py"


def test_read_text_file_numbers_lines_and_redacts_secrets(tmp_path: Path):
    path = tmp_path / "settings.py"
    path.write_text("name = 'AURA'\napi_key = 'private-value'\n", encoding="utf-8")
    result = read_text_file(path)
    assert "1: name = 'AURA'" in result["content"]
    assert "private-value" not in result["content"]
    assert "[REDACTED" in result["content"]


def test_read_text_file_blocks_env(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text("TOKEN=abc", encoding="utf-8")
    with pytest.raises(ValueError, match="sensitive"):
        read_text_file(path)


def test_safe_path_rejects_outside_home(tmp_path: Path):
    with pytest.raises(ValueError, match="outside"):
        safe_path(str(tmp_path))


def test_execute_tool_rejects_unknown_and_extra_arguments():
    with pytest.raises(ValueError, match="not permitted"):
        execute_tool("delete_file", {})
    with pytest.raises(ValueError, match="Unsupported"):
        execute_tool("get_memory_info", {"path": "/tmp"})
