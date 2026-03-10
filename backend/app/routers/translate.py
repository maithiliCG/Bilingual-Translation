"""Translation API routes."""

import asyncio
import json
import logging
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.config import settings
from app.models.enums import is_valid_language, get_language_name
from app.models.schemas import JobStatusResponse
from app.services.pipeline import Pipeline, job_store
from app.utils.file_utils import ensure_dir

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/translate", tags=["Translation"])

# Shared pipeline instance
pipeline = Pipeline()


def cleanup_job_files(job_id: str):
    """Delete uploaded files after job completion"""
    try:
        upload_dir = Path(settings.UPLOAD_DIR) / job_id
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
            logger.info(f"Cleaned up files for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to cleanup job {job_id}: {e}")


@router.post("")
async def start_translation(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_language: str = Form(...),
    translation_mode: str = Form("bilingual"),
):
    """
    Upload a PDF and start the translation pipeline.
    Returns a job_id for SSE streaming.
    """
    # Validate file
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Validate language
    if not is_valid_language(target_language):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language code: {target_language}",
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Save uploaded file
    upload_dir = ensure_dir(f"{settings.UPLOAD_DIR}/{job_id}")
    pdf_path = str(upload_dir / file.filename)

    try:
        with open(pdf_path, "wb") as f:
            content = await file.read()

            # Check file size
            size_mb = len(content) / (1024 * 1024)
            if size_mb > settings.MAX_UPLOAD_SIZE_MB:
                raise HTTPException(
                    status_code=400,
                    detail=f"File too large ({size_mb:.1f}MB). Max: {settings.MAX_UPLOAD_SIZE_MB}MB",
                )

            f.write(content)

        logger.info(
            f"Job {job_id}: Uploaded {file.filename} ({size_mb:.1f}MB), "
            f"target language: {get_language_name(target_language)}"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded file: {e}",
        )

    return {
        "job_id": job_id,
        "message": "Translation pipeline started",
        "file_name": file.filename,
        "target_language": get_language_name(target_language),
        "translation_mode": translation_mode,
        "stream_url": f"/api/translate/{job_id}/stream",
    }


@router.get("/{job_id}/stream")
async def stream_translation(job_id: str, background_tasks: BackgroundTasks):
    """
    SSE endpoint — stream page-by-page results as they complete.
    """

    # Find the PDF path for this job
    upload_dir = Path(settings.UPLOAD_DIR) / job_id
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Find the PDF file
    pdf_files = list(upload_dir.glob("*.pdf"))
    if not pdf_files:
        raise HTTPException(status_code=404, detail="PDF file not found for job")

    pdf_path = str(pdf_files[0])

    # Get target language from query or job store - with retry for race condition
    job = job_store.get_job(job_id)
    if not job:
        logger.info(f"Job {job_id} not found, waiting for creation...")
        for attempt in range(10):
            await asyncio.sleep(0.2)
            job = job_store.get_job(job_id)
            if job:
                logger.info(f"Job {job_id} found after {attempt + 1} attempts")
                break
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail="Job not found. Please upload a PDF first.",
            )
    
    target_language = job["target_language"]

    async def event_generator():
        """Generate SSE events from the pipeline."""
        try:
            async for event in pipeline.process_pdf(
                job_id, pdf_path, target_language
            ):
                event_type = event.get("event_type", "message")
                event_data = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {event_data}\n\n"

                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.05)

            # Send final done event
            yield f"event: done\ndata: {json.dumps({'status': 'done'})}\n\n"
            
            # Schedule cleanup after 1 hour using a non-blocking timer
            import threading
            timer = threading.Timer(3600, cleanup_job_files, args=[job_id])
            timer.daemon = True  # Won't block server shutdown
            timer.start()

        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            error_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/status")
async def get_translation_status(job_id: str):
    """Get current job status (polling fallback)."""
    status = pipeline.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    return status


