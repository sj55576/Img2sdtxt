"""tests/test_validators.py — style / tone / quality の共有バリデータのテスト"""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import validators
from config import QUALITY_LEVELS, STYLES, TONES

# ------------------------------------------------------------------ #
# is_valid_* — 例外を投げない純粋な述語関数
# ------------------------------------------------------------------ #


def test_is_valid_style_accepts_known_values():
    for style in STYLES:
        assert validators.is_valid_style(style) is True


def test_is_valid_style_accepts_empty_string():
    assert validators.is_valid_style("") is True


def test_is_valid_style_rejects_unknown_value():
    assert validators.is_valid_style("not_a_real_style") is False


def test_is_valid_tone_accepts_known_values():
    for tone in TONES:
        assert validators.is_valid_tone(tone) is True


def test_is_valid_tone_accepts_empty_string():
    assert validators.is_valid_tone("") is True


def test_is_valid_tone_rejects_unknown_value():
    assert validators.is_valid_tone("not_a_real_tone") is False


def test_is_valid_quality_accepts_known_values():
    for quality in QUALITY_LEVELS:
        assert validators.is_valid_quality(quality) is True


def test_is_valid_quality_accepts_empty_string():
    assert validators.is_valid_quality("") is True


def test_is_valid_quality_rejects_unknown_value():
    assert validators.is_valid_quality("not_a_real_quality") is False


# ------------------------------------------------------------------ #
# validate_* — HTTPException(400) を投げる版
# ------------------------------------------------------------------ #


def test_validate_style_returns_value_when_valid():
    assert validators.validate_style("anime") == "anime"


def test_validate_style_returns_empty_string_unchanged():
    assert validators.validate_style("") == ""


def test_validate_style_raises_400_for_invalid_value():
    with pytest.raises(HTTPException) as exc_info:
        validators.validate_style("not_a_real_style")
    assert exc_info.value.status_code == 400
    assert "style" in exc_info.value.detail.lower()


def test_validate_tone_raises_400_for_invalid_value():
    with pytest.raises(HTTPException) as exc_info:
        validators.validate_tone("not_a_real_tone")
    assert exc_info.value.status_code == 400
    assert "tone" in exc_info.value.detail.lower()


def test_validate_quality_returns_value_when_valid():
    for quality in QUALITY_LEVELS:
        assert validators.validate_quality(quality) == quality


def test_validate_quality_raises_400_for_invalid_value():
    with pytest.raises(HTTPException) as exc_info:
        validators.validate_quality("not_a_real_quality")
    assert exc_info.value.status_code == 400
    assert "quality" in exc_info.value.detail.lower()
