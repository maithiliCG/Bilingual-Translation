"""
GLM-5 Backend — FastAPI Application
PDF OCR → Translate → Reconstruct Pipeline

Uses GLM-OCR MaaS API for extraction and Google Gemini for translation & reconstruction.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import translate, languages, health, ocr_test

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    logger.info("=" * 60)
    logger.info("  GLM-5 Backend Starting...")
    if settings.GLM_USE_LOCAL:
        logger.info(f"  GLM-OCR:     LOCAL model ({settings.GLM_LOCAL_MODEL_PATH})")
    else:
        logger.info(f"  GLM-OCR API: {'✓ Configured' if settings.GLM_API_KEY else '✗ Missing'} ({settings.GLM_API_URL})")
    logger.info(f"  Gemini API:  {'✓ Configured' if settings.GEMINI_API_KEY else '✗ Missing'}")
    logger.info(f"  Model:       {settings.GEMINI_MODEL}")
    logger.info(f"  Render DPI:  {settings.RENDER_DPI}")
    logger.info(f"  Server:      {settings.HOST}:{settings.PORT}")
    logger.info("=" * 60)
    
    # Start periodic cleanup task
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(3600)  # 1 hour
            try:
                from app.services.pipeline import job_store
                deleted = job_store.cleanup_old_jobs(max_age_hours=24)
                if deleted > 0:
                    logger.info(f"Periodic cleanup: removed {deleted} old jobs")
                # Clean up old extracted images
                import shutil
                images_path = Path(settings.IMAGE_OUTPUT_DIR)
                if images_path.exists():
                    import time as _time
                    for img_dir in images_path.iterdir():
                        if img_dir.is_dir():
                            age_hours = (_time.time() - img_dir.stat().st_mtime) / 3600
                            if age_hours > 24:
                                shutil.rmtree(img_dir, ignore_errors=True)
                                logger.info(f"Cleaned up old image dir: {img_dir.name}")
            except Exception as e:
                logger.error(f"Cleanup failed: {e}")
    
    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    yield
    
    cleanup_task.cancel()
    logger.info("GLM-5 Backend shutting down...")


# Create FastAPI app
app = FastAPI(
    title="GLM-5 PDF Translation API",
    description=(
        "PDF OCR extraction using GLM-OCR, "
        "translation to Indian regional languages, "
        "and layout reconstruction using Gemini."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend access (applies to API routes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(languages.router)
app.include_router(translate.router)
app.include_router(ocr_test.router)

# Serve static files (fonts, etc.)
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")



# Add CORS headers for static files (fonts) — CORSMiddleware doesn't cover mounted apps
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class StaticFilesCORSMiddleware(BaseHTTPMiddleware):
    """Ensure static file responses (especially fonts and images) include CORS headers."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
        return response


app.add_middleware(StaticFilesCORSMiddleware)


# Root endpoint
@app.get("/")
async def root():
    return {
        "name": "GLM-5 PDF Translation API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
