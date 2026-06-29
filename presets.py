"""
プリセットプロンプトテンプレートの管理
"""

import json
import os
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

_presets_lock = threading.Lock()

PRESETS_PATH = Path(__file__).parent / "data" / "presets.json"
PRESET_ID_MAX_LENGTH = 64

# デフォルトプリセット
DEFAULT_PRESETS = [
    {
        "id": "anime",
        "name": "Anime Style",
        "description": "アニメ・マンガスタイル",
        "positive_suffix": "anime style, manga, 2d, vibrant colors, detailed linework",
        "negative_suffix": "realistic, photographic, 3d render, blurry",
        "style": "anime",
        "tone": "vibrant",
        "quality": "high",
        "is_default": True,
    },
    {
        "id": "photorealistic",
        "name": "Photorealistic",
        "description": "写実的な写真スタイル",
        "positive_suffix": "photorealistic, 8k, detailed, natural lighting, sharp focus, DSLR",
        "negative_suffix": "cartoon, anime, painting, illustration, blurry, low quality",
        "style": "photorealistic",
        "tone": "natural",
        "quality": "ultra",
        "is_default": True,
    },
    {
        "id": "oil_painting",
        "name": "Oil Painting",
        "description": "油絵スタイル",
        "positive_suffix": "oil painting, classical art, rich colors, brush strokes, canvas texture",
        "negative_suffix": "digital art, photograph, anime, low quality, watermark",
        "style": "painting",
        "tone": "warm",
        "quality": "high",
        "is_default": True,
    },
    {
        "id": "watercolor",
        "name": "Watercolor",
        "description": "水彩画スタイル",
        "positive_suffix": "watercolor painting, soft colors, translucent, delicate brushwork",
        "negative_suffix": "oil painting, digital, harsh lines, dark, saturated",
        "style": "painting",
        "tone": "soft",
        "quality": "high",
        "is_default": True,
    },
    {
        "id": "fantasy",
        "name": "Fantasy Art",
        "description": "ファンタジーアートスタイル",
        "positive_suffix": "fantasy art, epic, magical, highly detailed, concept art, trending on artstation",
        "negative_suffix": "mundane, realistic photography, low quality, blurry",
        "style": "concept_art",
        "tone": "dramatic",
        "quality": "high",
        "is_default": True,
    },
    {
        "id": "portrait",
        "name": "Portrait Photo",
        "description": "ポートレート写真スタイル",
        "positive_suffix": "portrait photography, bokeh background, professional lighting, sharp focus, 85mm lens",
        "negative_suffix": "full body, landscape, blurry, low resolution, bad anatomy",
        "style": "photorealistic",
        "tone": "natural",
        "quality": "ultra",
        "is_default": True,
    },
    {
        "id": "realistic_portrait",
        "name": "Realistic Portrait",
        "description": "リアルポートレート（高精細な人物描写）",
        "positive_suffix": "photorealistic, realistic skin texture, detailed face, natural pores, sharp focus, 85mm f/1.4, DSLR, 8k uhd, subsurface scattering, natural lighting",
        "negative_suffix": "cartoon, anime, painting, illustration, cgi, 3d render, doll, plastic skin, blurry, deformed face, bad anatomy, extra fingers, mutated hands, poorly drawn face",
        "style": "photorealistic",
        "tone": "natural",
        "quality": "ultra",
        "is_default": True,
    },
    {
        "id": "fashion_photo",
        "name": "Fashion Photo",
        "description": "ファッションフォト（雑誌風の人物撮影）",
        "positive_suffix": "fashion photography, editorial, high fashion, vogue style, professional model, studio lighting, sharp focus, glamorous, color grading, 50mm lens, full body shot",
        "negative_suffix": "casual, amateur, low quality, blurry, bad anatomy, deformed, cartoon, anime, poorly drawn face, extra limbs, disfigured",
        "style": "photorealistic",
        "tone": "vibrant",
        "quality": "ultra",
        "is_default": True,
    },
    {
        "id": "cinematic_portrait",
        "name": "Cinematic Portrait",
        "description": "シネマティックポートレート（映画的な人物描写）",
        "positive_suffix": "cinematic lighting, film grain, anamorphic lens flare, shallow depth of field, dramatic shadows, color grading, movie still, photorealistic face, detailed skin, 35mm film",
        "negative_suffix": "flat lighting, overexposed, cartoon, anime, painting, cgi, bad anatomy, deformed face, extra fingers, mutated hands, poorly drawn",
        "style": "photorealistic",
        "tone": "cinematic",
        "quality": "ultra",
        "is_default": True,
    },
    {
        "id": "street_snap",
        "name": "Street Snap",
        "description": "ストリートスナップ（自然な日常の人物写真）",
        "positive_suffix": "street photography, candid shot, natural pose, urban background, realistic, ambient lighting, 35mm lens, documentary style, authentic, photojournalistic",
        "negative_suffix": "studio, posed, artificial, cartoon, anime, painting, blurry, bad anatomy, deformed, extra limbs, poorly drawn face, overprocessed",
        "style": "photorealistic",
        "tone": "natural",
        "quality": "high",
        "is_default": True,
    },
    {
        "id": "studio_portrait",
        "name": "Studio Portrait",
        "description": "スタジオポートレート（プロのスタジオ撮影）",
        "positive_suffix": "studio photography, professional lighting, Rembrandt lighting, softbox, beauty dish, clean background, sharp focus, detailed face, realistic skin, headshot, 105mm lens",
        "negative_suffix": "outdoor, natural light, cartoon, anime, painting, blurry, bad anatomy, deformed face, extra fingers, poorly drawn, low quality, watermark",
        "style": "photorealistic",
        "tone": "natural",
        "quality": "ultra",
        "is_default": True,
    },
    {
        "id": "natural_light_portrait",
        "name": "Natural Light Portrait",
        "description": "自然光ポートレート（屋外の柔らかい自然光）",
        "positive_suffix": "natural light photography, golden hour, soft sunlight, outdoor portrait, warm tones, realistic face, detailed skin texture, lens bokeh, 85mm f/1.8, gentle shadows",
        "negative_suffix": "studio lighting, flash, harsh shadows, cartoon, anime, painting, cgi, bad anatomy, deformed face, extra fingers, poorly drawn, artificial lighting",
        "style": "photorealistic",
        "tone": "warm",
        "quality": "ultra",
        "is_default": True,
    },
]


