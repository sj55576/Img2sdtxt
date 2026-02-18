import os
from dotenv import load_dotenv

load_dotenv()

# LLM Server Configuration
LLM_SERVER_URL = os.getenv("LLM_SERVER_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

# Stable Diffusion API Configuration
SD_API_URL = os.getenv("SD_API_URL", "http://localhost:7860")

# API Server Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Image Configuration
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"]

# Prompt Customization Options
STYLES = [
    "photorealistic", "anime", "painting", "watercolor",
    "concept_art", "sketch", "pixel_art", "3d_render"
]
TONES = [
    "natural", "vibrant", "warm", "cool", "dark",
    "soft", "dramatic", "cinematic"
]
QUALITY_LEVELS = {
    "standard": "best quality",
    "high": "best quality, masterpiece, highly detailed",
    "ultra": "best quality, masterpiece, highly detailed, 8k uhd, sharp focus, professional"
}
