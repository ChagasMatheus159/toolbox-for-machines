"""LLM client with concurrency control for the Toolbox."""

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI

from toolbox.config import settings

log = logging.getLogger("toolbox.llm")

# Semaphore to limit concurrent LLM requests
_semaphore = asyncio.Semaphore(settings.llm_max_concurrent)

# Shared async OpenAI client
_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Get or create the shared OpenAI-compatible async client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.llm_url,
            api_key=settings.llm_api_key or "not-needed",
            timeout=settings.llm_timeout_seconds,
        )
    return _client


async def chat(
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float = 0.1,
    response_format: dict | None = None,
) -> str:
    """Send a chat completion request to the LLM with concurrency control.

    Args:
        messages: OpenAI-format messages list.
        max_tokens: Max output tokens (defaults to settings.llm_max_tokens).
        temperature: Sampling temperature (low for deterministic output).
        response_format: Optional response format constraint (e.g. {"type": "json_object"}).

    Returns:
        The assistant's response text.

    Raises:
        Exception: On timeout, OOM, or other LLM errors.
    """
    client = get_client()
    max_tokens = max_tokens or settings.llm_max_tokens

    async with _semaphore:
        log.debug("LLM request: %d messages, max_tokens=%d", len(messages), max_tokens)
        kwargs: dict[str, Any] = {
            "model": settings.llm_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format

        try:
            response = await client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            log.debug("LLM response: %d chars", len(content))
            return content.strip()
        except Exception as e:
            log.error("LLM request failed: %s", e)
            raise
