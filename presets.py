"""
プリセットプロンプトテンプレートの管理
"""
import json
from pathlib import Path
from typing import List, Dict, Optional

PRESETS_PATH = Path(__file__).parent / "data" / "presets.json"

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
        "is_default": True
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
        "is_default": True
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
        "is_default": True
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
        "is_default": True
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
        "is_default": True
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
        "is_default": True
    }
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
    PRESETS_PATH.parent.mkdir(exist_ok=True)
    PRESETS_PATH.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_presets() -> List[Dict]:
    return _load_presets()


def get_preset(preset_id: str) -> Optional[Dict]:
    return next((p for p in _load_presets() if p["id"] == preset_id), None)


def add_preset(preset: Dict) -> Dict:
    presets = _load_presets()
    if not preset.get("id"):
        import uuid
        preset["id"] = str(uuid.uuid4())[:8]
    preset["is_default"] = False
    presets.append(preset)
    _save_presets(presets)
    return preset


def delete_preset(preset_id: str) -> bool:
    presets = _load_presets()
    original_len = len(presets)
    presets = [p for p in presets if not (p["id"] == preset_id and not p.get("is_default", False))]
    if len(presets) < original_len:
        _save_presets(presets)
        return True
    return False
