import json
import logging
from typing import Dict

from config import QUALITY_LEVELS
from llm_provider import LLMProvider

logger = logging.getLogger("img2sdtxt.prompt")


class PromptGenerator:
    def __init__(self, llm_client: LLMProvider):
        self.llm_client = llm_client

    def _parse_json_response(self, text: str) -> Dict:
        """LLMのレスポンスからJSONを抽出"""
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())

    def _build_style_instruction(self, style: str, tone: str, quality: str) -> str:
        """カスタマイズ設定をプロンプト指示文に変換"""
        quality_tag = QUALITY_LEVELS.get(quality, QUALITY_LEVELS["standard"])
        style_map = {
            "photorealistic": "写実的な写真スタイル",
            "anime": "アニメ・マンガスタイル",
            "painting": "油絵・水彩画などの絵画スタイル",
            "watercolor": "水彩画スタイル",
            "concept_art": "コンセプトアート・ファンタジースタイル",
            "sketch": "スケッチ・線画スタイル",
            "pixel_art": "ピクセルアートスタイル",
            "3d_render": "3DCGレンダリングスタイル",
        }
        tone_map = {
            "natural": "自然な色調",
            "vibrant": "鮮やかな色彩",
            "warm": "温かみのある暖色系",
            "cool": "クールな寒色系",
            "dark": "暗い・ダークな雰囲気",
            "soft": "柔らかく穏やかな雰囲気",
            "dramatic": "ドラマチックで迫力のある雰囲気",
            "cinematic": "映画のような雰囲気",
        }
        parts = []
        if style and style in style_map:
            parts.append(f"スタイル: {style_map[style]}")
        if tone and tone in tone_map:
            parts.append(f"トーン: {tone_map[tone]}")
        if quality_tag:
            parts.append(f'品質タグを含める: "{quality_tag}"')
        return "\n".join(parts)

    def _call_llm(self, prompt: str) -> Dict:
        response_text = self.llm_client.generate_response(prompt)
        if not response_text:
            raise ValueError("LLMからレスポンスがありません")
        return self._parse_json_response(response_text)

    def generate_prompts(
        self,
        image_bytes: bytes,
        style: str = "",
        tone: str = "",
        quality: str = "high",
        preset_suffix_positive: str = "",
        preset_suffix_negative: str = "",
    ) -> Dict[str, str]:
        """画像からポジティブ・ネガティブプロンプトを生成"""
        logger.info("generate_prompts start style=%s tone=%s quality=%s", style, tone, quality)
        try:
            style_instruction = self._build_style_instruction(style, tone, quality)
            customization = f"\n\nカスタマイズ設定:\n{style_instruction}" if style_instruction else ""

            analysis_prompt = f"""提供された画像を分析して、Stable Diffusion用のプロンプトを生成してください。{customization}

JSON形式のみで返してください：
{{
  "positive": "ポジティブプロンプト (英語のカンマ区切りタグ形式)",
  "negative": "ネガティブプロンプト (英語のカンマ区切りタグ形式)"
}}

ポジティブ: 被写体の詳細説明、スタイルタグ、品質タグ、ムード・雰囲気を含める
ネガティブ: lowres, bad anatomy, bad hands, text, error, worst quality, low quality, blurryなどを含める

注意: JSONのみ返してください。"""

            response_text = self.llm_client.generate_response_with_image(analysis_prompt, image_bytes)
            if not response_text:
                raise ValueError("LLMからレスポンスがありません")
            result = self._parse_json_response(response_text)

            positive = result.get("positive", "")
            negative = result.get("negative", "")

            if preset_suffix_positive:
                positive = f"{positive}, {preset_suffix_positive}"
            if preset_suffix_negative:
                negative = f"{negative}, {preset_suffix_negative}"

            logger.info("generate_prompts done")
            return {"positive": positive, "negative": negative, "status": "success"}

        except json.JSONDecodeError as e:
            logger.error("generate_prompts JSON parse error: %s", str(e))
            return {"positive": "", "negative": "", "error": f"JSON parse error: {str(e)}", "status": "error"}
        except Exception as e:
            logger.error("generate_prompts error: %s", str(e))
            return {"positive": "", "negative": "", "error": str(e), "status": "error"}

    def refine_prompt(
        self,
        positive: str,
        negative: str = "",
        instruction: str = "",
        style: str = "",
        tone: str = "",
        quality: str = "high",
    ) -> Dict[str, str]:
        """既存のプロンプトをLLMで改善・強化する"""
        try:
            style_instruction = self._build_style_instruction(style, tone, quality)
            customization = f"\n\nカスタマイズ設定:\n{style_instruction}" if style_instruction else ""
            user_instruction = f"\n\n特別な指示: {instruction}" if instruction else ""

            prompt = f"""以下のStable Diffusion用プロンプトを改善・強化してください。{customization}{user_instruction}

現在のポジティブプロンプト:
{positive}

現在のネガティブプロンプト:
{negative if negative else "(なし)"}

改善のポイント:
- より詳細で具体的なタグを追加する
- 品質・スタイルタグを最適化する
- 重複するタグを整理する
- ネガティブプロンプトを充実させる
- タグの順序を重要度順に整える

JSON形式のみで返してください：
{{
  "positive": "改善されたポジティブプロンプト (英語のカンマ区切りタグ形式)",
  "negative": "改善されたネガティブプロンプト (英語のカンマ区切りタグ形式)",
  "changes": "改善した主な点の説明 (日本語)"
}}

注意: JSONのみ返してください。"""

            result = self._call_llm(prompt)
            return {
                "positive": result.get("positive", positive),
                "negative": result.get("negative", negative),
                "changes": result.get("changes", ""),
                "status": "success",
            }
        except Exception as e:
            return {"positive": positive, "negative": negative, "changes": "", "error": str(e), "status": "error"}

    def generate_prompts_text_only(
        self,
        description: str,
        style: str = "",
        tone: str = "",
        quality: str = "high",
        preset_suffix_positive: str = "",
        preset_suffix_negative: str = "",
    ) -> Dict[str, str]:
        """テキスト説明からプロンプトを生成"""
        logger.info("generate_prompts_text_only start style=%s tone=%s quality=%s", style, tone, quality)
        try:
            style_instruction = self._build_style_instruction(style, tone, quality)
            customization = f"\n\nカスタマイズ設定:\n{style_instruction}" if style_instruction else ""

            prompt = f"""以下の説明に基づいてStable Diffusion用のプロンプトを生成してください。

説明: {description}{customization}

JSON形式のみで返してください：
{{
  "positive": "ポジティブプロンプト (英語のカンマ区切りタグ形式)",
  "negative": "ネガティブプロンプト (英語のカンマ区切りタグ形式)"
}}

注意: JSONのみ返してください。"""

            result = self._call_llm(prompt)
            positive = result.get("positive", "")
            negative = result.get("negative", "")

            if preset_suffix_positive:
                positive = f"{positive}, {preset_suffix_positive}"
            if preset_suffix_negative:
                negative = f"{negative}, {preset_suffix_negative}"

            logger.info("generate_prompts_text_only done")
            return {"positive": positive, "negative": negative, "status": "success"}

        except Exception as e:
            logger.error("generate_prompts_text_only error: %s", str(e))
            return {"positive": "", "negative": "", "error": str(e), "status": "error"}
