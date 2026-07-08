"""tests/test_providers.py — LLM provider interface and factory tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cache as _cache_module
from cache import LLMCache
from llm_client import LLMClient
from llm_provider import LLMProvider
from models import SwitchProviderRequest


@pytest.fixture()
def temp_cache_db(tmp_path, monkeypatch):
    """Redirect cache DB_PATH to a temp file so tests don't touch data/."""
    db_file = tmp_path / "test_llm_cache.db"
    monkeypatch.setattr(_cache_module, "DB_PATH", db_file)
    yield db_file


# ------------------------------------------------------------------ #
# LLMProvider ABC
# ------------------------------------------------------------------ #


class TestLLMProviderABC:
    def test_cannot_instantiate_directly(self):
        """LLMProvider is abstract and must not be instantiable."""
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]


# ------------------------------------------------------------------ #
# LLMClient inherits LLMProvider
# ------------------------------------------------------------------ #


class TestLLMClientInterface:
    def _make_client(self) -> LLMClient:
        return LLMClient(base_url="http://localhost:1234", model="test-model")

    def test_is_llm_provider_subclass(self):
        assert issubclass(LLMClient, LLMProvider)

    def test_provider_name(self):
        client = self._make_client()
        assert client.provider_name == "openai_compatible"

    def test_model_returns_configured_model(self):
        client = self._make_client()
        assert client.model == "test-model"

    def test_base_url_is_normalized_for_endpoint_and_health_check(self):
        client = LLMClient(base_url="http://localhost:1234/v1/", model="test-model")
        assert client.base_url == "http://localhost:1234/v1"
        assert client.endpoint == "http://localhost:1234/v1/chat/completions"

    @patch("llm_client.requests.get")
    def test_is_available_checks_models_under_configured_base_url(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        client = LLMClient(base_url="http://localhost:1234/v1", model="test-model")
        assert client.is_available() is True
        mock_get.assert_called_once_with("http://localhost:1234/v1/models", timeout=5)

    def test_supports_vision_returns_true(self):
        client = self._make_client()
        assert client.supports_vision() is True


# ------------------------------------------------------------------ #
# AnthropicProvider
# ------------------------------------------------------------------ #


class TestAnthropicProvider:
    """Tests for AnthropicProvider that mock the anthropic SDK."""

    def _make_provider(self, mock_anthropic_cls):
        """Create an AnthropicProvider with a mocked Anthropic client."""
        from providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key="test-key", model="claude-test-model")

    def test_provider_name(self):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from providers.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(api_key="test-key", model="claude-test-model")
            assert provider.provider_name == "anthropic"

    def test_model_returns_configured_model(self):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from providers.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(api_key="test-key", model="claude-test-model")
            assert provider.model == "claude-test-model"

    def test_supports_vision_returns_true(self):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            from providers.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(api_key="test-key", model="claude-test-model")
            assert provider.supports_vision() is True

    def test_generate_response_calls_sdk_and_returns_text(self):
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            # Set up a realistic response shape
            from anthropic.types import TextBlock

            mock_content = TextBlock(type="text", text="generated text")
            mock_client.messages.create.return_value = MagicMock(content=[mock_content])

            from providers.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(api_key="test-key", model="claude-test-model")
            result = provider.generate_response("test prompt", max_tokens=100)

            assert result == "generated text"
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["model"] == "claude-test-model"
            assert call_kwargs["max_tokens"] == 100

    def test_generate_response_with_image_calls_sdk_with_image_content(self):
        from io import BytesIO

        from PIL import Image

        # Build a small valid PNG
        buf = BytesIO()
        Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
        image_bytes = buf.getvalue()

        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            from anthropic.types import TextBlock

            mock_content = TextBlock(type="text", text="image description")
            mock_client.messages.create.return_value = MagicMock(content=[mock_content])

            from providers.anthropic_provider import AnthropicProvider

            provider = AnthropicProvider(api_key="test-key", model="claude-test-model")
            result = provider.generate_response_with_image("describe this", image_bytes, max_tokens=200)

            assert result == "image description"
            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            # The messages should contain image + text content blocks
            messages = call_kwargs["messages"]
            assert len(messages) == 1
            content = messages[0]["content"]
            types = [block["type"] for block in content]
            assert "image" in types
            assert "text" in types


# ------------------------------------------------------------------ #
# GeminiProvider
# ------------------------------------------------------------------ #


