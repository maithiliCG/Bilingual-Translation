"""
Download service — generates PDF and DOCX from completed jobs.

PDF Generation:
  Uses Playwright + Chromium to render reconstructed HTML to PDF.
  This handles MathJax, CSS Grid, Google Fonts, and base64 images correctly.

DOCX Generation:
  Direct HTML → DOCX using python-docx + BeautifulSoup.
  Parses the reconstructed HTML semantically to preserve text order,
  bilingual structure, images, and tables.
"""

import asyncio
import logging
import io
import re
from typing import Optional

from app.config import settings
from app.utils.gemini_utils import strip_unwanted_lines

logger = logging.getLogger(__name__)

# Full Google Fonts CSS for all supported Indian languages
ALL_FONTS_CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Noto+Sans+Telugu:wght@400;500;600;700&family=Noto+Sans+Devanagari:wght@400;500;600;700&family=Noto+Sans+Tamil:wght@400;500;600;700&family=Noto+Sans+Kannada:wght@400;500;600;700&family=Noto+Sans+Malayalam:wght@400;500;600;700&family=Noto+Sans+Bengali:wght@400;500;600;700&family=Noto+Sans+Gujarati:wght@400;500;600;700&family=Noto+Sans+Gurmukhi:wght@400;500;600;700&family=Noto+Sans+Oriya:wght@400;500;600;700&family=Noto+Nastaliq+Urdu:wght@400;500;600;700&family=Noto+Sans+Marathi:wght@400;500;600;700&display=swap" rel="stylesheet" />
<style>
@font-face {
    font-family: 'Gautami';
    src: url('http://localhost:8000/static/fonts/Gautami.ttf') format('truetype');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}