def _load_presets() -> List[Dict]:
    PRESETS_PATH.parent.mkdir(exist_ok=True)
    if PRESETS_PATH.exists():
        try:
            data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else DEFAULT_PRESETS
        except Exception:
            pass
    return DEFAULT_PRESETS


def _save_presets(presets: List[Dict]):
    """アトミックな書き込みでプリセットを保存する"""
    PRESETS_PATH.parent.mkdir(exist_ok=True)
    data = json.dumps(presets, ensure_ascii=False, indent=2)
    # 同一ディレクトリに一時ファイルを作成し os.replace でアトミックに上書き
    fd, tmp_path = tempfile.mkstemp(dir=str(PRESETS_PATH.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp_path, str(PRESETS_PATH))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def get_all_presets() -> List[Dict]:
    return _load_presets()


def get_preset(preset_id: str) -> Optional[Dict]:
    return next((p for p in _load_presets() if p["id"] == preset_id), None)


def _is_valid_preset_id(preset_id: str) -> bool:
    """プリセットIDとして安全な文字列か判定する。"""
    if not isinstance(preset_id, str):
        return False
    if not preset_id or len(preset_id) > PRESET_ID_MAX_LENGTH:
        return False
    return all(ch.isalnum() or ch in ("_", "-") for ch in preset_id)


def _generate_unique_preset_id(existing_ids: set) -> str:
    """既存IDと衝突しない短いIDを生成する。"""
    while True:
        preset_id = uuid.uuid4().hex[:8]
        if preset_id not in existing_ids:
            return preset_id


def add_preset(preset: Dict) -> Dict:
    with _presets_lock:
        presets = _load_presets()
        existing_ids = {p.get("id") for p in presets}

        new_preset = dict(preset)
        requested_id = new_preset.get("id")
        if requested_id:
            if not _is_valid_preset_id(requested_id):
                raise ValueError(
                    "Preset id must be 1-64 characters and contain only letters, numbers, hyphens, or underscores."
                )
            if requested_id in existing_ids:
                raise ValueError(f"Preset id already exists: {requested_id}")
        else:
            new_preset["id"] = _generate_unique_preset_id(existing_ids)

        new_preset["is_default"] = False
        presets.append(new_preset)
        _save_presets(presets)
    return new_preset


def delete_preset(preset_id: str) -> bool:
    with _presets_lock:
        presets = _load_presets()
        original_len = len(presets)
        presets = [p for p in presets if not (p["id"] == preset_id and not p.get("is_default", False))]
        if len(presets) < original_len:
            _save_presets(presets)
            return True
    return False
