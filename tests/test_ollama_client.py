from unittest.mock import Mock

import requests

from app.ai.ollama_client import OllamaClient, OllamaError


def test_chat_returns_assistant_content():
    client = OllamaClient()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"message": {"content": "Hello from AURA"}}
    client.session.post = Mock(return_value=response)

    result = client.chat([{"role": "user", "content": "Hello"}])

    assert result == "Hello from AURA"
    client.session.post.assert_called_once()


def test_chat_reports_connection_error():
    client = OllamaClient()
    client.session.post = Mock(
        side_effect=requests.ConnectionError("connection refused")
    )

    try:
        client.chat([{"role": "user", "content": "Hello"}])
    except OllamaError as exc:
        assert "Could not complete" in str(exc)
    else:
        raise AssertionError("Expected OllamaError")


def test_chat_rejects_empty_response():
    client = OllamaClient()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"message": {"content": ""}}
    client.session.post = Mock(return_value=response)

    try:
        client.chat([{"role": "user", "content": "Hello"}])
    except OllamaError as exc:
        assert "empty response" in str(exc)
    else:
        raise AssertionError("Expected OllamaError")


def test_chat_completion_preserves_tool_calls_and_sends_tools():
    client = OllamaClient()
    tools = [{
        "type": "function",
        "function": {
            "name": "read_text_file",
            "description": "Read a text file",
            "parameters": {"type": "object", "properties": {}},
        },
    }]
    tool_calls = [{
        "function": {
            "name": "read_text_file",
            "arguments": {"path": "/tmp/example.py"},
        }
    }]
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "message": {"role": "assistant", "content": "", "tool_calls": tool_calls}
    }
    client.session.post = Mock(return_value=response)

    result = client.chat_completion(
        [{"role": "user", "content": "Read this file"}],
        tools=tools,
        num_predict=180,
    )

    assert result["message"]["tool_calls"] == tool_calls
    payload = client.session.post.call_args.kwargs["json"]
    assert payload["tools"] == tools
    assert payload["stream"] is False
    assert payload["options"]["num_predict"] == 180


def test_chat_completion_rejects_invalid_response_shape():
    client = OllamaClient()
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"unexpected": True}
    client.session.post = Mock(return_value=response)

    try:
        client.chat_completion([{"role": "user", "content": "Hello"}])
    except OllamaError as exc:
        assert "invalid chat response" in str(exc)
    else:
        raise AssertionError("Expected OllamaError")
