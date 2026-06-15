import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# LLM Server Configuration
LLM_SERVER_URL = os.getenv("LLM_SERVER_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

# Stable Diffusion API Configuration
SD_API_URL = os.getenv("SD_API_URL", "http://localhost:7860")
SD_OUTPUT_DIR = Path(__file__).parent / "outputs"

# API Server Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# HTTPS Configuration
HTTPS_ENABLED = os.getenv("HTTPS_ENABLED", "false").lower() == "true"
SSL_CERTFILE = os.getenv("SSL_CERTFILE", "")
SSL_KEYFILE = os.getenv("SSL_KEYFILE", "")

# Image Configuration
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp"]

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LLM_CACHE_ENABLED = os.getenv("LLM_CACHE_ENABLED", "true").lower() == "true"
LLM_CACHE_TTL = int(os.getenv("LLM_CACHE_TTL", "3600"))

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
