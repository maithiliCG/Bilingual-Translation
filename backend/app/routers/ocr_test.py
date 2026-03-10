"""OCR Test route — proxy image to GLM-OCR (local model or remote API) and return full results."""

import base64
import time
import logging

from fastapi import APIRouter, File, UploadFile, HTTPException
from app.config import settings
from app.services.glm_ocr_service import GLMOCRService
from app.services.glm_ocr_local_service import GLMOCRLocalService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["OCR Test"])

# Lazy-initialized singleton — created on first request, not at import time
_ocr_service = None


def _get_ocr_service():
    """Get or create OCR service instance (lazy init, avoids import-time side effects)."""
    global _ocr_service
    if _ocr_service is None:
        if settings.GLM_USE_LOCAL:
            _ocr_service = GLMOCRLocalService()
            logger.info("OCR Test route using LOCAL GLM-OCR model")
        else:
            _ocr_service = GLMOCRService()
            logger.info("OCR Test route using REMOTE GLM-OCR API")
    return _ocr_service


@router.post("/api/ocr-test")
async def test_ocr(file: UploadFile = File(...)):
    """
    Test the remote GLM-OCR API with an uploaded image.
    Returns the full API response including markdown, layout details, and timing.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed_ext = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")
    if not file.filename.lower().endswith(allowed_ext):
        raise HTTPException(
            status_code=400,
            detail=f"Only image files are accepted: {', '.join(allowed_ext)}",
        )

    try:
        image_bytes = await file.read()
        size_kb = len(image_bytes) / 1024

        if size_kb > 20 * 1024:  # 20MB limit
            raise HTTPException(
                status_code=400,
                detail=f"Image too large ({size_kb/1024:.1f}MB). Max: 20MB",
            )

        logger.info(f"OCR Test: Processing {file.filename} ({size_kb:.0f} KB)")

        # Time the full OCR call
        start_time = time.time()
        result = await _get_ocr_service().parse_page_image(image_bytes)
        elapsed = time.time() - start_time

        # Also get the optimized image for visualization
        optimized_bytes, mime_type = _get_ocr_service().optimize_for_api(image_bytes)
        optimized_b64 = base64.b64encode(optimized_bytes).decode("utf-8")

        # Build response
        return {
            "success": True,
            "file_name": file.filename,
            "original_size_kb": round(size_kb, 1),
            "optimized_size_kb": round(len(optimized_bytes) / 1024, 1),
            "processing_time_seconds": round(elapsed, 1),
            "api_url": settings.GLM_API_URL if not settings.GLM_USE_LOCAL else "local_model",
            "markdown_result": result.get("md_results", ""),
            "layout_details": result.get("layout_details", []),
            "optimized_image_base64": optimized_b64,
            "optimized_image_mime": mime_type,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR Test error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
