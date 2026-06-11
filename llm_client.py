import requests
import json
import base64
from io import BytesIO
from PIL import Image
from config import LLM_SERVER_URL, LLM_MODEL
from typing import Optional, List, Dict, Any

class LLMClient:
    def __init__(self, base_url: str = LLM_SERVER_URL, model: str = LLM_MODEL):
        self.base_url = base_url
        self.model = model
        self.endpoint = f"{base_url}/chat/completions"

    def _convert_webp_to_png(self, image_bytes: bytes) -> bytes:
        """WebP形式の画像をPNG形式に変換"""
        try:
            # 画像を開く
            image = Image.open(BytesIO(image_bytes))

            # WebP形式の場合のみ変換
            if image.format == 'WEBP':
                # PNGに変換
                png_buffer = BytesIO()
                # RGBに変換（アルファチャンネルがある場合も対応）
                if image.mode in ('RGBA', 'LA', 'P'):
                    # 透明度情報を保持
                    image.save(png_buffer, format='PNG')
                else:
                    image.convert('RGB').save(png_buffer, format='PNG')
                return png_buffer.getvalue()
            else:
                # WebP以外はそのまま返す
                return image_bytes
        except Exception as e:
            print(f"Warning: Image conversion failed ({str(e)}), using original image")
            return image_bytes

    def _encode_image_to_base64(self, image_bytes: bytes) -> str:
        """画像バイトをBase64エンコード（WebP→PNG変換含む）"""
        # WebPをPNGに変換
        converted_bytes = self._convert_webp_to_png(image_bytes)
        return base64.b64encode(converted_bytes).decode('utf-8')

    def is_available(self) -> bool:
        """LLMサーバーへの軽量な疎通確認 (GET /v1/models、タイムアウト5秒)"""
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=5)
            return r.status_code < 300
        except Exception:
            return False

    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """
        LLMサーバーに対してプロンプトを送信し、レスポンスを取得
        LM Studio/Lemonade server 互換のOpenAI互換API
        """
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "あなたはStable Diffusionのプロンプト生成の専門家です。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": max_tokens,
                "top_p": 0.9
            }

            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            if result.get("choices") and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]

            return None
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to LLM server at {self.base_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"LLM server request timed out")
        except Exception as e:
            raise Exception(f"LLM server error: {str(e)}")

    def generate_response_with_image(self, prompt: str, image_bytes: bytes, max_tokens: int = 500) -> Optional[str]:
        """
        画像を含めてLLMサーバーに対してプロンプトを送信し、レスポンスを取得
        LM Studio/Lemonade server 互換のOpenAI互換API (Vision Models対応)
        """
        try:
            image_base64 = self._encode_image_to_base64(image_bytes)

            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "あなたはStable Diffusionのプロンプト生成の専門家です。"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
                        ]
                    }
                ],
                "temperature": 0.7,
                "max_tokens": max_tokens,
                "top_p": 0.9
            }

            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=60
            )
            response.raise_for_status()

            result = response.json()
            if result.get("choices") and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]

            return None
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to LLM server at {self.base_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError(f"LLM server request timed out (vision model analysis may take longer)")
        except Exception as e:
            raise Exception(f"LLM server error: {str(e)}")
