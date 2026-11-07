from app.ai import agent as agent_module
from app.ai.agent import AuraAgent


def test_workspace_context_retrieves_relevant_indexed_excerpt(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_module,
        "get_project_index_status",
        lambda root: {
            "workspace": str(root),
            "indexed_files": 4,
            "indexed_size_mb": 0.2,
        },
    )
    monkeypatch.setattr(
        agent_module,
        "search_project_index",
        lambda root, query, max_results, context_lines: {
            "results": [{
                "relative_path": "app/auth.py",
                "line": 12,
                "excerpt": "11: def authenticate_user():\n12:     validate_token()",
            }] if query == "authenticate" else [],
        },
    )

    context = AuraAgent._workspace_context(
        tmp_path, "Explain how authenticate works in this project"
    )

    assert "app/auth.py" in context
    assert "validate_token()" in context
    assert str(tmp_path) in context


def test_workspace_context_is_empty_when_index_has_no_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_module,
        "get_project_index_status",
        lambda root: {"workspace": str(root), "indexed_files": 0},
    )

    assert AuraAgent._workspace_context(tmp_path, "explain authentication") == ""


def test_workspace_context_failure_does_not_break_chat(monkeypatch, tmp_path):
    def fail(_root):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(agent_module, "get_project_index_status", fail)

    assert AuraAgent._workspace_context(tmp_path, "explain authentication") == ""



def test_project_understanding_context_reads_relevant_function_source(monkeypatch, tmp_path):
    import json

    calls = []

    def fake_execute_tool(name, arguments):
        calls.append((name, arguments))
        if name == "analyze_python_project":
            return json.dumps({
                "symbols": [
                    {
                        "file": "main.py", "name": "main",
                        "qualified_name": "main", "kind": "function",
                        "line": 100, "end_line": 110, "docstring": "",
                    },
                    {
                        "file": "main.py", "name": "authenticate_gmail",
                        "qualified_name": "authenticate_gmail", "kind": "function",
                        "line": 20, "end_line": 40, "docstring": "",
                    },
                    {
                        "file": "mail.py", "name": "format_message",
                        "qualified_name": "format_message", "kind": "function",
                        "line": 5, "end_line": 8, "docstring": "",
                    },
                ]
            })
        assert name == "read_text_file"
        return json.dumps({
            "content": f"source lines {arguments['start_line']}-{arguments['end_line']}"
        })

    monkeypatch.setattr(agent_module, "execute_tool", fake_execute_tool)

    context = AuraAgent._project_understanding_context(
        tmp_path, "Explain how this project authenticates each Gmail account"
    )

    assert "authenticate_gmail" in context
    assert "main" in context
    assert "source lines 20-40" in context
    assert "source lines 100-110" in context
    assert any(name == "analyze_python_project" for name, _ in calls)
    assert sum(name == "read_text_file" for name, _ in calls) == 2


def test_project_understanding_context_skips_unrelated_chat(tmp_path):
    assert AuraAgent._project_understanding_context(
        tmp_path, "Hello AURA, how are you?"
    ) == ""


def test_project_understanding_context_failure_does_not_break_chat(monkeypatch, tmp_path):
    def fail(*_args, **_kwargs):
        raise RuntimeError("analysis unavailable")

    monkeypatch.setattr(agent_module, "execute_tool", fail)

    assert AuraAgent._project_understanding_context(
        tmp_path, "Explain the authentication flow"
    ) == ""
