from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import aiofiles
import os
from pathlib import Path

from config import API_HOST, API_PORT, DEBUG, ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from llm_client import LLMClient
from prompt_generator import PromptGenerator

# FastAPI App初期化
app = FastAPI(
    title="Image to Stable Diffusion Prompt",
    description="Convert images to SD prompts using local LLM",
    version="1.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LLMクライアント初期化
llm_client = LLMClient()
prompt_generator = PromptGenerator(llm_client)

# Static files マウント
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return FileResponse("static/index.html")


@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    try:
        # LLMサーバーの接続確認
        response = llm_client.generate_response("Hello")
        if response:
            return {
                "status": "healthy",
                "llm_server": "connected",
                "message": "Service is running properly"
            }
        else:
            return {
                "status": "degraded",
                "llm_server": "connected but no response",
                "message": "LLM server may have issues"
            }
    except ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="LLM server is not available. Make sure LM Studio or Lemonade server is running."
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service error: {str(e)}"
        )


@app.post("/api/generate-prompts")
async def generate_prompts(file: UploadFile = File(...)):
    """
    画像をアップロードしてプロンプトを生成
    """
    # ファイルタイプの確認
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )

    try:
        # ファイルを読み込む
        contents = await file.read()

        # ファイルサイズの確認
        if len(contents) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Image size exceeds maximum allowed size of {MAX_IMAGE_SIZE / 1024 / 1024}MB"
            )

        # プロンプト生成
        result = prompt_generator.generate_prompts(contents)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate prompts")
            )

        return {
            "success": True,
            "data": {
                "positive": result.get("positive", ""),
                "negative": result.get("negative", "")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing image: {str(e)}"
        )


@app.post("/api/generate-prompts-text")
async def generate_prompts_text(request_data: dict):
    """
    テキスト説明からプロンプトを生成（デモ用）
    """
    description = request_data.get("description", "").strip()

    if not description:
        raise HTTPException(
            status_code=400,
            detail="Description is required"
        )

    try:
        result = prompt_generator.generate_prompts_text_only(description)

        if result.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate prompts")
            )

        return {
            "success": True,
            "data": {
                "positive": result.get("positive", ""),
                "negative": result.get("negative", "")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating prompts: {str(e)}"
        )


@app.get("/api/config")
async def get_config():
    """設定情報の取得"""
    from config import LLM_SERVER_URL, LLM_MODEL
    return {
        "llm_server": LLM_SERVER_URL,
        "model": LLM_MODEL
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG
    )
