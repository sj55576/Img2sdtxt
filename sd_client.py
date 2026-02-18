"""
Stable Diffusion Web UI (AUTOMATIC1111) API クライアント
"""
import requests
import base64
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from config import SD_API_URL, SD_OUTPUT_DIR


class SDClient:
    def __init__(self, base_url: str = SD_API_URL):
        self.base_url = base_url.rstrip("/")
        # 出力ディレクトリを自動作成
        SD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def get_models(self) -> List[Dict]:
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise Exception(f"Failed to get models: {str(e)}")

    def get_current_model(self) -> str:
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/options", timeout=10)
            r.raise_for_status()
            return r.json().get("sd_model_checkpoint", "")
        except Exception:
            return ""

    def set_model(self, model_name: str) -> bool:
        """
        使用するモデルを切り替える
        model_name: チェックポイント名またはファイル名
        """
        try:
            payload = {"sd_model_checkpoint": model_name}
            response = requests.post(
                f"{self.base_url}/sdapi/v1/options",
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            print(f"✓ Model switched to: {model_name}")
            return True
        except Exception as e:
            print(f"Error switching model: {str(e)}")
            return False

    def get_model_list(self) -> List[Dict]:
        """利用可能なモデル一覧を取得（ハッシュと名前付き）"""
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            raise Exception(f"Failed to get models: {str(e)}")

    def txt2img(
        self,
        positive: str,
        negative: str,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg_scale: float = 7.0,
        sampler: str = "Euler a",
        seed: int = -1,
        batch_size: int = 1,
        model: str = "",
        loras: str = ""
    ) -> List[str]:
        """
        テキストから画像を生成し、Base64エンコードされた画像リストを返す
        model: 使用するモデル名（指定時は自動切り替え）
        loras: LoRA指定。形式: "lora1:1.0,lora2:0.8" または "<lora:lora1:1.0><lora:lora2:0.8>"
        """
        # モデルの切り替え（指定された場合）
        if model:
            self.set_model(model)

        # LoRAをプロンプトに追加
        final_positive = positive
        if loras:
            # LoRA形式の正規化
            if ":" in loras and not loras.startswith("<lora:"):
                # "lora1:1.0,lora2:0.8" 形式を "<lora:lora1:1.0><lora:lora2:0.8>" に変換
                lora_parts = loras.split(",")
                lora_tags = "".join([f"<lora:{part.strip()}>" for part in lora_parts])
            else:
                lora_tags = loras

            final_positive = f"{lora_tags}, {positive}"

        payload = {
            "prompt": final_positive,
            "negative_prompt": negative,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler_name": sampler,
            "seed": seed,
            "batch_size": batch_size,
            "restore_faces": False,
            "save_images": False
        }
        try:
            r = requests.post(
                f"{self.base_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=120
            )
            r.raise_for_status()
            result = r.json()
            return result.get("images", [])
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Stable Diffusion API at {self.base_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError("Stable Diffusion generation timed out")
        except Exception as e:
            raise Exception(f"SD API error: {str(e)}")

    def get_samplers(self) -> List[str]:
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/samplers", timeout=10)
            r.raise_for_status()
            return [s["name"] for s in r.json()]
        except Exception:
            return ["Euler a", "Euler", "DPM++ 2M Karras", "DDIM"]

    def save_images(
        self,
        images: List[str],
        positive: str = "",
        negative: str = "",
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg_scale: float = 7.0,
        sampler: str = "Euler a",
        seed: int = -1,
        model: str = "",
        loras: str = ""
    ) -> List[Dict]:
        """
        生成された画像（Base64エンコード）を保存
        メタデータ付きのJSONファイルも同時に保存
        """
        saved_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            for idx, image_base64 in enumerate(images):
                # ファイル名生成
                filename = f"sd_{timestamp}_{idx:03d}.png"
                filepath = SD_OUTPUT_DIR / filename

                # Base64をデコードして保存
                image_bytes = base64.b64decode(image_base64)
                with open(filepath, "wb") as f:
                    f.write(image_bytes)

                saved_files.append({
                    "filename": filename,
                    "path": str(filepath),
                    "index": idx
                })

            # メタデータ（生成パラメータ）をJSONで保存
            metadata = {
                "timestamp": timestamp,
                "image_count": len(images),
                "parameters": {
                    "positive_prompt": positive,
                    "negative_prompt": negative,
                    "width": width,
                    "height": height,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                    "sampler": sampler,
                    "seed": seed,
                    "model": model,
                    "loras": loras
                },
                "files": saved_files
            }

            metadata_filename = f"sd_{timestamp}_metadata.json"
            metadata_filepath = SD_OUTPUT_DIR / metadata_filename
            with open(metadata_filepath, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            print(f"✓ Saved {len(images)} image(s) to {SD_OUTPUT_DIR}")
            print(f"✓ Metadata saved to {metadata_filename}")

            return saved_files
        except Exception as e:
            print(f"Error saving images: {str(e)}")
            return []
