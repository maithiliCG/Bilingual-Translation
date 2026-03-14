"""Shared Gemini API utilities used by translation and reconstruction services."""

import asyncio
import logging
import re

logger = logging.getLogger(__name__)


async def call_gemini_with_timeout(client, model, contents, config, timeout=240):
    """Call Gemini API with timeout protection.

    Args:
        client: Google GenAI client instance
        model: Model name string
        contents: Prompt contents (text or multimodal)
        config: GenerateContentConfig
        timeout: Seconds before raising TimeoutError (default 240)

    Returns:
        Gemini API response object

    Raises:
        TimeoutError: If the API call doesn't complete within timeout
    """
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
        raise TimeoutError(f"Gemini API call timed out after {timeout} seconds")


def strip_unwanted_lines(html: str) -> str:
    """Remove unwanted borders, lines, and hr tags from reconstructed HTML.

    Gemini sometimes adds border-bottom or <hr> between questions despite
    explicit instructions not to. This post-processing step strips them.

    Shared between ReconstructionService and DownloadService.
    """
    # Remove border-bottom from inline styles on divs
    html = re.sub(r'border-bottom\s*:\s*[^;"]*;?', '', html)

    # Remove <hr> tags entirely (self-closing and regular)
    html = re.sub(r'<hr\s*/?\s*>', '', html, flags=re.IGNORECASE)
    html = re.sub(r'<hr\s+[^>]*/?\s*>', '', html, flags=re.IGNORECASE)

    # Remove border-top from inline styles (another line variant)
    # Only strip if it looks like a question separator (1px solid #eee, #ddd, #ccc, etc.)
    html = re.sub(
        r'border-top\s*:\s*1px\s+solid\s+#[cde][cde][cde]\s*;?',
        '',
        html,
        flags=re.IGNORECASE
    )

    return html


def remove_table_image_duplicates(markdown_content: str) -> str:
    """Remove image tags that appear immediately before markdown tables.

    The OCR sometimes creates both an image tag AND a text table
    for the same table content. We keep the text table and remove the image.

    Shared between GLMOCRService and GLMOCRLocalService.
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
