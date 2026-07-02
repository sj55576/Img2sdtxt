"""PNG Info インポート機能: アップロード画像から A1111 生成パラメータを抽出する。"""

import io
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

from config import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from deps import _validate_image_bytes
from sd_client import parse_a1111_parameters

logger = logging.getLogger("img2sdtxt.png_info")

router = APIRouter(prefix="/api", tags=["png-info"])


@router.post("/png-info")
async def get_png_info(file: UploadFile = File(...)):
    """アップロードされた画像の PNG tEXt "parameters" チャンクから
    A1111 の生成パラメータを抽出して返す。メタデータが無ければ has_metadata=False。"""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    _validate_image_bytes(contents)

    with Image.open(io.BytesIO(contents)) as img:
        raw = img.info.get("parameters")

    if not raw:
        return {"has_metadata": False}

    return {"has_metadata": True, "parameters": parse_a1111_parameters(raw)}
