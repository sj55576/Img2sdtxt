"""Shared application dependencies and helper utilities."""

import io
import logging
import threading
from typing import Optional

from fastapi import HTTPException
from PIL import Image

import config
from cache import LLMCache
from llm_client import LLMClient
from llm_provider import LLMProvider
from prompt_generator import PromptGenerator
from sd_client import SDClient

logger = logging.getLogger("img2sdtxt.deps")

_provider_lock = threading.Lock()


def create_llm_provider(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMProvider:
    """Create an LLM provider instance based on configuration."""
    provider = provider or config.LLM_PROVIDER

    if provider == "anthropic":
        from providers.anthropic_provider import AnthropicProvider

        key = api_key or config.ANTHROPIC_API_KEY
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required for Anthropic provider")
        mdl = model or config.ANTHROPIC_MODEL
        return AnthropicProvider(api_key=key, model=mdl)

    elif provider == "gemini":
        from providers.gemini_provider import GeminiProvider

        key = api_key or config.GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY is required for Gemini provider")
        mdl = model or config.GEMINI_MODEL
        return GeminiProvider(api_key=key, model=mdl)

    else:
        base_url = config.LLM_SERVER_URL
        mdl = model or config.LLM_MODEL
        return LLMClient(base_url=base_url, model=mdl)


llm_client: LLMProvider = create_llm_provider()
prompt_generator = PromptGenerator(llm_client)
sd_client = SDClient()
llm_cache = LLMCache(ttl_seconds=config.LLM_CACHE_TTL, enabled=config.LLM_CACHE_ENABLED)


def switch_provider(
    provider: str,
    model: str = "",
    api_key: str = "",
) -> LLMProvider:
    """Switch the active LLM provider at runtime. Thread-safe."""
    global llm_client, prompt_generator

    new_provider = create_llm_provider(
        provider=provider,
        model=model or None,
        api_key=api_key or None,
    )

    with _provider_lock:
        llm_client = new_provider
        prompt_generator = PromptGenerator(new_provider)

    logger.info(
        "Switched LLM provider to %s (model=%s)",
        new_provider.provider_name,
        new_provider.model,
    )
    return new_provider


def get_available_providers() -> list:
    """Return list of provider info dicts with availability status."""
    providers = [
        {
            "id": "openai_compatible",
            "name": "OpenAI Compatible (LM Studio / Ollama)",
            "configured": True,
            "requires_api_key": False,
            "server_url": config.LLM_SERVER_URL,
        },
        {
            "id": "anthropic",
            "name": "Anthropic Claude",
            "configured": bool(config.ANTHROPIC_API_KEY),
            "requires_api_key": True,
            "default_model": config.ANTHROPIC_MODEL,
        },
        {
            "id": "gemini",
            "name": "Google Gemini",
            "configured": bool(config.GEMINI_API_KEY),
            "requires_api_key": True,
            "default_model": config.GEMINI_MODEL,
        },
    ]
    return providers


def _as_int(data: dict, key: str, default: int) -> int:
    """Extract an int value from a dict; raise HTTPException 422 on failure."""
    val = data.get(key, default)
    try:
        return int(val)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"Parameter '{key}' must be an integer, got: {val!r}"
        )


def _as_float(data: dict, key: str, default: float) -> float:
    """Extract a float value from a dict; raise HTTPException 422 on failure."""
    val = data.get(key, default)
    try:
        return float(val)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=422,
            detail=f"Parameter '{key}' must be a number, got: {val!r}"
        )


def _validate_image_bytes(data: bytes) -> str:
    """Validate image bytes with PIL; raise HTTPException 400 if invalid."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        return "ok"
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}")
