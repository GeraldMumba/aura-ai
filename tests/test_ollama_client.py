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
