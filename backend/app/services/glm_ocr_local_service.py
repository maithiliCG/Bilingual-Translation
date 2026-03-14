"""
GLM-OCR Local service — uses locally downloaded GLM-OCR model for extraction.

Runs the zai-org/GLM-OCR model locally via Hugging Face Transformers.
Produces the same output format as the remote GLMOCRService so they
can be swapped transparently.

Model: zai-org/GLM-OCR (cached at ~/.cache/huggingface/hub/models--zai-org--GLM-OCR)
"""

import asyncio
import logging
import io
import re
import time
from typing import Dict, Any, Optional

import torch
from PIL import Image

from app.config import settings
from app.utils.gemini_utils import remove_table_image_duplicates

logger = logging.getLogger(__name__)

# Global model/processor singletons — loaded once, reused across requests
_model = None
_processor = None
_model_lock = None


def _get_model_lock():
    """Lazy-init asyncio.Lock inside the running event loop (Python 3.10+ safe)."""
    global _model_lock
    if _model_lock is None:
        _model_lock = asyncio.Lock()
    return _model_lock


def _load_model_sync():
    """Load model and processor (blocking, called once)."""
    global _model, _processor

    if _model is not None and _processor is not None:
        return

    from transformers import AutoProcessor, AutoModelForImageTextToText

    model_path = settings.GLM_LOCAL_MODEL_PATH

    logger.info(f"Loading local GLM-OCR model from: {model_path}")
    start = time.time()

    _processor = AutoProcessor.from_pretrained(model_path)

    # Determine device and dtype
    # On Apple Silicon (MPS), use float32 on CPU to avoid Metal memory allocation failures
    # MPS can run out of GPU memory with large vision models
    if torch.backends.mps.is_available():
        logger.info("Apple Silicon detected — loading model on CPU (float32) to avoid MPS memory issues")
        _model = AutoModelForImageTextToText.from_pretrained(
            pretrained_model_name_or_path=model_path,
            torch_dtype=torch.float32,
            device_map="cpu",
        )
    elif torch.cuda.is_available():
        logger.info("CUDA GPU detected — loading model with auto dtype/device")
        _model = AutoModelForImageTextToText.from_pretrained(
            pretrained_model_name_or_path=model_path,
            torch_dtype="auto",
            device_map="auto",
        )
    else:
        logger.info("No GPU available — loading model on CPU")
        _model = AutoModelForImageTextToText.from_pretrained(
            pretrained_model_name_or_path=model_path,
            torch_dtype=torch.float32,
            device_map="cpu",
        )

    elapsed = time.time() - start
    logger.info(
        f"GLM-OCR local model loaded in {elapsed:.1f}s "
        f"(device: {next(_model.parameters()).device})"
    )


