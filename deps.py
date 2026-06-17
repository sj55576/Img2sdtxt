"""Shared application dependencies and helper utilities."""

import io
from fastapi import HTTPException
from PIL import Image

import config
from llm_client import LLMClient
from prompt_generator import PromptGenerator
from sd_client import SDClient
from cache import LLMCache

llm_client = LLMClient()
prompt_generator = PromptGenerator(llm_client)
sd_client = SDClient()
llm_cache = LLMCache(ttl_seconds=config.LLM_CACHE_TTL, enabled=config.LLM_CACHE_ENABLED)


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