@router.get("/{job_id}/page/{page_num}")
async def get_page_result(job_id: str, page_num: int):
    """Get result for a specific page."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    page_data = job.get("pages", {}).get(page_num)
    if not page_data:
        raise HTTPException(
            status_code=404,
            detail=f"Page {page_num} not found or not yet processed",
        )

    return page_data


@router.post("/{job_id}/start")
async def trigger_pipeline(
    job_id: str,
    target_language: str = Form(...),
    translation_mode: str = Form("bilingual"),
):
    """
    Trigger the pipeline for a pre-uploaded PDF.
    Called after the upload endpoint creates the job.
    """
    upload_dir = Path(settings.UPLOAD_DIR) / job_id
    if not upload_dir.exists():
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    pdf_files = list(upload_dir.glob("*.pdf"))
    if not pdf_files:
        raise HTTPException(status_code=404, detail="PDF file not found for job")

    # Store target language in job
    from app.services.pdf_service import PDFService
    pdf_path = str(pdf_files[0])
    total_pages = PDFService.get_page_count(pdf_path)
    job_store.create_job(job_id, pdf_path, target_language, total_pages, translation_mode=translation_mode)

    return {
        "job_id": job_id,
        "message": "Pipeline registered. Connect to SSE stream to begin processing.",
        "total_pages": total_pages,
        "stream_url": f"/api/translate/{job_id}/stream",
    }


@router.get("/{job_id}/download/pdf")
async def download_pdf(job_id: str):
    """
    Download a PDF file for a completed job.
    Uses Playwright + Chromium to render HTML → PDF with full support for
    MathJax, CSS Grid, Google Fonts, and embedded images.
    Returns the PDF as a direct file download.
    """
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"].value != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (status: {job['status'].value})",
        )

    pages = job.get("pages", {})
    completed_pages = {
        k: v for k, v in pages.items() if v.get("status") == "completed"
    }

    if not completed_pages:
        raise HTTPException(status_code=400, detail="No completed pages found")

    from app.services.download_service import DownloadService

    download_service = DownloadService()

    pdf_path = job.get("pdf_path", "")
    base_name = Path(pdf_path).stem if pdf_path else "translated"
    file_name = f"{base_name}_translated"

    try:
        pdf_bytes = await download_service.generate_pdf(completed_pages, file_name)
    except Exception as e:
        logger.error(f"PDF generation failed for job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    import io

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}.pdf"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.get("/{job_id}/download/docx")
async def download_docx(job_id: str):
    """
    Download a DOCX file for a completed job.
    Pipeline: Playwright renders HTML → PDF, then pdf2docx converts PDF → DOCX.
    This ensures visual fidelity — MathJax, layout, and images are all preserved.
    """
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"].value != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (status: {job['status'].value})",
        )

    pages = job.get("pages", {})
    completed_pages = {
        k: v for k, v in pages.items() if v.get("status") == "completed"
    }

    if not completed_pages:
        raise HTTPException(status_code=400, detail="No completed pages found")

    from app.services.download_service import DownloadService

    download_service = DownloadService()

    # Get file name from the PDF path
    pdf_path = job.get("pdf_path", "")
    base_name = Path(pdf_path).stem if pdf_path else "translated"
    file_name = f"{base_name}_translated"

    # Get language code from job
    lang_code = job.get("target_language", "")

    try:
        docx_buffer = await download_service.generate_docx(
            completed_pages, file_name, lang_code=lang_code
        )
    except Exception as e:
        logger.error(f"DOCX generation failed for job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"DOCX generation failed: {e}")

    return StreamingResponse(
        docx_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{file_name}.docx"',
        },
    )


@router.get("/{job_id}/download/pdf-html")
async def download_pdf_html(job_id: str):
    """
    Return the print-ready HTML for browser preview (legacy/fallback).
    For actual PDF download, use the /download/pdf endpoint instead.
    """
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"].value != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed yet (status: {job['status'].value})",
        )

    pages = job.get("pages", {})

    from app.services.download_service import DownloadService

    download_service = DownloadService()

    pdf_path = job.get("pdf_path", "")
    base_name = Path(pdf_path).stem if pdf_path else "translated"

    html_content = download_service.generate_print_html(pages, base_name)

    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html_content)
