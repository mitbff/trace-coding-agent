from __future__ import annotations

from typing import Any, Protocol

from openai import OpenAI


class ModelClient(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any: ...


class OpenAIModelClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 90.0,
        max_retries: int = 2,
    ) -> None:
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.model = model

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        return response.choices[0].message
