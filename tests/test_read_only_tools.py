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



def test_search_file_contents_returns_line_numbered_matches(tmp_path: Path):
    from app.files.file_tools import search_file_contents

    source = tmp_path / "module.py"
    source.write_text("class Example:\n    def run(self):\n        return 'needle'\n", encoding="utf-8")
    result = search_file_contents(tmp_path, "needle", context_lines=1)

    assert result["matches_found"] == 1
    assert result["results"][0]["line"] == 3
    assert "3:         return 'needle'" in result["results"][0]["excerpt"]
    assert "2:     def run(self):" in result["results"][0]["excerpt"]


def test_search_file_contents_redacts_secret_lines(tmp_path: Path):
    from app.files.file_tools import search_file_contents

    source = tmp_path / "settings.py"
    source.write_text("api_key = 'do-not-leak'\nprint('api_key')\n", encoding="utf-8")
    result = search_file_contents(tmp_path, "api_key", context_lines=0)

    assert result["matches_found"] == 2
    assert "do-not-leak" not in str(result["results"])
    assert "[REDACTED: possible secret]" in result["results"][0]["excerpt"]


def test_search_file_contents_skips_sensitive_files_and_large_files(tmp_path: Path):
    from app.files.file_tools import search_file_contents

    (tmp_path / "module.py").write_text("needle = True", encoding="utf-8")
    (tmp_path / ".env").write_text("needle=secret", encoding="utf-8")
    (tmp_path / "large.py").write_text("needle" + ("x" * (512 * 1024)), encoding="utf-8")

    result = search_file_contents(tmp_path, "needle")

    assert result["matches_found"] == 1
    assert result["results"][0]["path"].endswith("module.py")


def test_search_file_contents_validates_query(tmp_path: Path):
    from app.files.file_tools import search_file_contents

    with pytest.raises(ValueError, match="at least two"):
        search_file_contents(tmp_path, "x")


def test_token_files_are_blocked_from_reading_and_content_search(tmp_path: Path):
    from app.files.file_tools import search_file_contents

    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    token_file = token_dir / "account_gmail_com.json"
    token_file.write_text('{"refresh_token": "do-not-read"}', encoding="utf-8")
    root_token = tmp_path / "token.json"
    root_token.write_text('{"refresh_token": "also-private"}', encoding="utf-8")

    with pytest.raises(ValueError, match="sensitive"):
        read_text_file(token_file)
    with pytest.raises(ValueError, match="sensitive"):
        read_text_file(root_token)

    result = search_file_contents(tmp_path, "refresh_token")
    assert result["matches_found"] == 0
    assert "do-not-read" not in str(result)
    assert "also-private" not in str(result)



def test_analyze_python_project_is_exposed_as_read_only_tool(tmp_path: Path, monkeypatch):
    import app.ai.tool_registry as registry

    monkeypatch.setattr(registry, "HOME", tmp_path.resolve())
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "main.py").write_text(
        "def main():\\n    return 'ready'\\n", encoding="utf-8"
    )

    result = json.loads(execute_tool("analyze_python_project", {"root": str(workspace)}))

    assert result["files_analyzed"] == 1
    assert any(item["qualified_name"] == "main" for item in result["symbols"])
