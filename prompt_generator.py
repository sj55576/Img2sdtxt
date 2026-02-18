import base64
from io import BytesIO
from llm_client import LLMClient
from typing import Dict, Tuple

class PromptGenerator:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def image_to_base64(self, image_bytes: bytes) -> str:
        """画像をBase64に変換"""
        return base64.b64encode(image_bytes).decode('utf-8')

    def generate_prompts(self, image_bytes: bytes) -> Dict[str, str]:
        """
        画像からポジティブ・ネガティブプロンプトを生成
        """
        try:
            # 画像解析用プロンプト
            analysis_prompt = """
以下の画像を分析して、Stable Diffusion用のプロンプトを生成してください。

JSON形式で以下のように返してください：
{
  "positive": "ポジティブプロンプト (詳細な画像の説明、スタイル、品質など)",
  "negative": "ネガティブプロンプト (避けたい要素、低品質な要素など)"
}

ポジティブプロンプトは以下を含める：
- 被写体の詳細な説明
- スタイル/アート形式
- 画質やテクニック
- ムード/アトモスフィア

ネガティブプロンプトは以下を含める：
- 避けたい品質の問題
- 不要な要素
- 一般的なアーティファクト

注意: JSON形式のみを返してください。追加テキストは不要です。
"""

            # LLMにプロンプト生成を依頼
            response_text = self.llm_client.generate_response(analysis_prompt)

            if not response_text:
                raise ValueError("LLMからレスポンスがありません")

            # JSONレスポンスを解析
            import json

            # JSONを抽出（markdown code block対応）
            json_str = response_text
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]

            result = json.loads(json_str.strip())

            return {
                "positive": result.get("positive", ""),
                "negative": result.get("negative", ""),
                "status": "success"
            }

        except json.JSONDecodeError as e:
            return {
                "positive": "",
                "negative": "",
                "error": f"JSON parse error: {str(e)}",
                "status": "error"
            }
        except Exception as e:
            return {
                "positive": "",
                "negative": "",
                "error": str(e),
                "status": "error"
            }

    def generate_prompts_text_only(self, description: str) -> Dict[str, str]:
        """
        テキスト説明からプロンプトを生成（デモ用）
        """
        try:
            prompt = f"""
以下の画像の説明に基づいて、Stable Diffusion用のプロンプトを生成してください。

説明: {description}

JSON形式で以下のように返してください：
{{
  "positive": "ポジティブプロンプト",
  "negative": "ネガティブプロンプト"
}}

注意: JSON形式のみを返してください。
"""

            response_text = self.llm_client.generate_response(prompt)

            if not response_text:
                raise ValueError("LLMからレスポンスがありません")

            import json
            json_str = response_text
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]

            result = json.loads(json_str.strip())

            return {
                "positive": result.get("positive", ""),
                "negative": result.get("negative", ""),
                "status": "success"
            }

        except Exception as e:
            return {
                "positive": "",
                "negative": "",
                "error": str(e),
                "status": "error"
            }
