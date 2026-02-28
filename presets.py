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
        "is_default": True
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
        "is_default": True
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
        "is_default": True
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
        "is_default": True
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
        "is_default": True
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