class GLMOCRLocalService:
    """Uses locally downloaded GLM-OCR model for Markdown extraction."""

    def __init__(self):
        self.model_path = settings.GLM_LOCAL_MODEL_PATH
        self.max_new_tokens = getattr(settings, "GLM_LOCAL_MAX_TOKENS", 8192)
        logger.info(f"GLM-OCR Local Service initialized → model: {self.model_path}")

    async def _ensure_model_loaded(self):
        """Ensure model is loaded (thread-safe, lazy load on first call)."""
        global _model, _processor
        if _model is None or _processor is None:
            async with _get_model_lock():
                if _model is None or _processor is None:
                    await asyncio.to_thread(_load_model_sync)

    async def parse_page_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Parse a page image using the local GLM-OCR model.

        Args:
            image_bytes: PNG image bytes of a PDF page

        Returns:
            Dict with keys:
              - md_results: Markdown string extracted from the page
              - layout_details: List of layout elements (empty for local model)
              - data_info: Additional metadata
        """
        from app.core.exceptions import GLMOCRError

        try:
            await self._ensure_model_loaded()

            original_size_kb = len(image_bytes) / 1024

            # Open image
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            original_w, original_h = img.width, img.height

            # For local inference, keep resolution reasonable for memory constraints
            # 1280px is a sweet spot: good OCR quality without GPU/CPU memory blowup
            local_max_dim = 1280
            if max(img.width, img.height) > local_max_dim:
                scale_factor = local_max_dim / max(img.width, img.height)
                new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(
                    f"Resized image from {original_w}x{original_h} → "
                    f"{img.width}x{img.height} for local inference"
                )

            logger.info(
                f"Sending image to local GLM-OCR model "
                f"(original: {original_size_kb:.0f}KB, "
                f"dims: {img.width}x{img.height})..."
            )

            # Build the message in the format expected by the model
            # Pass the PIL Image directly — no need to re-encode
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": img},
                        {"type": "text", "text": "Text Recognition:"},
                    ],
                }
            ]

            start_time = time.time()

            # Run inference in a thread to avoid blocking the event loop
            markdown_content = await asyncio.to_thread(
                self._run_inference, messages
            )

            elapsed = time.time() - start_time

            # Clean up markdown wrapping
            markdown_content = self._clean_markdown(markdown_content)

            # Post-process: Remove image tags that appear immediately before markdown tables
            markdown_content = remove_table_image_duplicates(markdown_content)

            logger.info(
                f"GLM-OCR local inference in {elapsed:.1f}s — "
                f"{len(markdown_content)} chars extracted"
            )

            return {
                "md_results": markdown_content,
                "layout_details": [],
                "layout_visualization": [],
                "data_info": {"inference_mode": "local"},
                "usage": {"inference_time_seconds": round(elapsed, 2)},
            }

        except Exception as e:
            logger.error(f"GLM-OCR local inference error: {e}", exc_info=True)
            raise GLMOCRError(f"GLM-OCR local inference failed: {e}")

    def _run_inference(self, messages: list) -> str:
        """Run model inference (blocking, runs in thread)."""
        global _model, _processor

        inputs = _processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(_model.device)

        # Remove token_type_ids if present (some models don't need it)
        inputs.pop("token_type_ids", None)

        with torch.no_grad():
            generated_ids = _model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
            )

        # Decode only the generated tokens (skip the input prompt)
        output_text = _processor.decode(
            generated_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )

        # Clean up memory after inference
        del inputs, generated_ids
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()

        return output_text.strip()

    def optimize_for_api(self, image_bytes: bytes) -> tuple:
        """
        Optimize image — mirrors the remote service interface for compatibility.
        Returns (optimized_bytes, mime_type).
        """
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            max_dim = settings.OCR_MAX_IMAGE_DIM

            if max(img.width, img.height) > max_dim:
                scale_factor = max_dim / max(img.width, img.height)
                new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            return buf.getvalue(), "image/jpeg"
        except Exception as e:
            logger.warning(f"Image optimization failed: {e}")
            return image_bytes, "image/png"

    def _clean_markdown(self, markdown_content: str) -> str:
        """Clean up markdown content from the model output."""
        markdown_content = markdown_content.strip()

        # Remove <think>...</think> blocks if present
        markdown_content = re.sub(
            r'<think>.*?</think>', '', markdown_content, flags=re.DOTALL
        ).strip()

        # Remove wrapping code block markers
        if markdown_content.startswith("```markdown"):
            markdown_content = markdown_content[len("```markdown"):].strip()
        if markdown_content.startswith("```"):
            markdown_content = markdown_content[3:].strip()
        if markdown_content.endswith("```"):
            markdown_content = markdown_content[:-3].strip()

        return markdown_content

    def _remove_table_image_duplicates(self, markdown_content: str) -> str:
        """Delegates to shared utility. Kept for backward compatibility."""
        return remove_table_image_duplicates(markdown_content)

    async def parse_pdf_bytes(
        self,
        pdf_bytes: bytes,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError("parse_pdf_bytes not used in single-page pipeline")

    def extract_page_layout_details(
        self, layout_details: list, page_index: int
    ) -> list:
        return []