class TestGeminiProvider:
    """Tests for GeminiProvider that mock the google.generativeai SDK."""

    def test_provider_name(self):
        with patch("google.generativeai.configure"), patch("google.generativeai.GenerativeModel") as mock_model_cls:
            mock_model_cls.return_value = MagicMock()
            from providers.gemini_provider import GeminiProvider

            provider = GeminiProvider(api_key="test-key", model="gemini-test-model")
            assert provider.provider_name == "gemini"

    def test_model_returns_configured_model(self):
        with patch("google.generativeai.configure"), patch("google.generativeai.GenerativeModel") as mock_model_cls:
            mock_model_cls.return_value = MagicMock()
            from providers.gemini_provider import GeminiProvider

            provider = GeminiProvider(api_key="test-key", model="gemini-test-model")
            assert provider.model == "gemini-test-model"

    def test_supports_vision_returns_true(self):
        with patch("google.generativeai.configure"), patch("google.generativeai.GenerativeModel") as mock_model_cls:
            mock_model_cls.return_value = MagicMock()
            from providers.gemini_provider import GeminiProvider

            provider = GeminiProvider(api_key="test-key", model="gemini-test-model")
            assert provider.supports_vision() is True

    def test_generate_response_calls_sdk_and_returns_text(self):
        with (
            patch("google.generativeai.configure"),
            patch("google.generativeai.GenerativeModel") as mock_model_cls,
            patch("google.generativeai.types.GenerationConfig"),
        ):
            mock_model_instance = MagicMock()
            mock_model_cls.return_value = mock_model_instance

            mock_response = MagicMock()
            mock_response.text = "gemini response text"
            mock_model_instance.generate_content.return_value = mock_response

            from providers.gemini_provider import GeminiProvider

            provider = GeminiProvider(api_key="test-key", model="gemini-test-model")
            result = provider.generate_response("test prompt", max_tokens=100)

            assert result == "gemini response text"
            mock_model_instance.generate_content.assert_called_once()
            call_args = mock_model_instance.generate_content.call_args
            # First positional arg should be the prompt string
            assert call_args[0][0] == "test prompt"

    def test_generate_response_with_image_calls_sdk_with_image_content(self):
        from io import BytesIO

        from PIL import Image as PILImage

        buf = BytesIO()
        PILImage.new("RGB", (1, 1), color=(0, 255, 0)).save(buf, format="PNG")
        image_bytes = buf.getvalue()

        with (
            patch("google.generativeai.configure"),
            patch("google.generativeai.GenerativeModel") as mock_model_cls,
            patch("google.generativeai.types.GenerationConfig"),
        ):
            mock_model_instance = MagicMock()
            mock_model_cls.return_value = mock_model_instance

            mock_response = MagicMock()
            mock_response.text = "gemini vision response"
            mock_model_instance.generate_content.return_value = mock_response

            from providers.gemini_provider import GeminiProvider

            provider = GeminiProvider(api_key="test-key", model="gemini-test-model")
            result = provider.generate_response_with_image("describe", image_bytes, max_tokens=150)

            assert result == "gemini vision response"
            mock_model_instance.generate_content.assert_called_once()
            call_args = mock_model_instance.generate_content.call_args
            # First positional arg should be a list [prompt, PIL_image]
            content_list = call_args[0][0]
            assert isinstance(content_list, list)
            assert len(content_list) == 2
            assert content_list[0] == "describe"


# ------------------------------------------------------------------ #
# create_llm_provider factory (from deps.py)
# ------------------------------------------------------------------ #


