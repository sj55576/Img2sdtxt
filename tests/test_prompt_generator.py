"""tests/test_prompt_generator.py — PromptGenerator の JSON 抽出・パースロジックのテスト"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fallback import ProviderResponse
from llm_client import LLMClient
from prompt_generator import PromptGenerator


def _make_generator(response_text: str) -> PromptGenerator:
    """モック LLMClient を使って PromptGenerator を構築する"""
    client = MagicMock(spec=LLMClient)
    client.generate_response.return_value = response_text
    client.generate_response_with_image.return_value = response_text
    return PromptGenerator(client)


# ------------------------------------------------------------------ #
# _parse_json_response
# ------------------------------------------------------------------ #


class TestParseJsonResponse:
    def test_plain_json(self):
        gen = _make_generator("")
        raw = '{"positive": "cat, cute", "negative": "blurry"}'
        result = gen._parse_json_response(raw)
        assert result["positive"] == "cat, cute"
        assert result["negative"] == "blurry"

    def test_json_in_markdown_fences(self):
        gen = _make_generator("")
        raw = '```json\n{"positive": "dog", "negative": "bad"}\n```'
        result = gen._parse_json_response(raw)
        assert result["positive"] == "dog"

    def test_json_in_generic_fences(self):
        gen = _make_generator("")
        raw = '```\n{"positive": "sky", "negative": "low quality"}\n```'
        result = gen._parse_json_response(raw)
        assert result["positive"] == "sky"

    def test_json_with_surrounding_prose(self):
        """小型モデルが JSON の前後に説明文を付けても抽出できる"""
        gen = _make_generator("")
        raw = 'はい、生成しました。\n{"positive": "forest", "negative": "blurry"}\nご確認ください。'
        result = gen._parse_json_response(raw)
        assert result["positive"] == "forest"

    def test_json_in_unclosed_fence_with_prose(self):
        gen = _make_generator("")
        raw = 'Here you go:\n```json\n{"positive": "city, {night}", "negative": "text"}\nEnjoy!'
        result = gen._parse_json_response(raw)
        assert result["positive"] == "city, {night}"

    def test_malformed_json_raises(self):
        gen = _make_generator("")
        import pytest

        with pytest.raises(json.JSONDecodeError):
            gen._parse_json_response("not json at all")


# ------------------------------------------------------------------ #
# generate_prompts_text_only（モック LLM を使用）
# ------------------------------------------------------------------ #


class TestGeneratePromptsTextOnly:
    def test_success(self):
        response = '{"positive": "1girl, smiling", "negative": "blurry, low quality"}'
        gen = _make_generator(response)
        result = gen.generate_prompts_text_only("a happy anime girl")
        assert result["status"] == "success"
        assert "1girl" in result["positive"]

    def test_error_on_bad_json(self):
        gen = _make_generator("I cannot generate that.")
        result = gen.generate_prompts_text_only("description")
        assert result["status"] == "error"
        assert "error" in result

    def test_preset_suffix_appended(self):
        response = '{"positive": "cat", "negative": "bad"}'
        gen = _make_generator(response)
        result = gen.generate_prompts_text_only(
            "a cat", preset_suffix_positive="anime style", preset_suffix_negative="3d render"
        )
        assert "anime style" in result["positive"]
        assert "3d render" in result["negative"]


# ------------------------------------------------------------------ #
# generate_prompts（画像バイト使用、ビジョンモデル）
# ------------------------------------------------------------------ #


class TestGeneratePromptsFromImage:
    def _make_png_bytes(self) -> bytes:
        from io import BytesIO

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (1, 1), color=(0, 0, 0)).save(buf, format="PNG")
        return buf.getvalue()

    def test_success(self):
        response = '{"positive": "landscape, trees", "negative": "ugly"}'
        gen = _make_generator(response)
        result = gen.generate_prompts(self._make_png_bytes())
        assert result["status"] == "success"
        assert "landscape" in result["positive"]

    def test_no_response_returns_error(self):
        client = MagicMock(spec=LLMClient)
        client.generate_response_with_image.return_value = None
        gen = PromptGenerator(client)
        result = gen.generate_prompts(self._make_png_bytes())
        assert result["status"] == "error"

    def test_success_preserves_provider_metadata_from_fallback_response(self):
        client = MagicMock(spec=LLMClient)
        client.generate_response_with_image.return_value = ProviderResponse(
            '{"positive": "landscape", "negative": "blurry"}',
            "gemini",
            "gemini-test",
        )
        gen = PromptGenerator(client)

        result = gen.generate_prompts(self._make_png_bytes())

        assert result["provider"] == "gemini"
        assert result["model"] == "gemini-test"

    def test_blend_uses_one_contact_sheet_and_includes_roles(self):
        response = '{"positive": "hero, watercolor", "negative": "blurry"}'
        gen = _make_generator(response)
        result = gen.generate_blended_prompts(
            [self._make_png_bytes(), self._make_png_bytes()], ["subject", "background style"]
        )
        assert result["status"] == "success"
        prompt, contact_sheet = gen.llm_client.generate_response_with_image.call_args.args
        assert "subject" in prompt
        assert "background style" in prompt
        assert contact_sheet.startswith(b"\x89PNG")

    def test_blend_requires_matching_two_to_three_references(self):
        gen = _make_generator("{}")
        result = gen.generate_blended_prompts([self._make_png_bytes()], ["subject"])
        assert result["status"] == "error"


# ------------------------------------------------------------------ #
# refine_prompt
# ------------------------------------------------------------------ #


class TestRefinePrompt:
    def test_success(self):
        response = '{"positive": "refined positive", "negative": "refined negative", "changes": "added detail"}'
        gen = _make_generator(response)
        result = gen.refine_prompt(positive="original positive", negative="original negative")
        assert result["status"] == "success"
        assert result["positive"] == "refined positive"
        assert result["changes"] == "added detail"

    def test_error_returns_original(self):
        client = MagicMock(spec=LLMClient)
        client.generate_response.side_effect = Exception("LLM error")
        gen = PromptGenerator(client)
        result = gen.refine_prompt(positive="keep this", negative="keep neg")
        assert result["status"] == "error"
        # オリジナルの値がそのまま返される
        assert result["positive"] == "keep this"
