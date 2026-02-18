import os
from dotenv import load_dotenv

load_dotenv()

# LLM Server Configuration
LLM_SERVER_URL = os.getenv("LLM_SERVER_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Image Configuration
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"]
