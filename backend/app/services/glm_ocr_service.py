"""
GLM-OCR service — uses remote GLM-OCR API server for extraction.

Sends page images (as base64) to the remote endpoint and receives
structured JSON + Markdown results.

API Endpoint: POST http://45.249.79.13:5002/glmocr/parse
Request:  { "images": ["data:image/png;base64,..."] }
Response: { "json_result": [[{...}]], "markdown_result": "..." }
"""

import asyncio
import logging
import io
import re
import base64
import time
from typing import Dict, Any, Optional

import httpx
from PIL import Image

from app.config import settings
from app.core.exceptions import GLMOCRError

logger = logging.getLogger(__name__)


class GLMOCRService:
    """Uses remote GLM-OCR API server for Markdown + layout extraction."""

    def __init__(self):
        self.api_url = settings.GLM_API_URL
        self.timeout = settings.GLM_OCR_TIMEOUT
        logger.info(f"GLM-OCR Service initialized → remote API: {self.api_url}")

    async def parse_page_image(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Send a page image to the remote GLM-OCR API for extraction.

        Args:
            image_bytes: PNG image bytes of a PDF page

        Returns:
            Dict with keys:
              - md_results: Markdown string extracted from the page
              - layout_details: List of layout elements with bounding boxes
              - data_info: Additional metadata
        """
        try:
            original_size_kb = len(image_bytes) / 1024

            # Optimize image for API: resize + compress as JPEG for faster upload
            optimized_bytes, mime_type = self.optimize_for_api(image_bytes)
            optimized_size_kb = len(optimized_bytes) / 1024

            # Convert to base64 data URI
            b64_data = base64.b64encode(optimized_bytes).decode("utf-8")
            data_uri = f"data:{mime_type};base64,{b64_data}"

            payload = {
                "images": [data_uri]
            }

            logger.info(
                f"Sending image to GLM-OCR API "
                f"(original: {original_size_kb:.0f}KB → optimized: {optimized_size_kb:.0f}KB, "
                f"format: {mime_type})..."
            )

            # Make the API call asynchronously
            start_time = time.time()

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            elapsed = time.time() - start_time

            # Check for HTTP errors
            if response.status_code != 200:
                error_detail = response.text[:500]
                raise GLMOCRError(
                    f"GLM-OCR API returned status {response.status_code}: {error_detail}"
                )

            result = response.json()

            # Extract markdown result
            markdown_content = result.get("markdown_result", "")

            # Extract layout/JSON details
            json_result = result.get("json_result", [])
            # json_result is typically [[{...}, {...}]] — list of pages, each page a list of elements
            layout_details = json_result[0] if json_result else []

            # Clean up markdown wrapping
            markdown_content = self._clean_markdown(markdown_content)

            # Post-process: Remove image tags that appear immediately before markdown tables
            markdown_content = self._remove_table_image_duplicates(markdown_content)

            logger.info(
                f"GLM-OCR API response in {elapsed:.1f}s — "
                f"{len(markdown_content)} chars, {len(layout_details)} layout elements"
            )

            return {
                "md_results": markdown_content,
                "layout_details": layout_details,
                "layout_visualization": [],
                "data_info": {},
                "usage": {},
            }

        except GLMOCRError:
            raise
        except httpx.TimeoutException:
            raise GLMOCRError(
                f"GLM-OCR API request timed out after {self.timeout}s. "
                f"The server at {self.api_url} may be overloaded or unreachable."
            )
        except httpx.ConnectError:
            raise GLMOCRError(
                f"Could not connect to GLM-OCR API at {self.api_url}. "
                f"Check if the server is running and accessible."
            )
        except Exception as e:
            logger.error(f"GLM-OCR API error: {e}", exc_info=True)
            raise GLMOCRError(f"GLM-OCR API call failed: {e}")

    def optimize_for_api(self, image_bytes: bytes) -> tuple:
        """
        Optimize image for the remote API:
        1. Resize if too large (cap dimensions)
        2. Convert to JPEG for much smaller file size (PNG can be 3-5x larger)
        3. Use quality 85 for good balance of clarity and size
        
        Returns:
            Tuple of (optimized_bytes, mime_type)
        """
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            original_w, original_h = img.width, img.height
            max_dim = settings.OCR_MAX_IMAGE_DIM
            resized = False

            if max(img.width, img.height) > max_dim:
                scale_factor = max_dim / max(img.width, img.height)
                new_size = (int(img.width * scale_factor), int(img.height * scale_factor))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                resized = True
                logger.info(
                    f"Resized image from {original_w}x{original_h} → "
                    f"{img.width}x{img.height} for API"
                )

            # Save as JPEG (much smaller than PNG for document images)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            jpeg_bytes = buf.getvalue()

            if not resized:
                logger.info(
                    f"Image {original_w}x{original_h} within limits, "
                    f"compressed PNG→JPEG: {len(image_bytes)/1024:.0f}KB → {len(jpeg_bytes)/1024:.0f}KB"
                )

            return jpeg_bytes, "image/jpeg"

        except Exception as e:
            logger.warning(f"Image optimization failed, sending original PNG: {e}")
            return image_bytes, "image/png"

    def _clean_markdown(self, markdown_content: str) -> str:
        """Clean up markdown content from the API response."""
        markdown_content = markdown_content.strip()

        # Remove wrapping code block markers
        if markdown_content.startswith("```markdown"):
            markdown_content = markdown_content[len("```markdown"):].strip()
        if markdown_content.startswith("```"):
            markdown_content = markdown_content[3:].strip()
        if markdown_content.endswith("```"):
            markdown_content = markdown_content[:-3].strip()

        return markdown_content

    def _remove_table_image_duplicates(self, markdown_content: str) -> str:
        """
        Remove image tags that appear immediately before markdown tables.
        The OCR sometimes creates both an image tag AND a text table
        for the same table content. We keep the text table and remove the image.
        """
        table_pattern = re.compile(
            r'(!\[image\]\(crop:[^)]+\))\s*\n+((?:\|[^\n]+\|\s*\n)+)',
            re.MULTILINE
        )

        def remove_table_images(match):
            table_content = match.group(2)
            # Check if this is actually a table (has header separator like |---|---|)
            if re.search(r'\|\s*[-:]+\s*\|', table_content):
                logger.info("Removed duplicate image tag before markdown table")
                return table_content  # Keep only the table, remove image
            else:
                return match.group(0)  # Keep both if not a proper table

        return table_pattern.sub(remove_table_images, markdown_content)

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
