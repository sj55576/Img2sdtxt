"""Shared request-value validators for style / tone / quality."""

from fastapi import HTTPException

from config import QUALITY_LEVELS, STYLES, TONES

STYLE_ERROR = f"Invalid style. Must be one of {STYLES}."
TONE_ERROR = f"Invalid tone. Must be one of {TONES}."
QUALITY_ERROR = f"Invalid quality. Must be one of {list(QUALITY_LEVELS.keys())}."


def is_valid_style(value: str) -> bool:
    """Empty string ("unspecified") is always allowed; otherwise must be in STYLES."""
    return value == "" or value in STYLES


def is_valid_tone(value: str) -> bool:
    """Empty string ("unspecified") is always allowed; otherwise must be in TONES."""
    return value == "" or value in TONES


def is_valid_quality(value: str) -> bool:
    """Empty string ("unspecified"/default) is always allowed; otherwise must be a known quality level."""
    return value == "" or value in QUALITY_LEVELS


def validate_style(value: str) -> str:
    """Raise HTTPException(400) if ``value`` is not an allowed style; otherwise return it unchanged."""
    if not is_valid_style(value):
        raise HTTPException(status_code=400, detail=STYLE_ERROR)
    return value


def validate_tone(value: str) -> str:
    """Raise HTTPException(400) if ``value`` is not an allowed tone; otherwise return it unchanged."""
    if not is_valid_tone(value):
        raise HTTPException(status_code=400, detail=TONE_ERROR)
    return value


def validate_quality(value: str) -> str:
    """Raise HTTPException(400) if ``value`` is not an allowed quality level; otherwise return it unchanged."""
    if not is_valid_quality(value):
        raise HTTPException(status_code=400, detail=QUALITY_ERROR)
    return value
