"""
Stable Diffusion Web UI (AUTOMATIC1111) API クライアント
"""
import requests
import base64
from typing import Optional, Dict, List
from config import SD_API_URL


class SDClient:
    def __init__(self, base_url: str = SD_API_URL):
        self.base_url = base_url.rstrip("/")

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
        batch_size: int = 1
    ) -> List[str]:
        """
        テキストから画像を生成し、Base64エンコードされた画像リストを返す
        """
        payload = {
            "prompt": positive,
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
