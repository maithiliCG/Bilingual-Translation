"""Language API routes."""

from fastapi import APIRouter
from app.models.enums import SUPPORTED_LANGUAGES

router = APIRouter(prefix="/api", tags=["Languages"])


@router.get("/languages")
async def get_languages():
    """Return list of supported Indian regional languages."""
    return {
        "languages": SUPPORTED_LANGUAGES,
        "count": len(SUPPORTED_LANGUAGES),
    }
