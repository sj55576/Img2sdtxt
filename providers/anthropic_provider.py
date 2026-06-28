"""Anthropic Claude LLM provider implementation."""

import base64
import logging
import time
from typing import Optional

import anthropic

from llm_provider import LLMProvider
from retry import retry_with_backoff

logger = logging.getLogger("img2sdtxt.anthropic")

SYSTEM_PROMPT = "あなたはStable Diffusionのプロンプト生成の専門家です。"

# Magic bytes for image format detection
_PNG_MAGIC = b"\x89PNG"
_JPEG_MAGIC = b"\xff\xd8\xff"
_GIF_MAGIC = (b"GIF87a", b"GIF89a")
_WEBP_MAGIC_RIFF = b"RIFF"
_WEBP_MAGIC_WEBP = b"WEBP"


def _detect_media_type(image_bytes: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if image_bytes[:4] == _PNG_MAGIC:
        return "image/png"
    if image_bytes[:3] == _JPEG_MAGIC:
        return "image/jpeg"
    if image_bytes[:6] in _GIF_MAGIC:
        return "image/gif"
    if image_bytes[:4] == _WEBP_MAGIC_RIFF and image_bytes[8:12] == _WEBP_MAGIC_WEBP:
        return "image/webp"
    # Default to JPEG for unknown formats
    return "image/jpeg"


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._model = model
        self.client = anthropic.Anthropic(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def supports_vision(self) -> bool:
        return True

    @retry_with_backoff(max_retries=1, base_delay=0.5)
    def is_available(self) -> bool:
        """Check connectivity by listing one model (5 s timeout)."""
        try:
            with anthropic.Anthropic(
                api_key=self.client.api_key,
                timeout=5.0,
            ) as client:
                client.models.list(limit=1)
            return True
        except anthropic.APIConnectionError:
            logger.warning("Anthropic API connection check failed")
            return False
        except anthropic.APITimeoutError:
            logger.warning("Anthropic API connection check timed out")
            return False
        except Exception as e:
            logger.warning("Anthropic API availability check error: %s", e)
            return False

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """Send a text prompt and return the generated response."""
        logger.debug("generate_response model=%s", self._model)
        t0 = time.time()
        try:
            response = self.client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                top_p=0.9,
            )
            elapsed = (time.time() - t0) * 1000
            logger.info("Anthropic call succeeded model=%s %.0fms", self._model, elapsed)
            return response.content[0].text
        except anthropic.APIConnectionError:
            logger.error("Cannot connect to Anthropic API")
            raise ConnectionError("Cannot connect to Anthropic API")
        except anthropic.APITimeoutError:
            logger.error("Anthropic API request timed out model=%s", self._model)
            raise TimeoutError("Anthropic API request timed out")
        except Exception as e:
            logger.error("Anthropic API error: %s", str(e))
            raise Exception(f"Anthropic API error: {str(e)}")

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def generate_response_with_image(
        self, prompt: str, image_bytes: bytes, max_tokens: int = 500
    ) -> Optional[str]:
        """Send an image + text prompt and return the generated response."""
        logger.debug(
            "generate_response_with_image model=%s image_bytes=%d",
            self._model,
            len(image_bytes),
        )
        t0 = time.time()
        try:
            media_type = _detect_media_type(image_bytes)
            base64_data = base64.b64encode(image_bytes).decode("utf-8")

            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_data,
                    },
                },
                {"type": "text", "text": prompt},
            ]

            response = self.client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                temperature=0.7,
                top_p=0.9,
                timeout=60,
            )
            elapsed = (time.time() - t0) * 1000
            logger.info(
                "Anthropic vision call succeeded model=%s %.0fms", self._model, elapsed
            )
            return response.content[0].text
        except anthropic.APIConnectionError:
            logger.error("Cannot connect to Anthropic API")
            raise ConnectionError("Cannot connect to Anthropic API")
        except anthropic.APITimeoutError:
            logger.error(
                "Anthropic API vision request timed out model=%s", self._model
            )
            raise TimeoutError(
                "Anthropic API request timed out (vision analysis may take longer)"
            )
        except Exception as e:
            logger.error("Anthropic API error: %s", str(e))
            raise Exception(f"Anthropic API error: {str(e)}")
