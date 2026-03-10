"""Health check route."""

from fastapi import APIRouter
from app.config import settings
from app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    # Report GLM-OCR status based on mode (local vs remote)
    if settings.GLM_USE_LOCAL:
        glm_status = {
            "configured": True,
            "mode": "local",
            "model": settings.GLM_LOCAL_MODEL_PATH,
        }
    else:
        glm_status = {
            "configured": bool(settings.GLM_API_KEY),
            "mode": "remote",
            "url": settings.GLM_API_URL,
        }

    return HealthResponse(
        status="ok",
        version="1.0.0",
        services={
            "glm_ocr": glm_status,
            "gemini": {
                "configured": bool(settings.GEMINI_API_KEY),
                "model": settings.GEMINI_MODEL,
            },
        },
    )

