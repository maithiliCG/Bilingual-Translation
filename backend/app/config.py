"""Application configuration using pydantic-settings."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# load_dotenv() pushes ALL .env vars into os.environ.
# This is required for third-party libraries (transformers, huggingface_hub)
# that read os.environ directly — e.g. TRANSFORMERS_OFFLINE, HF_HUB_OFFLINE.
# pydantic-settings only loads vars into the Settings class, NOT os.environ.
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # GLM-OCR mode: set GLM_USE_LOCAL=True to use local model, False for remote API
    GLM_USE_LOCAL: bool = True

    # GLM-OCR Local Model
    GLM_LOCAL_MODEL_PATH: str = "zai-org/GLM-OCR"
    GLM_LOCAL_MAX_TOKENS: int = 8192

    # GLM-OCR Remote API (kept for later when API is back up)
    GLM_API_KEY: str = ""
    GLM_API_URL: str = "http://45.249.79.13:5002/glmocr/parse"

    # Google Gemini API
    GEMINI_API_KEY: str = ""

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Storage
    UPLOAD_DIR: str = "./uploads"
    OUTPUT_DIR: str = "./outputs"

    # Pipeline settings
    GLM_OCR_MAX_PAGES_PER_REQUEST: int = 50  # Split large PDFs into chunks
    GLM_OCR_MAX_FILE_SIZE_MB: int = 50
    GLM_OCR_TIMEOUT: int = 300  # seconds
    GEMINI_MODEL: str = "gemini-2.0-flash"
    MAX_UPLOAD_SIZE_MB: int = 500  # Allow very large PDFs

    # Rendering & OCR Tuning
    RENDER_DPI: int = 200  # DPI for rendering PDF pages (200 = good balance for local model OCR quality)
    OCR_MAX_IMAGE_DIM: int = 1200  # Max image dimension for GLM-OCR API (smaller = faster remote processing)
    GEMINI_MAX_OUTPUT_TOKENS: int = 16384  # Max output tokens for Gemini reconstruction
    CROP_PADDING: int = 15  # Base padding around image crops (0-1000 scale) - now adaptive
    CROP_SMART_PADDING: bool = True  # Enable intelligent boundary detection (less aggressive)
    YOLO_IOU_THRESHOLD: float = 0.2  # IoU threshold for matching YOLO detections with GLM crops (lower = more lenient)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars (e.g. TRANSFORMERS_OFFLINE, HF_HUB_OFFLINE)


settings = Settings()

# Ensure directories exist
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
