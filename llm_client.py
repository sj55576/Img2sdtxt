import requests
import json
from config import LLM_SERVER_URL, LLM_MODEL
from typing import Optional

class LLMClient:
    def __init__(self, base_url: str = LLM_SERVER_URL, model: str = LLM_MODEL):
        self.base_url = base_url
        self.model = model
        self.endpoint = f"{base_url}/chat/completions"

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
