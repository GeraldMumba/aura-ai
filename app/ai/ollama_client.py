from __future__ import annotations

import os
from typing import Any

import requests


class OllamaError(RuntimeError):
    """Raised when Ollama cannot complete a request."""


class OllamaClient:
    """Small Ollama HTTP client supporting chat and native tool calling."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: tuple[int, int] = (5, 180),
    ) -> None:
        self.base_url = (base_url or os.getenv(
            "AURA_OLLAMA_URL", "http://127.0.0.1:11434"
        )).rstrip("/")
        self.model = model or os.getenv("AURA_MODEL", "llama3.2:3b")
        self.timeout = timeout
        self.session = requests.Session()

    def list_models(self) -> list[str]:
        try:
            response = self.session.get(
                f"{self.base_url}/api/tags", timeout=(5, 15)
            )
            response.raise_for_status()
            payload = response.json()
            return [
                item.get("name", "")
                for item in payload.get("models", [])
                if isinstance(item, dict) and item.get("name")
            ]
        except (requests.RequestException, ValueError) as exc:
            raise OllamaError(f"Could not reach Ollama: {exc}") from exc

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
        num_ctx: int = 2048,
        num_predict: int = 512,
    ) -> dict[str, Any]:
        """Return Ollama's complete /api/chat response, including tool_calls.

        This method is used by AURA's agent loop. Tool execution remains
        controlled by the application; this method only requests a response.
        """
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "5m",
            "options": {
                "num_ctx": max(512, min(int(num_ctx), 8192)),
                "num_predict": max(64, min(int(num_predict), 2048)),
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("message"), dict):
                raise OllamaError("Ollama returned an invalid chat response.")
            return data
        except requests.Timeout as exc:
            raise OllamaError(
                "Ollama took too long to respond. Try a smaller model or shorter prompt."
            ) from exc
        except requests.RequestException as exc:
            raise OllamaError(
                f"Could not complete the Ollama request: {exc}"
            ) from exc
        except ValueError as exc:
            raise OllamaError("Ollama returned invalid JSON.") from exc

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        num_ctx: int = 2048,
        num_predict: int = 512,
    ) -> str:
        """Send a normal chat request and return assistant text."""
        result = self.chat_completion(
            messages,
            model=model,
            num_ctx=num_ctx,
            num_predict=num_predict,
        )
        content = result.get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama returned an empty response.")
        return content.strip()
