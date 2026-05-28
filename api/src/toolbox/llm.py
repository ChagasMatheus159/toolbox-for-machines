"""LLM client with concurrency control and retry for the Toolbox."""

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI, RateLimitError, APIStatusError, APITimeoutError

from toolbox.config import settings

log = logging.getLogger("toolbox.llm")

# Semaphore to limit concurrent LLM requests
_semaphore = asyncio.Semaphore(settings.llm_max_concurrent)

# Shared async OpenAI client
_client: AsyncOpenAI | None = None

# Retry config
MAX_RETRIES = 2
RETRY_BACKOFF = [2, 4]  # seconds between retries


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

    Retries on 429 (rate limit) and 5xx errors with exponential backoff.
    Fails immediately on timeouts and 4xx (except 429).

    Args:
        messages: OpenAI-format messages list.
        max_tokens: Max output tokens (defaults to settings.llm_max_tokens).
        temperature: Sampling temperature (low for deterministic output).
        response_format: Optional response format constraint (e.g. {"type": "json_object"}).

    Returns:
        The assistant's response text.

    Raises:
        Exception: On timeout, client errors, or exhausted retries.
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

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = await client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                log.debug("LLM response: %d chars", len(content))
                return content.strip()
            except APITimeoutError:
                # Timeout — fail immediately, no point retrying
                log.error("LLM request timed out (attempt %d)", attempt + 1)
                raise
            except RateLimitError as e:
                # 429 — retry with backoff
                last_error = e
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt]
                    log.warning("LLM rate limited (429), retrying in %ds (attempt %d/%d)", wait, attempt + 1, MAX_RETRIES + 1)
                    await asyncio.sleep(wait)
                else:
                    log.error("LLM rate limited, retries exhausted")
                    raise
            except APIStatusError as e:
                # 5xx — retry; 4xx (except 429) — fail immediately
                if e.status_code >= 500:
                    last_error = e
                    if attempt < MAX_RETRIES:
                        wait = RETRY_BACKOFF[attempt]
                        log.warning("LLM server error (%d), retrying in %ds (attempt %d/%d)", e.status_code, wait, attempt + 1, MAX_RETRIES + 1)
                        await asyncio.sleep(wait)
                    else:
                        log.error("LLM server error (%d), retries exhausted", e.status_code)
                        raise
                else:
                    # 4xx client error — fail immediately
                    log.error("LLM client error (%d): %s", e.status_code, e)
                    raise
            except Exception as e:
                # Unknown error — fail immediately
                log.error("LLM request failed: %s", e)
                raise

        # Should not reach here, but just in case
        raise last_error or RuntimeError("LLM request failed")
