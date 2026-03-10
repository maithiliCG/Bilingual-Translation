"""Layout reconstruction service using Gemini multimodal."""

import asyncio
import logging
import json
import base64
import re
import io
from typing import Optional
from PIL import Image

from google import genai
from google.genai import types

from app.config import settings
from app.core.exceptions import ReconstructionError
from app.models.enums import get_language_name
from app.utils.file_utils import bytes_to_base64

logger = logging.getLogger(__name__)


async def call_gemini_with_timeout(client, model, contents, config, timeout=180):
    """Call Gemini API with timeout protection"""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=contents,
                config=config,
            ),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        raise ReconstructionError(f"Gemini API call timed out after {timeout} seconds")


class ReconstructionService:
    """
    Reconstructs translated content using Gemini multimodal.
    Sends the original page image + translated Markdown + layout details
    to Gemini so it can organize the content to match the original page structure.
    """

    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    async def reconstruct_page(
        self,
        page_image_bytes: bytes,
        translated_markdown: str,
        layout_details: list,
        target_language_code: str,
        page_number: int = 1,
        figure_detections: list = None,
        translation_mode: str = "bilingual",
    ) -> str:
        """
        Use Gemini to organize translated content matching original page layout.
        """
        if not translated_markdown or not translated_markdown.strip():
            b64_img = bytes_to_base64(page_image_bytes)
            return f'<div class="image-page" style="text-align:center;padding:8px;"><img src="data:image/png;base64,{b64_img}" style="max-width:100%;height:auto;" alt="Page {page_number}"></div>'

        import re as _re
        text_only = _re.sub(r'!\[.*?\]\(.*?\)', '', translated_markdown)
        text_only = _re.sub(r'[#*_\-|`>\[\](){}]', '', text_only)
        text_only = text_only.strip()
        meaningful_words = [w for w in text_only.split() if len(w) > 2 and not w.replace('.', '').replace(',', '').isdigit()]
        
        if len(meaningful_words) < 10:
            logger.info(f"Page {page_number}: Sparse content ({len(meaningful_words)} words), rendering as image")
            b64_img = bytes_to_base64(page_image_bytes)
            return f'<div class="image-page" style="text-align:center;padding:8px;"><img src="data:image/png;base64,{b64_img}" style="max-width:100%;height:auto;" alt="Page {page_number}"></div>'

        target_language = get_language_name(target_language_code)
        layout_summary = self._format_layout_summary(layout_details)

        if translation_mode == "monolingual":
            prompt = f"""You are an expert document layout specialist. Your output HTML will be rendered inside an A4-width container (max-width: 680px, padding: 12px 20px). Design your HTML accordingly.

TASK: Format the ALREADY-TRANSLATED {target_language} content below to match the layout of the attached original page image.

IMPORTANT: The text is ALREADY translated into {target_language}. DO NOT translate it again. Your job is ONLY to:
1. Organize the {target_language} content to match the original page layout (reading order, sections, columns, spacing).
2. Convert Markdown to clean HTML, keeping the text tightly coupled in the same structural blocks.
3. Preserve ALL image tags and convert them to HTML img tags.

CRITICAL — LAYOUT & CONTENT ORDERING:
1. Look at the attached ORIGINAL PAGE IMAGE carefully.
2. Output content in EXACTLY the same top-to-bottom reading order as the original image.
3. DO NOT reorder, skip, or move any content. If the original shows Question 31 before Question 32, your HTML must show them in that exact order.
4. If the original has a header/title bar at the top, output it FIRST.
5. TWO-COLUMN LAYOUTS: If the original image is divided into two distinct vertical columns, do NOT just flatten everything into a single long column. Instead, wrap the entire multi-column section in a `<div style="column-count: 2; column-gap: 40px; text-align: justify;">` to replicate the visual two-column flow.
6. Position each element (text, image, table) in the same relative position as the original. 

HANDLING IMAGES AND TABLES (CRITICAL MULTIMODAL RULE):
- The input text contains placeholder tags in this format: `![image](crop:[ymin, xmin, ymax, xmax])`
- Look at the attached ORIGINAL PAGE IMAGE to see exactly what is inside that cropped area.
- Rule 1 (CHARTS/GRAPHS): If the crop area contains a chart, graph, diagram, geometry figure, or picture, you MUST convert the tag to an HTML img tag:
  `<img src="crop:[ymin, xmin, ymax, xmax]" style="max-width:80%; height:auto; display:block; margin:10px auto;">`
- Rule 2 (TABLES): If the crop area contains a DATA TABLE with text/numbers, DO NOT render it as an `<img>`. Instead, output it as a properly styled HTML `<table>` using the translated content.
- Rule 3: For images, use the EXACT SAME crop coordinates — do NOT change the numbers in the src.
- Rule 4: NEVER drop, skip, or omit a crop tag. PRESERVE ALL CROP TAGS.
- Rule 5: Place images/tables in the EXACT same position relative to surrounding text.
- Rule 6: If you're unsure whether something is a table or image, default to `<img>`.

MATH AND FORMULAS (CRITICAL):
- Math expressions are already in LaTeX format wrapped in `$...$` or `$$...$$`
- Keep ALL math expressions EXACTLY as they appear
- Do NOT modify, unwrap, or translate anything inside `$...$` blocks
- INLINE MATH: If a math expression or percentage (like `$14\\frac{{2}}{{7}}\\%$` or `12.5%`) appears inside a sentence, keep it INLINE.

LAYOUT RULES:
1. Each QUESTION block must be wrapped in its own `<div>` with `margin-bottom: 12px; padding: 8px 0;`. Use ONLY margin and padding for spacing. ABSOLUTELY NO border-bottom, NO <hr>, NO horizontal lines, NO separators. 
2. Question number must be **bold**: `<b>31.</b>`. The question text should immediately follow within the same div.
3. **MCQ OPTIONS (VISUAL MATCHING & RESPONSIVE LAYOUT)**: Observe how options are arranged in the original image and match that grouping, BUT prioritize space efficiency.
   - If options are short (1-4 words each), ALWAYS put them in a single row using: `<div style="display: flex; flex-wrap: wrap; gap: 20px; margin-top: 6px;">`
   - If options are medium length, use a 2x2 grid: `<div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 6px;">`
   - ONLY use vertical stacking if the options are very long sentences.
4. If the original has a shaded/colored header bar, replicate with `background-color` and `padding`.
5. **TABLES (GRID LINES)**: Use `<table style="border-collapse:collapse; width:100%; margin:8px 0;">`. Look at the image: ONLY add a 1px solid border to `<td>` and `<th>` elements if visible grid lines exist in the original image.
6. Use inline CSS only. Font-size: 13px for body text, 15px for headings. Line-height: 1.5.
7. FORBIDDEN: No `<hr>`, no `border-bottom` on divs. Do NOT insert arbitrary `<br>` or new `<p>` blocks into the middle of a sentence. Let text wrap naturally.
8. SPACING: Keep spacing compact — match the density of the original page. Don't add excessive whitespace.
9. **IGNORE HEADERS/LOGOS**: Completely EXCLUDE any institute logos, header blocks, test center names, addresses, or branch lists at the very top or bottom of the original page.

OUTPUT: Raw HTML only. No ```html``` wrapper, no explanations.

EXTRACTED CONTENT:
---
{translated_markdown}
---

HTML:"""
        else:
            prompt = f"""You are an expert document layout specialist. Your output HTML will be rendered inside an A4-width container (max-width: 680px, padding: 12px 20px). Design your HTML accordingly.

TASK: Format the BILINGUAL ALREADY-TRANSLATED (English + {target_language}) content below to match the layout of the attached original page image.

IMPORTANT: The text is ALREADY translated and formatted bilingually. DO NOT translate it again, and DO NOT remove the English text. Your job is ONLY to:
1. Organize the BILINGUAL content to match the original page layout (reading order, sections, columns, spacing).
2. Convert Markdown to clean HTML, keeping the stacked bilingual text (English followed by {target_language}) tightly coupled in the same structural blocks.
3. Preserve ALL image tags and convert them to HTML img tags.

CRITICAL — LAYOUT & CONTENT ORDERING:
1. Look at the attached ORIGINAL PAGE IMAGE carefully.
2. Output content in EXACTLY the same top-to-bottom reading order as the original image.
3. DO NOT reorder, skip, or move any content. If the original shows Question 31 before Question 32, your HTML must show them in that exact order.
4. If the original has a header/title bar at the top, output it FIRST.
5. TWO-COLUMN LAYOUTS: If the original image is divided into two distinct vertical columns, do NOT just flatten everything into a single long column. Instead, wrap the entire multi-column section in a `<div style="column-count: 2; column-gap: 40px; text-align: justify;">` to replicate the visual two-column flow.
6. Position each element (text, image, table) in the same relative position as the original. Each bilingual pair (English + {target_language}) acts as a single logical block representing the original English block in the image.

DO NOT TRANSLATE or REMOVE: The content is already bilingual (English + {target_language}). Keep BOTH languages exactly as they are.

HANDLING IMAGES AND TABLES (CRITICAL MULTIMODAL RULE):
- The input text contains placeholder tags in this format: `![image](crop:[ymin, xmin, ymax, xmax])`
- Look at the attached ORIGINAL PAGE IMAGE to see exactly what is inside that cropped area.
- Rule 1 (CHARTS/GRAPHS): If the crop area contains a chart, graph, diagram, geometry figure, or picture, you MUST convert the tag to an HTML img tag:
  `<img src="crop:[ymin, xmin, ymax, xmax]" style="max-width:80%; height:auto; display:block; margin:10px auto;">`
  Use max-width:80% for large charts, max-width:50% for smaller diagrams, max-width:30% for icons/logos — match the proportion visible in the original.
- Rule 2 (TABLES): If the crop area contains a DATA TABLE with text/numbers, DO NOT render it as an `<img>`. Instead, READ the table structure (rows, columns, cell layout) from the original image at those coordinates, and output it as a properly styled HTML `<table>` using the already-translated bilingual content from the extracted markdown above. Do NOT re-translate or discard English — the text is already prepared.
- Rule 3: For images, use the EXACT SAME crop coordinates — do NOT change the numbers in the src.
- Rule 4: NEVER drop, skip, or omit a crop tag. It must either become an `<img>` (if it's a visual graph/figure) or a `<table>` (if it's a text table). PRESERVE ALL CROP TAGS.
- Rule 5: Place images/tables in the EXACT same position relative to surrounding text as shown in the original image.
- Rule 6: If you're unsure whether something is a table or image, default to `<img>` to preserve the visual content.

MATH AND FORMULAS (CRITICAL):
- Math expressions are already in LaTeX format wrapped in `$...$` or `$$...$$`
- Keep ALL math expressions EXACTLY as they appear
- Do NOT modify, unwrap, or translate anything inside `$...$` blocks
- INLINE MATH: If a math expression or percentage (like `$14\\frac{2}{7}\\%$` or `12.5%`) appears inside a sentence, keep it INLINE. Do NOT wrap it in a new `<div>`, `<p>`, or place it on a new line. It must flow naturally in the paragraph.

LAYOUT RULES:
1. Each QUESTION block must be wrapped in its own `<div>` with `margin-bottom: 12px; padding: 8px 0;`. Use ONLY margin and padding for spacing. ABSOLUTELY NO border-bottom, NO <hr>, NO horizontal lines, NO separators. 
2. Question number must be **bold**: `<b>31.</b>`. The question text (both English and {target_language} translation) should immediately follow within the same div. You can put a `<br>` between the English and Translated text if they belong together.
3. **MCQ OPTIONS (VISUAL MATCHING & RESPONSIVE LAYOUT)**: Observe how options are arranged in the original image and match that grouping, BUT prioritize space efficiency.
   - If options are short (1-4 words each), ALWAYS put them in a single row using: `<div style="display: flex; flex-wrap: wrap; gap: 20px; margin-top: 6px;">`
   - If options are medium length, use a 2x2 grid: `<div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 6px;">`
   - ONLY use vertical stacking (`<div style="display: flex; flex-direction: column; gap: 6px; margin-top: 6px;">`) if the options are very long sentences that span the entire page width.
   - NEVER blindly force options into a vertical stack just because they are bilingual. Use `flex-wrap` or `grid` to allow them to flow horizontally if space permits.
   - For EACH option, treat the English text and the {target_language} translation as a single unified block. Use `<br>` or `<div style="margin-top:2px;">` INSIDE the individual option div to stack the {target_language} text immediately beneath the English text. DO NOT DISCARD THE TRANSLATION.
   - Example markup for a single bilingual option: `<div><b>A)</b> English text<br><span style="color:#444;">{target_language} text</span></div>`
5. If the original has a shaded/colored header bar, replicate with `background-color` and `padding`.
6. **TABLES (GRID LINES)**: Use `<table style="border-collapse:collapse; width:100%; margin:8px 0;">`. Look at the image: ONLY add a 1px solid border to `<td>` and `<th>` elements if visible grid lines exist in the original image. If the image shows implicitly aligned columns of text without drawn lines, use `<td style="border:none; padding:6px 10px;">` to preserve the visual cleanliness.
7. Use inline CSS only. Font-size: 13px for body text, 15px for headings. Line-height: 1.5.
8. FORBIDDEN: No `<hr>`, no `border-bottom` on divs, no horizontal separators of any kind. Do NOT insert arbitrary `<br>` or new `<p>` blocks into the middle of a sentence. Let text wrap naturally. Keep words like '1st', '2nd', '3rd', '4th', etc., strictly INLINE within their sentences. Do not break a single sentence into multiple separate blocks.
9. SPACING: Keep spacing compact — match the density of the original page. Don't add excessive whitespace.
10. **IGNORE HEADERS/LOGOS**: Completely EXCLUDE any institute logos, header blocks, test center names, addresses, or branch lists at the very top or bottom of the original page. Do NOT wrap them in HTML and DO NOT convert their crop tags to images. Omit them entirely.

OUTPUT: Raw HTML only. No ```html``` wrapper, no explanations.

EXTRACTED CONTENT:
---
{translated_markdown}
---

HTML ({target_language}):"""

        try:
            logger.info(
                f"Reconstructing page {page_number} layout with Gemini (mode: {translation_mode})..."
            )

            # Prepare multimodal content: image + text
            image_part = types.Part.from_bytes(
                data=page_image_bytes,
                mime_type="image/png",
            )

            response = await call_gemini_with_timeout(
                self.client,
                self.model,
                [image_part, prompt],
                types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                ),
                timeout=180
            )

            html_content = response.text
            if not html_content:
                raise ReconstructionError(
                    f"Empty reconstruction response for page {page_number}"
                )

            # Clean up: remove wrapping code blocks
            html_content = html_content.strip()
            if html_content.startswith("```html"):
                html_content = html_content[len("```html"):].strip()
            if html_content.startswith("```"):
                html_content = html_content[3:].strip()
            if html_content.endswith("```"):
                html_content = html_content[:-3].strip()

            # ---- Debug: log whether crop tags survived reconstruction ----
            crop_debug_pattern = re.compile(r'crop:', re.IGNORECASE)
            md_img_pattern = re.compile(r'!\[.*?\]\(.*?crop:.*?\)', re.IGNORECASE)
            crop_hits_html = crop_debug_pattern.findall(html_content)
            md_img_hits = md_img_pattern.findall(html_content)
            
            # Count expected crop tags from input
            expected_crops = len(re.findall(r'crop:', translated_markdown, re.IGNORECASE))
            actual_crops = len(crop_hits_html) + len(md_img_hits)
            
            logger.info(
                f"Page {page_number}: Gemini output has {len(crop_hits_html)} crop refs, "
                f"{len(md_img_hits)} unconverted markdown image tags (expected: {expected_crops})"
            )
            
            # Recovery mechanism: if Gemini dropped crop tags, try to recover them
            if expected_crops > actual_crops:
                missing_count = expected_crops - actual_crops
                logger.warning(
                    f"Page {page_number}: {missing_count} crop tag(s) lost during reconstruction. "
                    f"Attempting recovery..."
                )
                # Extract all crop tags from original markdown
                original_crops = re.findall(
                    r'!\[([^\]]*)\]\((crop:\s*\[?[\d\s,]+\]?)\)',
                    translated_markdown,
                    re.IGNORECASE
                )
                # Find which ones are missing in HTML
                for alt_text, crop_coords in original_crops:
                    if crop_coords not in html_content:
                        logger.info(f"Page {page_number}: Recovering lost crop tag: {crop_coords}")
                        # Append at the end with a note
                        recovery_img = f'<div style="margin:10px 0;"><img src="{crop_coords}" style="max-width:80%; height:auto; display:block; margin:0 auto;" alt="{alt_text}"><p style="font-size:11px; color:#666; text-align:center;">Recovered image</p></div>'
                        html_content += recovery_img

            # Pre-process: convert any leftover markdown image syntax
            # ![image](crop:[ymin, xmin, ymax, xmax]) → <img src="crop:[ymin, xmin, ymax, xmax]" ...>
            # Gemini sometimes leaves these unconverted
            html_content = re.sub(
                r'!\[([^\]]*)\]\((crop:\s*\[?[\d\s,]+\]?)\)',
                r'<img src="\2" style="max-width:100%; height:auto; display:block; margin:10px auto;" alt="\1">',
                html_content
            )

            # Process any crop instructions — replace crop:coords with base64 data URIs
            # If YOLO figure detections are available, use their precise coordinates
            def process_crops(html: str, img_bytes: bytes, yolo_figures: list = None) -> str:
                from app.services.layout_detection_service import find_best_yolo_match

                # Enhanced regex: handles multiple coordinate formats
                # Matches: crop:[y,x,y,x], crop: [y,x,y,x], crop:y,x,y,x, [y,x,y,x]
                pattern = re.compile(
                    r'(?:crop:\s*(?:\[)?|(?<=src=["\'])\[)\s*'
                    r'(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*'
                    r'(?:\])?',
                    re.IGNORECASE
                )
                
                matches_found = pattern.findall(html)
                if not matches_found:
                    expected_crops = len(re.compile(r'crop:', re.IGNORECASE).findall(translated_markdown))
                    if expected_crops > 0:
                        logger.warning(f"Page {page_number}: No crop coordinates found in HTML despite {expected_crops} in input — images won't be embedded")
                    else:
                        logger.info(f"Page {page_number}: No crop coordinates requested for this page.")
                    return html
                
                logger.info(f"Page {page_number}: Found {len(matches_found)} crop regions to process: {matches_found}")
                
                try:
                    full_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    w, h = full_img.size
                    logger.info(f"Page {page_number}: Source image size {w}x{h}")
                except Exception as e:
                    logger.error(f"Failed to open image for cropping: {e}")
                    return html

                def replacer(match):
                    try:
                        ymin, xmin, ymax, xmax = map(int, match.groups())
                        glm_coords = [ymin, xmin, ymax, xmax]
                        
                        # Try to match with a YOLO detection for precise coordinates
                        # Use more lenient IoU threshold (0.2) for better matching
                        if yolo_figures:
                            yolo_match = find_best_yolo_match(glm_coords, yolo_figures, iou_threshold=0.2)
                            if yolo_match:
                                old_coords = [ymin, xmin, ymax, xmax]
                                ymin, xmin, ymax, xmax = yolo_match["bbox_normalized"]
                                logger.info(
                                    f"Page {page_number}: YOLO precision upgrade — "
                                    f"GLM [{old_coords}] → YOLO [{ymin},{xmin},{ymax},{xmax}] "
                                    f"(conf={yolo_match['confidence']:.2f})"
                                )
                            else:
                                logger.info(
                                    f"Page {page_number}: No YOLO match for crop [{ymin},{xmin},{ymax},{xmax}], "
                                    f"using GLM-OCR coordinates"
                                )
                        
                        logger.info(f"Page {page_number}: Cropping region [{ymin},{xmin},{ymax},{xmax}]")
                        
                        # Adaptive padding based on image size
                        # Larger images get more padding to avoid cutting edges
                        box_width = xmax - xmin
                        box_height = ymax - ymin
                        box_area = box_width * box_height
                        
                        # Base padding: 15 for small images, up to 25 for large images
                        if box_area < 50000:  # Small image
                            padding = 12
                        elif box_area < 200000:  # Medium image
                            padding = 18
                        else:  # Large image
                            padding = 25
                        
                        logger.info(f"Page {page_number}: Using adaptive padding={padding} for box area={box_area}")
                        
                        # Validate boxes and apply padding
                        ymin = max(0, min(1000, ymin - padding))
                        xmin = max(0, min(1000, xmin - padding))
                        ymax = max(0, min(1000, ymax + padding))
                        xmax = max(0, min(1000, xmax + padding))
                        
                        # Validate and fix inverted coordinates
                        if ymin >= ymax:
                            logger.warning(f"Page {page_number}: Invalid y coords ({ymin} >= {ymax}), swapping")
                            ymin, ymax = ymax, ymin
                        if xmin >= xmax:
                            logger.warning(f"Page {page_number}: Invalid x coords ({xmin} >= {xmax}), swapping")
                            xmin, xmax = xmax, xmin

                        real_ymin = int((ymin / 1000.0) * h)
                        real_xmin = int((xmin / 1000.0) * w)
                        real_ymax = int((ymax / 1000.0) * h)
                        real_xmax = int((xmax / 1000.0) * w)
                        
                        # Ensure minimum size (at least 20x20 pixels for visibility)
                        if (real_xmax - real_xmin) < 20 or (real_ymax - real_ymin) < 20:
                            logger.warning(
                                f"Page {page_number}: Crop region too small "
                                f"({real_xmax - real_xmin}x{real_ymax - real_ymin}), expanding to minimum size"
                            )
                            # Expand to minimum 30x30 pixels centered on original box
                            center_x = (real_xmin + real_xmax) // 2
                            center_y = (real_ymin + real_ymax) // 2
                            real_xmin = max(0, center_x - 15)
                            real_xmax = min(w, center_x + 15)
                            real_ymin = max(0, center_y - 15)
                            real_ymax = min(h, center_y + 15)
                        
                        # Ensure within image bounds
                        real_xmin = max(0, min(w - 1, real_xmin))
                        real_ymin = max(0, min(h - 1, real_ymin))
                        real_xmax = max(1, min(w, real_xmax))
                        real_ymax = max(1, min(h, real_ymax))
                        
                        # Final validation
                        if real_xmax <= real_xmin or real_ymax <= real_ymin:
                            logger.warning(f"Page {page_number}: Invalid crop box after scaling: ({real_xmin},{real_ymin})->({real_xmax},{real_ymax})")
                            return match.group(0)
                        
                        # Initial crop with error handling
                        try:
                            cropped = full_img.crop((real_xmin, real_ymin, real_xmax, real_ymax))
                            
                            # Validate cropped image before processing
                            if cropped.size[0] == 0 or cropped.size[1] == 0:
                                raise ValueError(f"Cropped image has zero size: {cropped.size}")
                            
                            # Smart boundary detection - trim excess whitespace
                            # Only apply if image is large enough (>100x100)
                            if settings.CROP_SMART_PADDING and cropped.size[0] > 100 and cropped.size[1] > 100:
                                cropped = self._smart_crop_trim(cropped, page_number)
                            
                            crop_bytes = io.BytesIO()
                            cropped.save(crop_bytes, format="PNG", optimize=True)
                            b64_crop = bytes_to_base64(crop_bytes.getvalue())
                            logger.info(
                                f"Page {page_number}: Successfully cropped region "
                                f"{cropped.size[0]}x{cropped.size[1]}px, base64 length: {len(b64_crop)}"
                            )
                            return f"data:image/png;base64,{b64_crop}"
                        except Exception as crop_error:
                            logger.error(
                                f"Page {page_number}: Crop failed for region [{ymin},{xmin},{ymax},{xmax}]: {crop_error}. "
                                f"Attempting fallback with expanded bounds."
                            )
                            # Fallback: try with extra padding
                            try:
                                fallback_padding = 50
                                fb_ymin = max(0, real_ymin - fallback_padding)
                                fb_xmin = max(0, real_xmin - fallback_padding)
                                fb_ymax = min(h, real_ymax + fallback_padding)
                                fb_xmax = min(w, real_xmax + fallback_padding)
                                cropped = full_img.crop((fb_xmin, fb_ymin, fb_xmax, fb_ymax))
                                crop_bytes = io.BytesIO()
                                cropped.save(crop_bytes, format="PNG", optimize=True)
                                b64_crop = bytes_to_base64(crop_bytes.getvalue())
                                logger.info(f"Page {page_number}: Fallback crop successful with expanded bounds")
                                return f"data:image/png;base64,{b64_crop}"
                            except Exception as fallback_error:
                                logger.error(f"Page {page_number}: Fallback crop also failed: {fallback_error}")
                                return match.group(0)
                        
                    except Exception as e:
                        logger.error(f"Error processing crop match: {e}")
                        return match.group(0)

                # Replace all crop directives with real base64 data
                new_html = pattern.sub(replacer, html)
                return new_html

            html_content = process_crops(html_content, page_image_bytes, figure_detections or [])

            # Post-process: hide broken/hallucinated image sources
            html_content = self._hide_broken_images(html_content)

            # Post-process: fix fractions (2/5 → MathJax)
            html_content = self._fix_fractions(html_content)

            # Post-process: fix superscripts and unit expressions
            html_content = self._fix_superscripts_and_units(html_content)

            # Post-process: remove unwanted lines/borders/hr between questions
            html_content = self._strip_unwanted_lines(html_content)

            # Wrap in a page container with styling
            wrapped_html = self._wrap_page_html(
                html_content, page_number, target_language_code
            )

            logger.info(
                f"Reconstruction complete for page {page_number}: "
                f"{len(wrapped_html)} chars"
            )
            return wrapped_html

        except ReconstructionError:
            raise
        except Exception as e:
            raise ReconstructionError(
                f"Reconstruction failed for page {page_number}: {e}"
            )

    def _fix_fractions(self, html: str) -> str:
        """
        Convert plain-text fractions to MathJax notation.
        Math-block-aware: only processes text outside $...$ blocks.
        HTML-tag-aware: skips content inside HTML tags to protect attributes.
        MCQ-safe: won't mangle option patterns like '1) 14' or '2) 16'.

        Examples:
          '2/5'     → '$\\frac{2}{5}$'
          '10 1/2'  → '$10\\frac{1}{2}$'
          '33 1/3'  → '$33\\frac{1}{3}$'
        """
        import re

        # Split into math and non-math segments
        math_pattern = re.compile(r'(\$\$[^\$]+?\$\$|\$[^\$]+?\$)')
        segments = math_pattern.split(html)

        # Regex to isolate HTML tags from plain text
        tag_splitter = re.compile(r'(<[^>]+>)')

        processed = []
        for segment in segments:
            if segment.startswith('$'):
                # MathJax block — leave untouched
                processed.append(segment)
            else:
                # Split into HTML tag pieces vs plain-text pieces
                parts = tag_splitter.split(segment)
                fixed_parts = []
                for part in parts:
                    if part.startswith('<'):
                        # HTML tag — never modify
                        fixed_parts.append(part)
                    else:
                        # Plain text — fix fractions carefully
                        # Mixed fractions: "10 1/2" → "$10\frac{1}{2}$"
                        # Guard: NOT preceded by ')' (MCQ option numbers like "1) 14")
                        part = re.sub(
                            r'(?<!\))\b(\d+)\s+(\d+)/(\d+)\b',
                            r'$\1\\frac{\2}{\3}$',
                            part
                        )
                        # Simple fractions: "2/5" → "$\frac{2}{5}$"
                        # Guards: not after ')', not dates (03/2026)
                        part = re.sub(
                            r'(?<!\))(?<!\d)(?<!/)(\d{1,2})/(\d{1,2})(?!\d|/)',
                            r'$\\frac{\1}{\2}$',
                            part
                        )
                        fixed_parts.append(part)
                processed.append(''.join(fixed_parts))

        return ''.join(processed)

    def _hide_broken_images(self, html: str) -> str:
        """Replace bad src attributes (hallucinations or failed crops) with a transparent 1x1 pixel to avoid broken icons."""
        import re
        empty_pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        # Fix double quotes src
        html = re.sub(
            r'(<img\s+[^>]*src=")(?!data:image)([^"]+)("[^>]*>)',
            rf'\g<1>{empty_pixel}\g<3>',
            html,
            flags=re.IGNORECASE
        )
        # Fix single quotes src
        html = re.sub(
            r"(<img\s+[^>]*src=')(?!data:image)([^']+)('[^>]*>)",
            rf"\g<1>{empty_pixel}\g<3>",
            html,
            flags=re.IGNORECASE
        )
        return html

    def _fix_superscripts_and_units(self, html: str) -> str:
        """
        Post-process HTML to fix common superscript/unit patterns.
        
        IMPORTANT: This function is math-block-aware. It splits the HTML into
        MathJax segments ($...$, $$...$$) and non-math segments, then ONLY
        applies superscript conversions to non-math text. MathJax blocks are
        left completely untouched.
        """
        import re

        # Step 1: Split HTML into math blocks and non-math segments
        # Matches $$...$$ (display) and $...$ (inline), preserving them
        math_pattern = re.compile(r'(\$\$[^\$]+?\$\$|\$[^\$]+?\$)')
        segments = math_pattern.split(html)

        # Regex to isolate HTML tags from plain text
        tag_splitter = re.compile(r'(<[^>]+>)')

        # Step 2: Process ONLY non-math segments
        processed = []
        for segment in segments:
            if segment.startswith('$'):
                # This is a MathJax block — trim inner whitespace for reliable rendering
                if segment.startswith('$$'):
                    inner = segment[2:-2].strip()
                    segment = '$$' + inner + '$$'
                else:
                    inner = segment[1:-1].strip()
                    segment = '$' + inner + '$'
                processed.append(segment)
            else:
                # Split into HTML tag pieces vs plain-text pieces
                parts = tag_splitter.split(segment)
                fixed_parts = []
                for part in parts:
                    if part.startswith('<'):
                        # HTML tag — never modify
                        fixed_parts.append(part)
                    else:
                        # Non-math plain text — apply superscript fixes here
                        part = self._apply_superscript_fixes(part)
                        fixed_parts.append(part)
                processed.append(''.join(fixed_parts))

        return ''.join(processed)

    def _apply_superscript_fixes(self, text: str) -> str:
        """Apply unit and caret superscript fixes to non-math text only.
        
        Handles multiple scenarios:
        - Unicode ² ³ ¹ characters
        - Caret notation: cm^2, m^3
        - Bare unit+digit: cm2, m3, km2 (no caret)
        - Non-English units: సెం.మీ^2, సెం.మీ.2
        - Gemini using <sub> instead of <sup> for exponents
        """
        import re

        # Unicode superscript characters → HTML <sup>
        unicode_map = {
            '²': '<sup>2</sup>',
            '³': '<sup>3</sup>',
            '¹': '<sup>1</sup>',
        }
        for char, replacement in unicode_map.items():
            text = text.replace(char, replacement)

        # Fix Gemini using <sub> instead of <sup> for numeric exponents
        # <sub>2</sub> or <sub>3</sub> after unit-like text → <sup>
        text = re.sub(
            r'(?:cm|km|m|mm|ft|in|yd|mi)\s*<sub>(\d+)</sub>',
            lambda m: m.group(0).replace('<sub>', '<sup>').replace('</sub>', '</sup>'),
            text,
            flags=re.IGNORECASE,
        )

        # Caret notation for common units: cm^2, m^3, km^2, etc.
        text = re.sub(r'(\b(?:cm|km|m|mm|ft|in|yd|mi|sq)\s*)\^(\d+)', r'\1<sup>\2</sup>', text, flags=re.IGNORECASE)

        # Bare unit+digit WITHOUT caret: "cm2", "m3", "km2" → "cm<sup>2</sup>"
        # Only match 2 or 3 (square/cube) to avoid false positives
        text = re.sub(
            r'\b(cm|km|mm|ft|yd|mi)([23])\b',
            r'\1<sup>\2</sup>',
            text,
            flags=re.IGNORECASE,
        )
        # Special case: "m2" or "m3" — only after a digit+space to avoid matching words like "m2p"
        text = re.sub(r'(\d\s*m)([23])\b', r'\1<sup>\2</sup>', text)

        # General standalone caret notation: 14^2, x^3, etc (but NOT inside HTML tags)
        text = re.sub(r'(?<![\<\w/])(\d+)\^(\d+)(?![^<]*>)', r'\1<sup>\2</sup>', text)

        # Non-English/translated text followed by ^2 or ^3 (e.g. సెం.మీ^2, सेमी^2)
        text = re.sub(r'\^([23])\b', r'<sup>\1</sup>', text)

        # "sq cm" / "sq m" → cm²/m² style
        text = re.sub(r'\bsq\.?\s*cm\b', 'cm<sup>2</sup>', text, flags=re.IGNORECASE)
        text = re.sub(r'\bsq\.?\s*m\b', 'm<sup>2</sup>', text, flags=re.IGNORECASE)

        # Catch trailing plain digit after any text ending with a period or dot
        # Common in Telugu: "సెం.మీ.2" → "సెం.మీ.<sup>2</sup>"  
        # Pattern: non-digit char followed by a lone 2 or 3 at word boundary,
        # preceded by a dot (typical of abbreviations in Indian languages)
        text = re.sub(r'(\.)([23])(?=\s|<|$|,)', r'\1<sup>\2</sup>', text)

        return text

    def _strip_unwanted_lines(self, html: str) -> str:
        """
        Remove unwanted borders, lines, and hr tags from reconstructed HTML.
        
        Gemini sometimes adds border-bottom or <hr> between questions despite
        explicit instructions not to. This post-processing step strips them.
        """
        # Remove border-bottom from inline styles on divs
        html = re.sub(r'border-bottom\s*:\s*[^;"]*;?', '', html)
        
        # Remove <hr> tags entirely (self-closing and regular)
        html = re.sub(r'<hr\s*/?\s*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<hr\s+[^>]*/?\s*>', '', html, flags=re.IGNORECASE)
        
        # Remove border-top from inline styles (another line variant)
        # But only outside of table contexts — we want table borders
        # Only strip if it looks like a question separator (1px solid #eee, #ddd, #ccc, etc.)
        html = re.sub(
            r'border-top\s*:\s*1px\s+solid\s+#[cde][cde][cde]\s*;?',
            '',
            html,
            flags=re.IGNORECASE
        )
        
        return html

    def _format_layout_summary(self, layout_details: list) -> str:
        """Format layout details into a readable summary for the prompt."""
        if not layout_details:
            return "No layout details available."

        lines = []
        for i, element in enumerate(layout_details):
            if isinstance(element, dict):
                label = element.get("label", "unknown")
                bbox = element.get("bbox_2d", [])
                content_preview = (element.get("content", "") or "")[:100]
                lines.append(
                    f"  Element {i + 1}: type={label}, "
                    f"position={bbox}, "
                    f"content_preview=\"{content_preview}...\""
                )

        return "\n".join(lines) if lines else "No layout details available."

    def _smart_crop_trim(self, img: Image.Image, page_number: int) -> Image.Image:
        """Intelligently trim excess whitespace from cropped image while preserving content."""
        try:
            import numpy as np
            
            # Convert to numpy array
            img_array = np.array(img.convert('RGB'))
            h, w = img_array.shape[:2]
            
            # Calculate brightness for each pixel (grayscale)
            gray = np.mean(img_array, axis=2)
            
            # Detect non-white regions (threshold at 240 - less aggressive)
            # Higher threshold = more conservative trimming (preserves more border)
            threshold = 240
            non_white = gray < threshold
            
            # Find bounding box of non-white content
            rows = np.any(non_white, axis=1)
            cols = np.any(non_white, axis=0)
            
            if not rows.any() or not cols.any():
                # Image is all white, return original
                logger.info(f"Page {page_number}: Image is all white, keeping original crop")
                return img
            
            row_min, row_max = np.where(rows)[0][[0, -1]]
            col_min, col_max = np.where(cols)[0][[0, -1]]
            
            # Add margin (8 pixels) to avoid cutting too close
            margin = 8
            row_min = max(0, row_min - margin)
            col_min = max(0, col_min - margin)
            row_max = min(h - 1, row_max + margin)
            col_max = min(w - 1, col_max + margin)
            
            # Calculate how much we're trimming
            trim_percent = 100 * (1 - ((row_max - row_min) * (col_max - col_min)) / (h * w))
            
            # Only trim if we're removing significant whitespace (>15%)
            # More conservative threshold to avoid over-trimming
            if trim_percent > 15:
                trimmed = img.crop((col_min, row_min, col_max + 1, row_max + 1))
                logger.info(f"Page {page_number}: Smart trim removed {trim_percent:.1f}% whitespace")
                return trimmed
            else:
                logger.info(f"Page {page_number}: Minimal whitespace ({trim_percent:.1f}%), keeping original")
                return img
                
        except Exception as e:
            logger.warning(f"Page {page_number}: Smart trim failed: {e}, using original crop")
            return img

    def _wrap_page_html(
        self, html_content: str, page_number: int, lang_code: str
    ) -> str:
        """Wrap page HTML with proper container and base styling.

        Styling is designed to match A4 proportions:
        - A4 content width ≈ 680px (210mm - 30mm margins at 96 DPI)
        - Font sizes match the reconstruction prompt (13px body, 15px headings)
        - Removed page-break controls to allow continuous flowing content across pages
        """
        # Determine text direction
        direction = "rtl" if lang_code == "ur" else "ltr"

        # Language-specific font stack mapping to the Google Fonts added in the frontend
        font_families = {
            "te": "'Gautami', 'Noto Sans Telugu', sans-serif",
            "hi": "'Noto Sans Devanagari', 'Mangal', sans-serif",
            "ta": "'Noto Sans Tamil', 'Latha', sans-serif",
            "kn": "'Noto Sans Kannada', 'Tunga', sans-serif",
            "ml": "'Noto Sans Malayalam', 'Kartika', sans-serif",
            "mr": "'Noto Sans Devanagari', 'Noto Sans Marathi', 'Mangal', sans-serif",
            "bn": "'Noto Sans Bengali', 'Vrinda', sans-serif",
            "gu": "'Noto Sans Gujarati', 'Shruti', sans-serif",
            "pa": "'Noto Sans Gurmukhi', 'Raavi', sans-serif",
            "or": "'Noto Sans Oriya', 'Kalinga', sans-serif",
            "ur": "'Noto Nastaliq Urdu', 'Urdu Typesetting', sans-serif",
        }

        font_family = font_families.get(lang_code, "sans-serif")

        return f"""<div class="translated-page" data-page="{page_number}" dir="{direction}" style="
    font-family: {font_family};
    font-size: 13px;
    padding: 12px 20px;
    line-height: 1.5;
    color: #1a1a1a;
    max-width: 680px;
    margin: 0 auto;
    overflow-wrap: break-word;
    word-wrap: break-word;
">
<style>
    .translated-page table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
    .translated-page td, .translated-page th {{ border: 1px solid #bbb; padding: 6px 10px; text-align: left; vertical-align: top; font-size: 13px; }}
    .translated-page th {{ background-color: #f0f0f0; font-weight: 600; }}
    .translated-page img {{ max-width: 100%; height: auto; display: block; margin: 8px auto; }}
    .translated-page hr {{ display: none !important; }}
    .translated-page h1, .translated-page h2, .translated-page h3 {{ margin: 8px 0 4px 0; font-size: 15px; }}
    .translated-page h1 {{ font-size: 17px; }}
    .translated-page p {{ margin: 3px 0; }}
    .translated-page ul, .translated-page ol {{ margin: 3px 0; padding-left: 24px; }}
    .translated-page > div {{ border-bottom: none !important; }}
</style>
{html_content}
</div>"""
