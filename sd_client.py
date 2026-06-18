"""
Stable Diffusion Web UI (AUTOMATIC1111) API クライアント
"""
import requests
import base64
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from config import SD_API_URL, SD_OUTPUT_DIR
from retry import retry_with_backoff

logger = logging.getLogger("img2sdtxt.sd")


class SDClient:
    def __init__(self, base_url: str = SD_API_URL):
        self.base_url = base_url.rstrip("/")
        # 出力ディレクトリを自動作成
        SD_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @retry_with_backoff(max_retries=1, base_delay=0.5)
    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/sd-models", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    @retry_with_backoff(max_retries=2, base_delay=1.0)
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
            logger.info("Model switched to: %s", model_name)
            return True
        except Exception as e:
            logger.error("Error switching model: %s", str(e))
            return False

    def get_model_list(self) -> List[Dict]:
        """利用可能なモデル一覧を取得（get_models に委譲）"""
        return self.get_models()

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def get_loras(self) -> List[Dict]:
        """利用可能なLoRA一覧を取得"""
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/loras", timeout=10)
            r.raise_for_status()
            result = r.json()
            if isinstance(result, list):
                return result
            logger.warning("get_loras unexpected response format: %s", type(result))
            return []
        except Exception as e:
            logger.warning("get_loras failed to fetch LoRAs from %s/sdapi/v1/loras: %s", self.base_url, e)
            return []

    def get_progress(self) -> Optional[Dict]:
        """SD WebUI の生成進捗を取得。エラー時は None を返す (タイムアウト5秒)"""
        try:
            r = requests.get(
                f"{self.base_url}/sdapi/v1/progress",
                params={"skip_current_image": "true"},
                timeout=5
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    @retry_with_backoff(max_retries=1, base_delay=0.5)
    def get_controlnet_models(self) -> List[str]:
        """Get available ControlNet models from SD WebUI"""
        try:
            r = requests.get(f"{self.base_url}/controlnet/model_list", timeout=10)
            r.raise_for_status()
            result = r.json()
            models = result.get("model_list", [])
            logger.info("get_controlnet_models: found %d model(s)", len(models))
            return models
        except Exception as e:
            logger.warning("get_controlnet_models failed (ControlNet may not be installed): %s", e)
            return []

    @retry_with_backoff(max_retries=1, base_delay=0.5)
    def get_controlnet_modules(self) -> List[str]:
        """Get available ControlNet preprocessor modules"""
        try:
            r = requests.get(f"{self.base_url}/controlnet/module_list", timeout=10)
            r.raise_for_status()
            result = r.json()
            modules = result.get("module_list", [])
            logger.info("get_controlnet_modules: found %d module(s)", len(modules))
            return modules
        except Exception as e:
            logger.warning("get_controlnet_modules failed (ControlNet may not be installed): %s", e)
            return []

    @retry_with_backoff(max_retries=1, base_delay=0.5)
    def get_controlnet_settings(self) -> Dict:
        """Get ControlNet extension settings"""
        try:
            r = requests.get(f"{self.base_url}/controlnet/settings", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning("get_controlnet_settings failed (ControlNet may not be installed): %s", e)
            return {}

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    def get_upscalers(self) -> List[str]:
        try:
            r = requests.get(f"{self.base_url}/sdapi/v1/upscalers", timeout=10)
            r.raise_for_status()
            return [u["name"] for u in r.json()]
        except Exception:
            return ["Latent", "Latent (antialiased)", "Latent (bicubic)", "Latent (bicubic antialiased)",
                    "Latent (nearest)", "None", "Lanczos", "Nearest",
                    "ESRGAN_4x", "LDSR", "R-ESRGAN 4x+", "R-ESRGAN 4x+ Anime6B",
                    "ScuNET GAN", "ScuNET PSNR", "SwinIR 4x"]

    @retry_with_backoff(max_retries=2, base_delay=2.0)
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
        loras: str = "",
        enable_hr: bool = False,
        hr_scale: float = 2.0,
        hr_upscaler: str = "R-ESRGAN 4x+",
        hr_second_pass_steps: int = 0,
        hr_denoising_strength: float = 0.7,
        controlnet_args: Optional[List[Dict]] = None
    ) -> List[str]:
        """
        テキストから画像を生成し、Base64エンコードされた画像リストを返す
        model: 使用するモデル名（指定時は自動切り替え）
        loras: LoRA指定。形式: "lora1:1.0,lora2:0.8" または "<lora:lora1:1.0><lora:lora2:0.8>"
        enable_hr: Hires.fix を有効化（アップスケール生成）
        hr_scale: アップスケール倍率
        hr_upscaler: アップスケーラー名
        hr_second_pass_steps: Hires.fix 第2パスのステップ数（0=メインと同じ）
        hr_denoising_strength: Hires.fix のデノイジング強度
        controlnet_args: ControlNet設定のリスト（None の場合は無効）
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
            "save_images": False,
            "enable_hr": enable_hr,
            "hr_scale": hr_scale,
            "hr_upscaler": hr_upscaler,
            "hr_second_pass_steps": hr_second_pass_steps,
            "denoising_strength": hr_denoising_strength if enable_hr else 0.7
        }
        if controlnet_args:
            payload["alwayson_scripts"] = {
                "controlnet": {
                    "args": controlnet_args
                }
            }
            logger.info("txt2img: controlnet enabled with %d unit(s)", len(controlnet_args))

        logger.info("txt2img start url=%s width=%d height=%d steps=%d", self.base_url, width, height, steps)
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

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    def img2img(
        self,
        init_image: str,
        positive: str,
        negative: str,
        denoising_strength: float = 0.75,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg_scale: float = 7.0,
        sampler: str = "Euler a",
        seed: int = -1,
        batch_size: int = 1,
        resize_mode: int = 0,
        model: str = "",
        loras: str = "",
        enable_hr: bool = False,
        hr_scale: float = 2.0,
        hr_upscaler: str = "R-ESRGAN 4x+",
        hr_second_pass_steps: int = 0,
        hr_denoising_strength: float = 0.7,
        controlnet_args: Optional[List[Dict]] = None
    ) -> List[str]:
        """
        画像から画像を生成し、Base64エンコードされた画像リストを返す
        init_image: Base64エンコードされた入力画像
        denoising_strength: 変化の強さ (0.0=変化なし, 1.0=完全変換)
        resize_mode: 0=そのままリサイズ, 1=クロップ&リサイズ, 2=リサイズ&フィル
        enable_hr: Hires.fix を有効化（アップスケール生成）
        hr_scale: アップスケール倍率
        hr_upscaler: アップスケーラー名
        hr_second_pass_steps: Hires.fix 第2パスのステップ数
        hr_denoising_strength: Hires.fix のデノイジング強度
        controlnet_args: ControlNet設定のリスト（None の場合は無効）
        """
        if model:
            self.set_model(model)

        # LoRAをプロンプトに追加
        final_positive = positive
        if loras:
            if ":" in loras and not loras.startswith("<lora:"):
                lora_parts = loras.split(",")
                lora_tags = "".join([f"<lora:{part.strip()}>" for part in lora_parts])
            else:
                lora_tags = loras
            final_positive = f"{lora_tags}, {positive}"

        payload = {
            "init_images": [init_image],
            "prompt": final_positive,
            "negative_prompt": negative,
            "denoising_strength": denoising_strength,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler_name": sampler,
            "seed": seed,
            "batch_size": batch_size,
            "resize_mode": resize_mode,
            "restore_faces": False,
            "save_images": False,
            "enable_hr": enable_hr,
            "hr_scale": hr_scale,
            "hr_upscaler": hr_upscaler,
            "hr_second_pass_steps": hr_second_pass_steps,
            "hr_denoising_strength": hr_denoising_strength
        }
        if controlnet_args:
            payload["alwayson_scripts"] = {
                "controlnet": {
                    "args": controlnet_args
                }
            }
            logger.info("img2img: controlnet enabled with %d unit(s)", len(controlnet_args))

        try:
            r = requests.post(
                f"{self.base_url}/sdapi/v1/img2img",
                json=payload,
                timeout=180
            )
            r.raise_for_status()
            result = r.json()
            return result.get("images", [])
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Stable Diffusion API at {self.base_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError("Stable Diffusion img2img generation timed out")
        except Exception as e:
            raise Exception(f"SD API error: {str(e)}")

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    def inpaint(
        self,
        init_image: str,
        mask: str,
        positive: str,
        negative: str,
        denoising_strength: float = 0.75,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        cfg_scale: float = 7.0,
        sampler: str = "Euler a",
        seed: int = -1,
        batch_size: int = 1,
        mask_blur: int = 4,
        inpainting_fill: int = 1,
        inpaint_full_res: bool = True,
        inpaint_full_res_padding: int = 32,
        model: str = "",
        loras: str = ""
    ) -> List[str]:
        """
        インペインティング（マスク領域を描き直す）を実施し、Base64エンコードされた画像リストを返す
        init_image: Base64エンコードされた入力画像
        mask: Base64エンコードされたマスク画像（白=描き直す領域, 黒=保持する領域）
        denoising_strength: 変化の強さ (0.0=変化なし, 1.0=完全変換)
        mask_blur: マスクのぼかし半径
        inpainting_fill: 0=塗りつぶし, 1=元画像, 2=潜在ノイズ, 3=潜在ゼロ
        inpaint_full_res: マスク領域のみをフル解像度でインペイント
        inpaint_full_res_padding: マスク領域周囲のパディング
        """
        if model:
            self.set_model(model)

        final_positive = positive
        if loras:
            if ":" in loras and not loras.startswith("<lora:"):
                lora_parts = loras.split(",")
                lora_tags = "".join([f"<lora:{part.strip()}>" for part in lora_parts])
            else:
                lora_tags = loras
            final_positive = f"{lora_tags}, {positive}"

        payload = {
            "init_images": [init_image],
            "mask": mask,
            "prompt": final_positive,
            "negative_prompt": negative,
            "denoising_strength": denoising_strength,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler_name": sampler,
            "seed": seed,
            "batch_size": batch_size,
            "mask_blur": mask_blur,
            "inpainting_fill": inpainting_fill,
            "inpaint_full_res": inpaint_full_res,
            "inpaint_full_res_padding": inpaint_full_res_padding,
            "restore_faces": False,
            "save_images": False
        }
        try:
            r = requests.post(
                f"{self.base_url}/sdapi/v1/img2img",
                json=payload,
                timeout=180
            )
            r.raise_for_status()
            result = r.json()
            return result.get("images", [])
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot connect to Stable Diffusion API at {self.base_url}")
        except requests.exceptions.Timeout:
            raise TimeoutError("Stable Diffusion inpainting timed out")
        except Exception as e:
            raise Exception(f"SD API error: {str(e)}")

    @retry_with_backoff(max_retries=2, base_delay=1.0)
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
        loras: str = "",
        mode: str = "txt2img",
        denoising_strength: float = 0.75
    ) -> List[Dict]:
        """
        生成された画像（Base64エンコード）を保存
        メタデータ付きのJSONファイルも同時に保存
        mode: "txt2img", "img2img", または "inpaint"
        """
        saved_files = []
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        date_str = now.strftime("%Y-%m-%d")
        if mode == "img2img":
            prefix = "i2i"
        elif mode == "inpaint":
            prefix = "inp"
        else:
            prefix = "sd"

        # 日付ごとのサブフォルダを作成
        date_dir = SD_OUTPUT_DIR / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        try:
            for idx, image_base64 in enumerate(images):
                # ファイル名生成
                filename = f"{prefix}_{timestamp}_{idx:03d}.png"
                filepath = date_dir / filename

                # Base64をデコードして保存
                image_bytes = base64.b64decode(image_base64)
                with open(filepath, "wb") as f:
                    f.write(image_bytes)

                # PNG tEXt チャンクにA1111互換メタデータを埋め込む
                try:
                    png_meta = PngInfo()
                    params_text = positive
                    if negative:
                        params_text += f"\nNegative prompt: {negative}"
                    params_text += f"\nSteps: {steps}, Sampler: {sampler}, CFG scale: {cfg_scale}, Seed: {seed}, Size: {width}x{height}"
                    if model:
                        params_text += f", Model: {model}"
                    if loras:
                        params_text += f", LoRA: {loras}"
                    if mode in ("img2img", "inpaint"):
                        params_text += f", Denoising strength: {denoising_strength}"
                    png_meta.add_text("parameters", params_text)
                    with Image.open(filepath) as img:
                        img.save(filepath, "PNG", pnginfo=png_meta)
                except Exception as e:
                    print(f"Warning: PNG metadata embedding failed for {filename}: {e}")

                # サムネイル生成 (200px JPEG、.jpg 拡張子)
                try:
                    thumbs_dir = date_dir / "thumbs"
                    thumbs_dir.mkdir(exist_ok=True)
                    thumb_stem = Path(filename).stem
                    thumb_path = thumbs_dir / f"{thumb_stem}.jpg"
                    with Image.open(filepath) as pil_img:
                        pil_img.thumbnail((200, 200), Image.LANCZOS)
                        pil_img.save(thumb_path, "JPEG", quality=80, optimize=True)
                except Exception as e:
                    print(f"Warning: thumbnail generation failed for {filename}: {e}")

                saved_files.append({
                    "filename": filename,
                    "path": str(filepath),
                    "index": idx
                })

            # メタデータ（生成パラメータ）をJSONで保存
            params = {
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
            }
            if mode in ("img2img", "inpaint"):
                params["denoising_strength"] = denoising_strength

            metadata = {
                "timestamp": timestamp,
                "mode": mode,
                "image_count": len(images),
                "parameters": params,
                "files": saved_files
            }

            metadata_filename = f"{prefix}_{timestamp}_metadata.json"
            metadata_filepath = date_dir / metadata_filename
            with open(metadata_filepath, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            print(f"✓ Saved {len(images)} image(s) to {date_dir}")
            print(f"✓ Metadata saved to {metadata_filename}")

            return saved_files
        except Exception as e:
            print(f"Error saving images: {str(e)}")
            return []

    def read_png_metadata(self, filepath: str) -> Optional[Dict]:
        """
        PNGファイルのtEXtチャンクからA1111形式のパラメータを読み込み、辞書に変換して返す。
        パラメータが存在しない場合はNoneを返す。
        """
        try:
            with Image.open(filepath) as img:
                info = img.info
            raw = info.get("parameters")
            if not raw:
                return None

            result: Dict = {}
            lines = raw.split("\n")

            positive_lines = []
            negative_lines = []
            settings_line = ""
            in_negative = False

            for line in lines:
                if line.startswith("Negative prompt:"):
                    in_negative = True
                    negative_lines.append(line[len("Negative prompt:"):].strip())
                elif in_negative and not line.startswith("Steps:"):
                    negative_lines.append(line)
                elif line.startswith("Steps:"):
                    settings_line = line
                    in_negative = False
                elif not in_negative:
                    positive_lines.append(line)

            result["positive_prompt"] = "\n".join(positive_lines).strip()
            if negative_lines:
                result["negative_prompt"] = "\n".join(negative_lines).strip()

            if settings_line:
                for part in settings_line.split(","):
                    part = part.strip()
                    if ": " in part:
                        key, _, value = part.partition(": ")
                        key = key.strip()
                        value = value.strip()
                        mapping = {
                            "Steps": "steps",
                            "Sampler": "sampler",
                            "CFG scale": "cfg_scale",
                            "Seed": "seed",
                            "Size": "size",
                            "Model": "model",
                            "LoRA": "loras",
                            "Denoising strength": "denoising_strength",
                        }
                        if key in mapping:
                            out_key = mapping[key]
                            if out_key in ("steps", "seed"):
                                try:
                                    value = int(value)
                                except ValueError:
                                    pass
                            elif out_key in ("cfg_scale", "denoising_strength"):
                                try:
                                    value = float(value)
                                except ValueError:
                                    pass
                            elif out_key == "size":
                                if "x" in value:
                                    w, _, h = value.partition("x")
                                    try:
                                        result["width"] = int(w)
                                        result["height"] = int(h)
                                    except ValueError:
                                        pass
                                continue
                            result[out_key] = value

            result["raw"] = raw
            return result
        except Exception as e:
            print(f"Warning: could not read PNG metadata from {filepath}: {e}")
            return None
