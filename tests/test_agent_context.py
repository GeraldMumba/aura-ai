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