class TestCreateLLMProviderFactory:
    """Tests for the create_llm_provider factory function in deps.py."""

    def test_default_returns_llm_client(self):
        with (
            patch("config.LLM_PROVIDER", "openai_compatible"),
            patch("config.LLM_SERVER_URL", "http://localhost:1234"),
            patch("config.LLM_MODEL", "default-model"),
        ):
            from deps import create_llm_provider

            provider = create_llm_provider(provider="openai_compatible")
            assert isinstance(provider, LLMClient)

    def test_anthropic_with_api_key_returns_anthropic_provider(self):
        with patch("anthropic.Anthropic") as mock_cls, patch("config.ANTHROPIC_MODEL", "claude-sonnet-4-20250514"):
            mock_cls.return_value = MagicMock()
            from deps import create_llm_provider
            from providers.anthropic_provider import AnthropicProvider

            provider = create_llm_provider(provider="anthropic", api_key="test-key")
            assert isinstance(provider, AnthropicProvider)

    def test_gemini_with_api_key_returns_gemini_provider(self):
        with (
            patch("google.generativeai.configure"),
            patch("google.generativeai.GenerativeModel") as mock_model_cls,
            patch("config.GEMINI_MODEL", "gemini-2.5-flash"),
        ):
            mock_model_cls.return_value = MagicMock()
            from deps import create_llm_provider
            from providers.gemini_provider import GeminiProvider

            provider = create_llm_provider(provider="gemini", api_key="test-key")
            assert isinstance(provider, GeminiProvider)

    def test_anthropic_without_api_key_raises_value_error(self):
        with patch("config.ANTHROPIC_API_KEY", ""), patch("config.ANTHROPIC_MODEL", "claude-sonnet-4-20250514"):
            from deps import create_llm_provider

            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                create_llm_provider(provider="anthropic", api_key=None)

    def test_gemini_without_api_key_raises_value_error(self):
        with patch("config.GEMINI_API_KEY", ""), patch("config.GEMINI_MODEL", "gemini-2.5-flash"):
            from deps import create_llm_provider

            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                create_llm_provider(provider="gemini", api_key=None)


# ------------------------------------------------------------------ #
# SwitchProviderRequest Pydantic model
# ------------------------------------------------------------------ #


class TestSwitchProviderRequest:
    def test_requires_provider_field(self):
        with pytest.raises(Exception):
            SwitchProviderRequest()  # type: ignore[call-arg]

    def test_provider_only(self):
        req = SwitchProviderRequest(provider="anthropic")
        assert req.provider == "anthropic"
        assert req.model == ""
        assert req.api_key == ""

    def test_all_fields(self):
        req = SwitchProviderRequest(provider="gemini", model="gemini-2.5-flash", api_key="key123")
        assert req.provider == "gemini"
        assert req.model == "gemini-2.5-flash"
        assert req.api_key == "key123"

    def test_model_and_api_key_optional_with_defaults(self):
        req = SwitchProviderRequest(provider="openai_compatible")
        assert req.model == ""
        assert req.api_key == ""


# ------------------------------------------------------------------ #
# Cache key includes provider and model
# ------------------------------------------------------------------ #


class TestCacheKeyIncludesProvider:
    def test_different_providers_produce_different_keys(self, temp_cache_db):
        cache = LLMCache()
        key_a = cache._make_key(None, "hello", "anime", "dark", "high", provider="anthropic", model="claude-3")
        key_b = cache._make_key(None, "hello", "anime", "dark", "high", provider="gemini", model="claude-3")
        assert key_a != key_b

    def test_different_models_produce_different_keys(self, temp_cache_db):
        cache = LLMCache()
        key_a = cache._make_key(None, "hello", "anime", "dark", "high", provider="anthropic", model="model-a")
        key_b = cache._make_key(None, "hello", "anime", "dark", "high", provider="anthropic", model="model-b")
        assert key_a != key_b

    def test_same_inputs_produce_same_key(self, temp_cache_db):
        cache = LLMCache()
        key_a = cache._make_key(b"img", "hello", "anime", "dark", "high", provider="gemini", model="gemini-2.5-flash")
        key_b = cache._make_key(b"img", "hello", "anime", "dark", "high", provider="gemini", model="gemini-2.5-flash")
        assert key_a == key_b

    def test_empty_provider_and_model_are_valid(self, temp_cache_db):
        cache = LLMCache()
        key = cache._make_key(None, "text", "style", "tone", "quality")
        assert isinstance(key, str)
        assert len(key) == 64  # sha256 hex digest length

    def test_get_and_set_pass_through_provider_model(self, temp_cache_db):
        cache = LLMCache()
        result_data = {"positive": "flowers", "negative": "blurry"}

        cache.set(None, "flowers", "anime", "bright", "high", result_data, provider="anthropic", model="claude-3")

        # Same key should hit
        hit = cache.get(None, "flowers", "anime", "bright", "high", provider="anthropic", model="claude-3")
        assert hit == result_data

        # Different provider should miss
        miss = cache.get(None, "flowers", "anime", "bright", "high", provider="gemini", model="claude-3")
        assert miss is None
