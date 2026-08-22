"""tests/test_llm_client.py — OpenAI互換クライアントの応答処理（打ち切り検出含む）のテスト"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_client import LLMClient, LLMResponseTruncatedError  # noqa: E402


def _completion(content: str, finish_reason: str = "stop") -> dict:
    return {
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": content}}]
    }


def _mock_post(payload: dict) -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class TestExtractMessageContent:
    def test_returns_content(self):
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        assert client._extract_message_content(_completion('{"positive": "cat"}')) == '{"positive": "cat"}'

    def test_no_choices_returns_none(self):
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        assert client._extract_message_content({"choices": []}) is None

    def test_length_finish_reason_raises(self):
        """max_tokens 到達で打ち切られた応答は、途中のJSONを返さず明示的に失敗させる"""
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        with pytest.raises(LLMResponseTruncatedError):
            client._extract_message_content(_completion('```json\n{"positive": "cat', finish_reason="length"))


class TestGenerateResponseTruncation:
    def test_generate_response_raises_on_truncation(self):
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        with patch("llm_client.requests.post", return_value=_mock_post(_completion("partial", "length"))):
            with pytest.raises(LLMResponseTruncatedError):
                client.generate_response("hello")

    def test_generate_response_with_image_raises_on_truncation(self, tmp_path):
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        with patch("llm_client.requests.post", return_value=_mock_post(_completion("partial", "length"))):
            with patch.object(LLMClient, "_encode_image_to_base64", return_value="AAAA"):
                with pytest.raises(LLMResponseTruncatedError):
                    client.generate_response_with_image("describe", b"fake-bytes")

    def test_generate_response_returns_content(self):
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        with patch("llm_client.requests.post", return_value=_mock_post(_completion("ok"))):
            assert client.generate_response("hello") == "ok"


class TestStreamTruncation:
    @staticmethod
    def _sse_response(lines: list[str]) -> MagicMock:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.iter_lines.return_value = iter(lines)
        response.__enter__ = lambda self: self
        response.__exit__ = lambda self, *args: False
        return response

    def test_stream_raises_after_truncated_finish(self):
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        lines = [
            'data: {"choices": [{"delta": {"content": "{\\"positive\\": "}}]}',
            'data: {"choices": [{"delta": {}, "finish_reason": "length"}]}',
            "data: [DONE]",
        ]
        with patch("llm_client.requests.post", return_value=self._sse_response(lines)):
            with pytest.raises(LLMResponseTruncatedError):
                list(client.generate_response_stream("hello"))

    def test_stream_yields_content_when_complete(self):
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        lines = [
            'data: {"choices": [{"delta": {"content": "he"}}]}',
            'data: {"choices": [{"delta": {"content": "llo"}, "finish_reason": "stop"}]}',
            "data: [DONE]",
        ]
        with patch("llm_client.requests.post", return_value=self._sse_response(lines)):
            assert list(client.generate_response_stream("hi")) == ["he", "llo"]
