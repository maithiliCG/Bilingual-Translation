"""
Pipeline orchestrator — coordinates the full PDF translation flow.

Flow: PDF → Split Pages → GLM-OCR → Translate → Reconstruct → Stream
"""

import asyncio
import logging
import re
import uuid
import json
import base64
from pathlib import Path
from typing import Dict, Any, AsyncGenerator, Optional

from app.config import settings
from app.services.pdf_service import PDFService
from app.services.glm_ocr_service import GLMOCRService
from app.services.glm_ocr_local_service import GLMOCRLocalService
from app.services.translation_service import TranslationService
from app.services.reconstruction_service import ReconstructionService
from app.models.schemas import (
    JobStatus,
    PageResult,
    JobStatusResponse,
    SSEPageEvent,
    SSEProgressEvent,
)
from app.core.exceptions import PipelineError
from app.utils.file_utils import bytes_to_base64

logger = logging.getLogger(__name__)


class JobStore:
    """In-memory job storage.

    WARNING: All job data is lost when the server restarts (including uvicorn --reload).
    Active SSE streams will break, and download buttons for completed jobs will return 404.
    For production, replace with Redis or a database-backed store.
    """

    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create_job(self, job_id: str, pdf_path: str, target_language: str, total_pages: int, translation_mode: str = "bilingual"):
        import time
        self._jobs[job_id] = {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "pdf_path": pdf_path,
            "target_language": target_language,
            "total_pages": total_pages,
            "completed_pages": 0,
            "current_stage": "initialized",
            "message": "Job created, waiting to start...",
            "pages": {},
            "error": None,
            "created_at": time.time(),
            "completed_at": None,
            "translation_mode": translation_mode,
        }

    def get_job(self, job_id: str) -> Optional[Dict]:
        return self._jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs):
        if job_id in self._jobs:
            if kwargs.get("status") in (JobStatus.COMPLETED, JobStatus.FAILED):
                import time
                kwargs["completed_at"] = time.time()
            self._jobs[job_id].update(kwargs)

    def update_page(self, job_id: str, page_number: int, **kwargs):
        if job_id in self._jobs:
            if page_number not in self._jobs[job_id]["pages"]:
                self._jobs[job_id]["pages"][page_number] = {
                    "page_number": page_number,
                    "status": "pending",
                }
            self._jobs[job_id]["pages"][page_number].update(kwargs)

    def delete_job(self, job_id: str):
        self._jobs.pop(job_id, None)

    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """Remove jobs older than max_age_hours"""
        import time
        current_time = time.time()
        to_delete = []
        for job_id, job in self._jobs.items():
            completed_at = job.get('completed_at', 0)
            if completed_at and completed_at < current_time - (max_age_hours * 3600):
                to_delete.append(job_id)
        for job_id in to_delete:
            logger.info(f"Cleaning up old job: {job_id}")
            self.delete_job(job_id)
        return len(to_delete)


# Global job store
job_store = JobStore()


