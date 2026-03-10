"""PDF processing service — splitting PDFs and rendering page images."""

import io
import logging
from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF

from app.core.exceptions import PDFProcessingError

logger = logging.getLogger(__name__)


class PDFService:
    """Handles PDF splitting and page image rendering."""

    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """Get the total number of pages in a PDF."""
        try:
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception as e:
            raise PDFProcessingError(f"Failed to open PDF: {e}")

    @staticmethod
    def render_page_image(pdf_path: str, page_number: int, dpi: int = 200) -> bytes:
        """
        Render a single PDF page as a PNG image.
        
        Args:
            pdf_path: Path to the PDF file
            page_number: 0-indexed page number
            dpi: Resolution for rendering (200 DPI gives good OCR quality)
        
        Returns:
            PNG image bytes
        """
        try:
            doc = fitz.open(pdf_path)
            if page_number >= len(doc):
                raise PDFProcessingError(
                    f"Page {page_number} out of range (total: {len(doc)})"
                )

            page = doc[page_number]
            # Render at specified DPI
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image_bytes = pix.tobytes("png")

            doc.close()

            # Post-process: sharpen and enhance contrast for better OCR accuracy
            try:
                from PIL import Image as PILImage, ImageFilter, ImageEnhance
                import io as _io
                pil_img = PILImage.open(_io.BytesIO(image_bytes)).convert("RGB")
                # Unsharp mask for edge sharpening (improves text & chart clarity)
                pil_img = pil_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=150, threshold=3))
                # Mild contrast boost to make text pop against background
                pil_img = ImageEnhance.Contrast(pil_img).enhance(1.15)
                buf = _io.BytesIO()
                pil_img.save(buf, format="PNG", optimize=False)
                image_bytes = buf.getvalue()
                logger.info(f"Page {page_number}: Sharpened & contrast-enhanced image ({len(image_bytes)} bytes)")
            except Exception as enh_err:
                logger.warning(f"Image enhancement failed (continuing with raw render): {enh_err}")

            return image_bytes

        except PDFProcessingError:
            raise
        except Exception as e:
            raise PDFProcessingError(f"Failed to render page {page_number}: {e}")

    @staticmethod
    def split_pdf_to_chunks(
        pdf_path: str, chunk_size: int = 50
    ) -> List[Tuple[int, int]]:
        """
        Split a PDF into page ranges for chunked processing.
        GLM-OCR MaaS API supports max 100 pages per request,
        but we use smaller chunks for better streaming.
        
        Args:
            pdf_path: Path to the PDF
            chunk_size: Max pages per chunk
        
        Returns:
            List of (start_page, end_page) tuples (1-indexed for GLM API)
        """
        total_pages = PDFService.get_page_count(pdf_path)
        chunks = []

        for start in range(0, total_pages, chunk_size):
            end = min(start + chunk_size, total_pages)
            # GLM API uses 1-indexed pages
            chunks.append((start + 1, end))

        logger.info(
            f"Split PDF ({total_pages} pages) into {len(chunks)} chunks: {chunks}"
        )
        return chunks

    @staticmethod
    def get_pdf_bytes_for_chunk(
        pdf_path: str, start_page: int, end_page: int
    ) -> bytes:
        """
        Extract a range of pages from a PDF as bytes.
        Used for sending chunks to GLM-OCR.
        
        Args:
            pdf_path: Path to original PDF
            start_page: 1-indexed start page
            end_page: 1-indexed end page (inclusive)
        
        Returns:
            PDF bytes for the chunk
        """
        try:
            src_doc = fitz.open(pdf_path)
            new_doc = fitz.open()

            # PyMuPDF uses 0-indexed pages
            for page_num in range(start_page - 1, end_page):
                if page_num < len(src_doc):
                    new_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)

            pdf_bytes = new_doc.tobytes()
            new_doc.close()
            src_doc.close()

            return pdf_bytes

        except Exception as e:
            raise PDFProcessingError(
                f"Failed to extract pages {start_page}-{end_page}: {e}"
            )