</style>
"""


class DownloadService:
    """Generates PDF and DOCX files from completed job data using Playwright."""

    # ─────────────────────────────────────────────────────────────
    #  HTML Template Builder
    # ─────────────────────────────────────────────────────────────

    def _build_print_html(self, pages: dict, file_name: str = "translated") -> str:
        """
        Build a complete HTML document optimized for Playwright PDF rendering.

        Includes:
        - MathJax 3 with inline/display math support
        - Google Fonts for 11 Indian languages
        - A4 page sizing with proper margins
        - A __RENDER_READY__ flag for Playwright to wait on
        - All reconstructed page HTML content
        """
        all_pages_html = ""
        sorted_pages = sorted(pages.items(), key=lambda x: int(x[0]))

        for page_num, page_data in sorted_pages:
            if page_data.get("status") != "completed":
                continue
            html = page_data.get("reconstructed_html", "")
            if not html:
                continue

            # Strip unwanted visual artifacts
            html = self._strip_unwanted_lines(html)

            all_pages_html += f"""
                <div class="page-content-section">
                    {html}
                </div>
            """

        html_document = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{file_name} - Translated</title>
    {ALL_FONTS_CSS}
    <script>
        // MathJax configuration
        MathJax = {{
            tex: {{
                inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
                displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
            }},
            startup: {{
                pageReady: () => {{
                    return MathJax.startup.defaultPageReady().then(() => {{
                        // After MathJax renders, wait for fonts + images
                        return Promise.all([
                            document.fonts.ready,
                            ...Array.from(document.images).map(img =>
                                img.complete ? Promise.resolve() : new Promise(res => {{
                                    img.onload = res;
                                    img.onerror = res;
                                }})
                            )
                        ]).then(() => {{
                            window.__RENDER_READY__ = true;
                        }});
                    }});
                }}
            }}
        }};
    </script>
    <script id="MathJax-script" async
            src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-svg.js"></script>
    <script>
        // Fallback: if MathJax CDN fails or no math on page, still set ready
        setTimeout(() => {{
            if (!window.__RENDER_READY__) {{
                Promise.all([
                    document.fonts.ready,
                    ...Array.from(document.images).map(img =>
                        img.complete ? Promise.resolve() : new Promise(res => {{
                            img.onload = res;
                            img.onerror = res;
                        }})
                    )
                ]).then(() => {{
                    window.__RENDER_READY__ = true;
                }});
            }}
        }}, 8000);
    </script>
    <style>
        @page {{
            size: A4;
            margin: 15mm 15mm 20mm 15mm;
        }}
        * {{
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            padding: 0;
            background: white;
            font-family: 'Gautami', 'Noto Sans Telugu', 'Inter', sans-serif;
            font-size: 13px;
            line-height: 1.5;
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: normal;
        }}
        ::-webkit-scrollbar {{ display: none; }}

        /* Each page section flows continuously, constrained to A4 content width */
        .page-content-section {{
            width: 100%;
            max-width: 680px;
            margin: 0 auto;
            position: relative;
            display: block;
            padding: 0 10px 0.5rem 10px;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }}
        /* Subtle separator between original pages */
        .page-content-section + .page-content-section {{
            border-top: 1px dashed #ddd;
            margin-top: 0.5rem;
            padding-top: 0.5rem;
        }}
        /* Allow continuous flow of text by omitting page-break controls */
        .translated-page > div {{
            /* continuous flow */
        }}
        .translated-page table {{
            /* continuous flow */
        }}

        img {{
            max-width: 100%;
            height: auto;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        td, th {{
            border: 1px solid #ccc;
            padding: 6px 10px;
        }}
        /* Remove leftover border-bottom from question divs */
        .translated-page > div {{
            border-bottom: none !important;
        }}
        hr {{
            display: none !important;
        }}
    </style>
</head>
<body>
    {all_pages_html}
</body>
</html>"""
        return html_document

    # ─────────────────────────────────────────────────────────────
    #  PDF Generation (Playwright + Chromium)
    # ─────────────────────────────────────────────────────────────

    async def generate_pdf(self, pages: dict, file_name: str = "translated") -> bytes:
        """
        Generate a PDF file from completed page HTML using Playwright + Chromium.

        This is the core rendering engine. It:
        1. Builds a complete HTML document with MathJax, fonts, and styling
        2. Launches headless Chromium via Playwright
        3. Waits for MathJax to typeset, fonts to load, images to decode
        4. Renders to A4 PDF with proper margins

        Args:
            pages: dict of page_number -> page_data with reconstructed_html
            file_name: Base name for the document title

        Returns:
            PDF bytes ready for download
        """
        from playwright.async_api import async_playwright

        html_content = self._build_print_html(pages, file_name)
        logger.info(f"Generating PDF via Playwright ({len(html_content)} chars HTML)...")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                page = await browser.new_page()

                # Load HTML and wait for all network requests to settle
                # (Google Fonts CSS, MathJax CDN script)
                await page.set_content(html_content, wait_until='networkidle')

                # Wait for the __RENDER_READY__ flag
                # (set after MathJax finishes + fonts loaded + all images decoded)
                try:
                    await page.wait_for_function(
                        "() => window.__RENDER_READY__ === true",
                        timeout=45000
                    )
                    logger.info("Render ready: MathJax, fonts, and images all loaded")
                except Exception as wait_err:
                    logger.warning(
                        f"Render ready wait timed out ({wait_err}) — "
                        f"proceeding with PDF generation anyway"
                    )

                # Small buffer for Chromium to finish any final paints
                await asyncio.sleep(0.5)

                # Generate the PDF
                pdf_bytes = await page.pdf(
                    format='A4',
                    margin={
                        'top': '15mm',
                        'right': '15mm',
                        'bottom': '20mm',
                        'left': '15mm',
                    },
                    print_background=True,
                    prefer_css_page_size=True,
                )

                await browser.close()

            logger.info(f"PDF generated successfully: {len(pdf_bytes):,} bytes")
            return pdf_bytes

        except Exception as e:
            logger.error(f"Playwright PDF generation failed: {e}", exc_info=True)
            raise RuntimeError(f"PDF generation failed: {e}")

    # ─────────────────────────────────────────────────────────────
    #  DOCX Generation (Direct HTML → python-docx)
    # ─────────────────────────────────────────────────────────────

    async def generate_docx(
        self,
        pages: dict,
        file_name: str = "translated",
        lang_code: str = "",
    ) -> io.BytesIO:
        """
        Generate a DOCX file by directly parsing HTML and building
        the document with python-docx + BeautifulSoup.

        This preserves text semantics, bilingual structure, spacing,
        and images correctly — unlike pdf2docx which reverse-engineers
        PDF layout and often merges/reorders sentences.

        Args:
            pages: dict of page_number -> page_data with reconstructed_html
            file_name: Base name for the document title
            lang_code: Target language code (for font selection)

        Returns:
            BytesIO buffer containing the .docx file
        """
        from app.services.html_to_docx_service import HtmlToDocxConverter

        try:
            logger.info(
                f"DOCX generation: Converting HTML → DOCX directly "
                f"(lang={lang_code}, pages={len(pages)})"
            )

            # Run the conversion in a thread to avoid blocking the event loop
            converter = HtmlToDocxConverter(lang_code=lang_code)
            buffer = await asyncio.to_thread(converter.convert, pages)

            logger.info(
                f"DOCX generated successfully: {buffer.getbuffer().nbytes:,} bytes "
                f"(lang={lang_code})"
            )
            return buffer

        except Exception as e:
            logger.error(f"DOCX generation failed: {e}", exc_info=True)
            raise RuntimeError(f"DOCX generation failed: {e}")

    # ─────────────────────────────────────────────────────────────
    #  Legacy / Utility Methods
    # ─────────────────────────────────────────────────────────────

    def generate_print_html(self, pages: dict, file_name: str = "translated") -> str:
        """
        Generate a complete HTML document for browser preview.
        Same as _build_print_html but as a public method.
        Useful for previewing the content before PDF generation.
        """
        return self._build_print_html(pages, file_name)

    def _strip_unwanted_lines(self, html: str) -> str:
        """Delegates to shared utility. Kept for backward compatibility."""
        return strip_unwanted_lines(html)