class Pipeline:
    """Orchestrates the full PDF → OCR → Translate → Reconstruct pipeline."""

    def __init__(self):
        self.pdf_service = PDFService()
        # Use local or remote GLM-OCR based on config
        if settings.GLM_USE_LOCAL:
            self.glm_ocr_service = GLMOCRLocalService()
            logger.info("Pipeline using LOCAL GLM-OCR model")
        else:
            self.glm_ocr_service = GLMOCRService()
            logger.info("Pipeline using REMOTE GLM-OCR API")
        self.translation_service = TranslationService()
        self.reconstruction_service = ReconstructionService()
        # Concurrency limiter for Gemini API calls (translation + reconstruction)
        self._gemini_semaphore = asyncio.Semaphore(3)

    async def process_pdf(
        self,
        job_id: str,
        pdf_path: str,
        target_language: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Process a PDF through the entire pipeline, yielding SSE events.
        
        Args:
            job_id: Unique job identifier
            pdf_path: Path to uploaded PDF
            target_language: Target language code
        
        Yields:
            SSE event dicts for each page and progress update
        """
        try:
            # Stage 0: Get page count
            total_pages = self.pdf_service.get_page_count(pdf_path)

            # Only create job if not already created by /start endpoint (avoid race condition)
            existing = job_store.get_job(job_id)
            if not existing:
                job_store.create_job(job_id, pdf_path, target_language, total_pages, translation_mode="bilingual")
                translation_mode = "bilingual"
            else:
                # Update with fresh page count in case it wasn't set
                job_store.update_job(job_id, total_pages=total_pages)
                translation_mode = existing.get("translation_mode", "bilingual")

            job_store.update_job(
                job_id,
                status=JobStatus.PROCESSING,
                current_stage="starting",
                message=f"Processing PDF with {total_pages} pages...",
            )

            yield self._progress_event(
                job_id, f"Starting pipeline — {total_pages} pages detected",
                "starting", total_pages=total_pages
            )

            # Define a helper function to run OCR for a page asynchronously
            async def run_ocr_for_page(page_index):
                page_img_bytes = await asyncio.to_thread(
                    self.pdf_service.render_page_image, pdf_path, page_index, settings.RENDER_DPI
                )
                img_b64 = bytes_to_base64(page_img_bytes)
                ocr_result = await self.glm_ocr_service.parse_page_image(page_img_bytes)
                return page_img_bytes, img_b64, ocr_result

            # Start the first OCR task if there are pages
            next_ocr_task = None
            if total_pages > 0:
                next_ocr_task = asyncio.create_task(run_ocr_for_page(0))

            # Process each page sequentially for streaming, but pipelined
            for page_idx in range(total_pages):
                page_num = page_idx + 1

                try:
                    # Update status
                    job_store.update_page(job_id, page_num, status="processing")

                    yield self._progress_event(
                        job_id,
                        f"Page {page_num}/{total_pages}: Extracting content with GLM-OCR...",
                        "ocr_extraction", page_number=page_num,
                        total_pages=total_pages,
                    )

                    # Await the current OCR task
                    page_image_bytes, page_image_b64, ocr_result = await next_ocr_task

                    # Pre-fetch the NEXT page OCR while we translate/reconstruct the current one
                    if page_idx + 1 < total_pages:
                        next_ocr_task = asyncio.create_task(run_ocr_for_page(page_idx + 1))

                    original_markdown = ocr_result.get("md_results", "")
                    layout_details = ocr_result.get("layout_details", [])

                    # Debug: check if OCR extracted any image crop tags
                    crop_tags = re.findall(r'!\[.*?\]\(crop:.*?\)', original_markdown)
                    logger.info(
                        f"Page {page_num}: OCR extracted {len(original_markdown)} chars, "
                        f"{len(crop_tags)} crop image tag(s) found"
                    )
                    if crop_tags:
                        for ct in crop_tags:
                            logger.info(f"  Crop tag: {ct}")

                   

                    # --- DocLayout-YOLO: Detect figures for precise cropping ---
                    figure_detections = []
                    try:
                        from app.services.layout_detection_service import LayoutDetectionService
                        layout_detector = LayoutDetectionService()
                        figure_detections = await layout_detector.detect_figures(page_image_bytes)
                        if figure_detections:
                            logger.info(
                                f"Page {page_num}: YOLO detected {len(figure_detections)} figure(s) "
                                f"for precise cropping"
                            )
                            # Inject YOLO figures that are NOT already represented by GLM-OCR crop tags
                            # Uses IoU-based matching to avoid duplicates
                            from app.services.layout_detection_service import compute_iou
                            existing_crop_coords = re.findall(
                                r'crop:\s*\[?\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)',
                                original_markdown, flags=re.IGNORECASE
                            )
                            existing_boxes = [[int(y1), int(x1), int(y2), int(x2)] for y1, x1, y2, x2 in existing_crop_coords]
                            
                            injected_images = []
                            for fig in figure_detections:
                                bbox = fig.get("bbox_normalized")
                                if not bbox:
                                    continue
                                ymin, xmin, ymax, xmax = bbox
                                # Check if any existing GLM-OCR crop overlaps significantly with this YOLO detection
                                is_duplicate = any(
                                    compute_iou([ymin, xmin, ymax, xmax], existing_box) > 0.3
                                    for existing_box in existing_boxes
                                )
                                if not is_duplicate:
                                    img_tag = f"![image](crop:[{ymin}, {xmin}, {ymax}, {xmax}])"
                                    # Store tuple of (ymin, img_tag) so we can sort by vertical position
                                    injected_images.append((ymin, img_tag))
                                    logger.info(f"Page {page_num}: Injecting YOLO figure [{ymin},{xmin},{ymax},{xmax}] (no GLM-OCR overlap)")
                                else:
                                    logger.info(f"Page {page_num}: Skipping YOLO figure [{ymin},{xmin},{ymax},{xmax}] (overlaps existing GLM-OCR crop)")
                            
                            if injected_images:
                                # Sort by vertical position descending (bottom to top)
                                # so that inserting into a list doesn't shift the indices for subsequent insertions.
                                injected_images.sort(key=lambda x: x[0], reverse=True)
                                
                                lines = original_markdown.split('\\n')
                                for ymin, img_tag in injected_images:
                                    # Calculate proportional line index based on normalized Y coordinate (0-1000)
                                    target_line_idx = int((ymin / 1000.0) * len(lines))
                                    # Ensure we don't go out of bounds
                                    target_line_idx = max(0, min(target_line_idx, len(lines)))
                                    # Insert the tag
                                    lines.insert(target_line_idx, f"\\n{img_tag}\\n")
                                    
                                original_markdown = "\\n".join(lines)
                    except Exception as yolo_err:
                        logger.warning(f"Page {page_num}: YOLO detection failed ({yolo_err}), using GLM-OCR coordinates")

                    # layout_details for a single image is usually at index 0
                    page_layout = (
                        layout_details[0]
                        if layout_details and isinstance(layout_details[0], list)
                        else layout_details
                    )

                    # --- TOKEN REPLACER ARCHITECTURE ---
                    # Hide complex crop coordinates from the LLMs to prevent truncation/corruption
                    image_token_map = {}
                    
                    def tokenize_image_tag(match):
                        original_tag = match.group(0)
                        token = f"<IMG_{str(uuid.uuid4())[:8].upper()}>"
                        image_token_map[token] = original_tag
                        return token
                        
                    tokenized_markdown = re.sub(
                        r'!\[.*?\]\s*\(crop:\[?\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]?\)',
                        tokenize_image_tag,
                        original_markdown,
                        flags=re.IGNORECASE
                    )
                    
                    if image_token_map:
                        logger.info(f"Page {page_num}: Tokenized {len(image_token_map)} image tags to hide from LLM")

                    # --- Stage 3: Translate ---
                    yield self._progress_event(
                        job_id,
                        f"Page {page_num}/{total_pages}: Translating content...",
                        "translation", page_number=page_num,
                        total_pages=total_pages,
                    )

                    logger.info(
                        f"Page {page_num}: Sending to translation — "
                        f"language='{target_language}', input={len(tokenized_markdown)} chars, "
                        f"preview: {tokenized_markdown[:100]}..."
                    )

                    translated_markdown = await self.translation_service.translate_markdown(
                        tokenized_markdown,
                        target_language,
                        page_num,
                        translation_mode=translation_mode,
                    )

                    logger.info(
                        f"Page {page_num}: Translation result — "
                        f"output={len(translated_markdown)} chars, "
                        f"preview: {translated_markdown[:100]}..."
                    )

                    # --- UNTOKENIZE IMAGE TAGS ---
                    # Restore the original crop coordinates so Reconstruction Service can use them to reference the image!
                    if image_token_map:
                        for token, original_tag in image_token_map.items():
                            translated_markdown = translated_markdown.replace(token, original_tag)
                        logger.info(f"Page {page_num}: Untokenized {len(image_token_map)} image tags into translated markdown")

                    # --- Stage 4: Reconstruct Layout ---
                    yield self._progress_event(
                        job_id,
                        f"Page {page_num}/{total_pages}: Reconstructing layout...",
                        "reconstruction", page_number=page_num,
                        total_pages=total_pages,
                    )

                    reconstructed_html = (
                        await self.reconstruction_service.reconstruct_page(
                            page_image_bytes,
                            translated_markdown,
                            page_layout,
                            target_language,
                            page_num,
                            figure_detections=figure_detections,
                            translation_mode=translation_mode,
                        )
                    )

                    # --- Page Complete ---
                    completed_count = job_store.get_job(job_id)["completed_pages"] + 1
                    job_store.update_job(job_id, completed_pages=completed_count)
                    job_store.update_page(
                        job_id,
                        page_num,
                        status="completed",
                        original_markdown=original_markdown,
                        translated_markdown=translated_markdown,
                        reconstructed_html=reconstructed_html,
                        original_image_base64=page_image_b64,
                    )

                    # Yield page complete event
                    yield {
                        "event_type": "page_complete",
                        "job_id": job_id,
                        "page_number": page_num,
                        "total_pages": total_pages,
                        "status": "completed",
                        "original_image_base64": page_image_b64,
                        "original_markdown": original_markdown,
                        "translated_markdown": translated_markdown,
                        "reconstructed_html": reconstructed_html,
                    }

                    logger.info(
                        f"Page {page_num}/{total_pages} completed for job {job_id}"
                    )

                except Exception as page_error:
                    logger.error(
                        f"Error processing page {page_num}: {page_error}",
                        exc_info=True,
                    )

                    job_store.update_page(
                        job_id, page_num,
                        status="failed",
                        error=str(page_error),
                    )

                    yield {
                        "event_type": "page_error",
                        "job_id": job_id,
                        "page_number": page_num,
                        "total_pages": total_pages,
                        "status": "failed",
                        "error": str(page_error),
                    }

            # --- All Pages Complete ---
            job_store.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                current_stage="completed",
                message=f"All {total_pages} pages processed successfully!",
            )

            yield {
                "event_type": "job_complete",
                "job_id": job_id,
                "total_pages": total_pages,
                "status": "completed",
                "message": f"All {total_pages} pages processed successfully!",
            }

        except Exception as e:
            logger.error(f"Pipeline error for job {job_id}: {e}", exc_info=True)

            job_store.update_job(
                job_id,
                status=JobStatus.FAILED,
                current_stage="error",
                message=str(e),
                error=str(e),
            )

            yield {
                "event_type": "job_error",
                "job_id": job_id,
                "status": "failed",
                "error": str(e),
                "message": f"Pipeline failed: {e}",
            }



    def _progress_event(
        self, job_id: str, message: str, stage: str,
        page_number: int = None, total_pages: int = 0
    ) -> dict:
        """Create a progress event dict."""
        job_store.update_job(
            job_id, current_stage=stage, message=message
        )
        return {
            "event_type": "progress",
            "job_id": job_id,
            "message": message,
            "stage": stage,
            "page_number": page_number,
            "total_pages": total_pages,
        }

    def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        """Get current job status."""
        job = job_store.get_job(job_id)
        if not job:
            return None

        pages = []
        for pn, pdata in sorted(job.get("pages", {}).items()):
            pages.append(PageResult(
                page_number=pdata.get("page_number", pn),
                status=pdata.get("status", "pending"),
                original_markdown=pdata.get("original_markdown"),
                translated_markdown=pdata.get("translated_markdown"),
                reconstructed_html=pdata.get("reconstructed_html"),
                error=pdata.get("error"),
            ))

        return JobStatusResponse(
            job_id=job["job_id"],
            status=job["status"],
            total_pages=job["total_pages"],
            completed_pages=job["completed_pages"],
            current_stage=job.get("current_stage", ""),
            message=job.get("message", ""),
            pages=pages,
            error=job.get("error"),
        )
