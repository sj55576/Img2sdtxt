"""Google Gemini LLM provider implementation."""

import logging
import time
from io import BytesIO
from typing import Optional

import google.generativeai as genai
from PIL import Image

from llm_provider import LLMProvider
from retry import retry_with_backoff

logger = logging.getLogger("img2sdtxt.gemini")

_SYSTEM_PROMPT = "あなたはStable Diffusionのプロンプト生成の専門家です。"


class GeminiProvider(LLMProvider):
    """LLM provider backed by Google Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        genai.configure(api_key=api_key)
        self._model_name = model
        self._model = genai.GenerativeModel(
            model_name=model,
            system_instruction=_SYSTEM_PROMPT,
        )

    # ------------------------------------------------------------------
    # Abstract property implementations
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model(self) -> str:
        return self._model_name

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    @retry_with_backoff(max_retries=1, base_delay=0.5)
    def is_available(self) -> bool:
        """Check connectivity by listing models; returns True if at least one model is reachable."""
        try:
            for _ in genai.list_models():
                return True
            return True
        except Exception as e:
            logger.warning("Gemini availability check failed: %s", e)
            return False

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """Send a text prompt to Gemini and return the generated text."""
        logger.debug("generate_response model=%s", self._model_name)
        t0 = time.time()
        try:
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.7,
                top_p=0.9,
            )
            response = self._model.generate_content(
                prompt,
                generation_config=generation_config,
            )
            elapsed = (time.time() - t0) * 1000
            logger.info("Gemini call succeeded model=%s %.0fms", self._model_name, elapsed)
            return response.text
        except ConnectionError:
            logger.error("Cannot connect to Gemini API model=%s", self._model_name)
            raise
        except TimeoutError:
            logger.error("Gemini request timed out model=%s", self._model_name)
            raise
        except Exception as e:
            logger.error("Gemini API error: %s", str(e))
            raise Exception(f"Gemini API error: {str(e)}")

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def generate_response_with_image(
        self,
        prompt: str,
        image_bytes: bytes,
        max_tokens: int = 500,
    ) -> Optional[str]:
        """Send a prompt with an image to Gemini and return the generated text."""
        logger.debug(
            "generate_response_with_image model=%s image_bytes=%d",
            self._model_name,
            len(image_bytes),
        )
        t0 = time.time()
        try:
            image = Image.open(BytesIO(image_bytes))
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.7,
                top_p=0.9,
            )
            response = self._model.generate_content(
                [prompt, image],
                generation_config=generation_config,
            )
            elapsed = (time.time() - t0) * 1000
            logger.info(
                "Gemini vision call succeeded model=%s %.0fms",
                self._model_name,
                elapsed,
            )
            return response.text
        except ConnectionError:
            logger.error("Cannot connect to Gemini API model=%s", self._model_name)
            raise
        except TimeoutError:
            logger.error("Gemini vision request timed out model=%s", self._model_name)
            raise
        except Exception as e:
            logger.error("Gemini API error: %s", str(e))
            raise Exception(f"Gemini API error: {str(e)}")

    def supports_vision(self) -> bool:
        return True
