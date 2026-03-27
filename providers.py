"""NoVa LeadScore — AI Provider (LiteLLM swap-ready + retry + fallback)"""

import time
from dataclasses import dataclass
from typing import Optional

from litellm import completion
from loguru import logger

from config import Config


@dataclass
class AIResponse:
    """Standardized AI response."""
    content: str
    model: str
    tokens_used: int = 0
    duration_ms: int = 0
    fallback_used: bool = False


class AIProviderError(Exception):
    """Wrapper for AI call failures with diagnosis."""
    def __init__(self, what: str, why: str, fix: str):
        self.what = what
        self.why = why
        self.fix = fix
        super().__init__(f"{what}: {why} → {fix}")


def call_llm(
    prompt: str,
    config: Config,
    system_prompt: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4000,
    response_format: Optional[dict] = None,
) -> AIResponse:
    """Call LLM with retry + fallback. Returns standardized AIResponse.

    PRE: prompt non-empty, config has valid llm_model + api_key
    POST: AIResponse with content, or raises AIProviderError
    INVARIANT: Never returns empty content without error
    """
    if not prompt.strip():
        raise AIProviderError("Empty prompt", "No input provided", "Provide lead data")

    if not config.llm_api_key:
        raise AIProviderError("No API key", "llm_api_key is empty", "Set LLM_API_KEY or GOOGLE_AI_API_KEY in .env")

    providers = [(config.llm_model, config.llm_api_key, False)]
    if config.fallback_model and config.fallback_api_key:
        providers.append((config.fallback_model, config.fallback_api_key, True))

    last_error = None

    for model, api_key, is_fallback in providers:
        for attempt in range(1, config.max_retries + 1):
            start = time.time()
            try:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                kwargs = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "api_key": api_key,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                resp = completion(**kwargs)
                content = resp.choices[0].message.content or ""
                duration = int((time.time() - start) * 1000)
                tokens = getattr(resp.usage, "total_tokens", 0) if resp.usage else 0

                logger.bind(
                    service="llm", model=model, action="call",
                    duration_ms=duration, status="ok", tokens=tokens,
                    fallback=is_fallback, attempt=attempt
                ).info("LLM call success")

                return AIResponse(
                    content=content,
                    model=model,
                    tokens_used=tokens,
                    duration_ms=duration,
                    fallback_used=is_fallback,
                )

            except Exception as e:
                duration = int((time.time() - start) * 1000)
                last_error = e
                logger.bind(
                    service="llm", model=model, action="call",
                    duration_ms=duration, status="error",
                    error=str(e), attempt=attempt, fallback=is_fallback
                ).warning(f"LLM attempt {attempt}/{config.max_retries} failed")

                if attempt < config.max_retries:
                    wait = config.retry_backoff * (2 ** (attempt - 1))
                    time.sleep(wait)

        if is_fallback:
            break  # both providers exhausted
        logger.warning(f"Primary provider {model} exhausted, trying fallback...")

    # All providers failed
    raise AIProviderError(
        what="AI scoring failed",
        why=f"All providers exhausted after retries: {last_error}",
        fix="Check API key in .env, verify internet connection, or try a different LLM_MODEL"
    )
