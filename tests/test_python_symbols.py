from pathlib import Path

from app.files.python_symbols import analyze_python_project, analyze_python_source


def test_analyze_python_source_extracts_symbols_imports_and_calls():
    source = """from pathlib import Path
import json

class MailClient:
    def send(self):
        self.authenticate()

    def authenticate(self):
        return json.loads("{}")

def main():
    client = MailClient()
    client.send()
"""
    result = analyze_python_source(source, "mail.py")

    assert result["parse_error"] is None
    assert {item["name"] for item in result["imports"]} == {"Path", "json"}
    symbols = {item["qualified_name"]: item for item in result["symbols"]}
    assert symbols["MailClient"]["kind"] == "class"
    assert symbols["MailClient.send"]["line"] == 5
    assert any(call["expression"] == "self.authenticate" for call in symbols["MailClient.send"]["calls"])
    assert any(call["expression"] == "json.loads" for call in symbols["MailClient.authenticate"]["calls"])


def test_analyze_python_source_reports_syntax_errors_without_raising():
    result = analyze_python_source("def broken(:\n    pass\n", "broken.py")

    assert result["symbols"] == []
    assert result["parse_error"].startswith("SyntaxError:")


def test_analyze_python_project_builds_bounded_static_call_candidates(tmp_path: Path):
    (tmp_path / "auth.py").write_text(
        "def authenticate():\n    return True\n", encoding="utf-8"
    )
    (tmp_path / "main.py").write_text(
        "from auth import authenticate\n\ndef main():\n    authenticate()\n",
        encoding="utf-8",
    )
    (tmp_path / "token.json").write_text(
        '{"refresh_token": "must-not-be-read"}', encoding="utf-8"
    )

    result = analyze_python_project(tmp_path)

    assert result["files_analyzed"] == 2
    assert {item["file"] for item in result["symbols"]} == {"auth.py", "main.py"}
    main = next(item for item in result["symbols"] if item["qualified_name"] == "main")
    call = next(item for item in main["calls"] if item["name"] == "authenticate")
    assert call["resolution"] == "unique_candidate"
    assert call["candidates"] == ["auth.py:authenticate"]
    assert "must-not-be-read" not in str(result)
    assert "static name-based candidates" in result["relationship_note"]


def test_analyze_python_project_respects_file_limit(tmp_path: Path):
    for index in range(3):
        (tmp_path / f"module_{index}.py").write_text(
            f"def function_{index}():\n    return {index}\n", encoding="utf-8"
        )

    result = analyze_python_project(tmp_path, max_files=2)

    assert result["files_scanned"] == 2
    assert result["files_analyzed"] == 2
    assert result["truncated"] is True
