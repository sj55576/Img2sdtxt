import base64
import json
import logging
import time
from io import BytesIO
from typing import Iterator, Optional

import requests
from PIL import Image

from config import LLM_MODEL, LLM_SERVER_URL
from llm_provider import LLMProvider
from retry import retry_with_backoff

logger = logging.getLogger("img2sdtxt.llm")


class LLMClient(LLMProvider):
    def __init__(self, base_url: str = LLM_SERVER_URL, model: str = LLM_MODEL):
        self.base_url = base_url
        self._model = model
        self.endpoint = f"{base_url}/chat/completions"

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    @property
    def model(self) -> str:
        return self._model

    def supports_streaming(self) -> bool:
        return True

    def _build_text_payload(self, prompt: str, max_tokens: int) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "あなたはStable Diffusionのプロンプト生成の専門家です。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "top_p": 0.9,
        }

    def _build_image_payload(self, prompt: str, image_bytes: bytes, max_tokens: int) -> dict:
        image_base64 = self._encode_image_to_base64(image_bytes)
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "あなたはStable Diffusionのプロンプト生成の専門家です。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    ],
                },
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "top_p": 0.9,
        }

    def _stream_chat(self, payload: dict, timeout: int) -> Iterator[str]:
        """OpenAI互換の SSE ストリーミングレスポンスから content の差分を逐次 yield する"""
        payload = {**payload, "stream": True}
        try:
            with requests.post(self.endpoint, json=payload, timeout=timeout, stream=True) as response:
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    content = (choices[0].get("delta") or {}).get("content")
                    if content:
                        yield content
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to LLM server at %s", self.base_url)
            raise ConnectionError(f"Cannot connect to LLM server at {self.base_url}")
        except requests.exceptions.Timeout:
            logger.error("LLM streaming request timed out url=%s", self.endpoint)
            raise TimeoutError("LLM server request timed out")

    def generate_response_stream(self, prompt: str, max_tokens: int = 500) -> Iterator[str]:
        logger.debug("generate_response_stream url=%s model=%s", self.endpoint, self.model)
        yield from self._stream_chat(self._build_text_payload(prompt, max_tokens), timeout=30)

    def generate_response_with_image_stream(
        self, prompt: str, image_bytes: bytes, max_tokens: int = 500
    ) -> Iterator[str]:
        logger.debug(
            "generate_response_with_image_stream url=%s model=%s image_bytes=%d",
            self.endpoint,
            self.model,
            len(image_bytes),
        )
        yield from self._stream_chat(self._build_image_payload(prompt, image_bytes, max_tokens), timeout=60)

    def _convert_webp_to_png(self, image_bytes: bytes) -> bytes:
        """WebP形式の画像をPNG形式に変換"""
        try:
            # 画像を開く
            image = Image.open(BytesIO(image_bytes))

            # WebP形式の場合のみ変換
            if image.format == "WEBP":
                # PNGに変換
                png_buffer = BytesIO()
                # RGBに変換（アルファチャンネルがある場合も対応）
                if image.mode in ("RGBA", "LA", "P"):
                    # 透明度情報を保持
                    image.save(png_buffer, format="PNG")
                else:
                    image.convert("RGB").save(png_buffer, format="PNG")
                return png_buffer.getvalue()
            else:
                # WebP以外はそのまま返す
                return image_bytes
        except Exception as e:
            logger.warning("Image conversion failed (%s), using original image", str(e))
            return image_bytes

    def _encode_image_to_base64(self, image_bytes: bytes) -> str:
        """画像バイトをBase64エンコード（WebP→PNG変換含む）"""
        # WebPをPNGに変換
        converted_bytes = self._convert_webp_to_png(image_bytes)
        return base64.b64encode(converted_bytes).decode("utf-8")

    @retry_with_backoff(max_retries=1, base_delay=0.5)
    def is_available(self) -> bool:
        """LLMサーバーへの軽量な疎通確認 (GET /v1/models、タイムアウト5秒)"""
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=5)
            return r.status_code < 300
        except Exception:
            return False

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """
        LLMサーバーに対してプロンプトを送信し、レスポンスを取得
        LM Studio/Lemonade server 互換のOpenAI互換API
        """
        logger.debug("generate_response url=%s model=%s", self.endpoint, self.model)
        t0 = time.time()
        try:
            payload = self._build_text_payload(prompt, max_tokens)

            response = requests.post(self.endpoint, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()
            if result.get("choices") and len(result["choices"]) > 0:
                elapsed = (time.time() - t0) * 1000
                logger.info("LLM call succeeded model=%s %.0fms", self.model, elapsed)
                return result["choices"][0]["message"]["content"]

            return None
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to LLM server at %s", self.base_url)
            raise ConnectionError(f"Cannot connect to LLM server at {self.base_url}")
        except requests.exceptions.Timeout:
            logger.error("LLM server request timed out url=%s", self.endpoint)
            raise TimeoutError("LLM server request timed out")
        except Exception as e:
            logger.error("LLM server error: %s", str(e))
            raise Exception(f"LLM server error: {str(e)}")

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def generate_response_with_image(self, prompt: str, image_bytes: bytes, max_tokens: int = 500) -> Optional[str]:
        """
        画像を含めてLLMサーバーに対してプロンプトを送信し、レスポンスを取得
        LM Studio/Lemonade server 互換のOpenAI互換API (Vision Models対応)
        """
        logger.debug(
            "generate_response_with_image url=%s model=%s image_bytes=%d", self.endpoint, self.model, len(image_bytes)
        )
        t0 = time.time()
        try:
            payload = self._build_image_payload(prompt, image_bytes, max_tokens)

            response = requests.post(self.endpoint, json=payload, timeout=60)
            response.raise_for_status()

            result = response.json()
            if result.get("choices") and len(result["choices"]) > 0:
                elapsed = (time.time() - t0) * 1000
                logger.info("LLM vision call succeeded model=%s %.0fms", self.model, elapsed)
                return result["choices"][0]["message"]["content"]

            return None
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to LLM server at %s", self.base_url)
            raise ConnectionError(f"Cannot connect to LLM server at {self.base_url}")
        except requests.exceptions.Timeout:
            logger.error("LLM vision request timed out url=%s", self.endpoint)
            raise TimeoutError("LLM server request timed out (vision model analysis may take longer)")
        except Exception as e:
            logger.error("LLM server error: %s", str(e))
            raise Exception(f"LLM server error: {str(e)}")
