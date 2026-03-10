"""Translation service using Google Gemini."""

import asyncio
import logging
import json
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings
from app.core.exceptions import TranslationError
from app.models.enums import get_language_name

logger = logging.getLogger(__name__)

# Language-specific formal style guidance for government exam papers
LANGUAGE_STYLE_NOTES = {
    "Telugu": "Use classical formal Telugu (గ్రాంథిక భాష) as used in Andhra Pradesh/Telangana government exam papers. Prefer క్రింది over కింది, క్రొత్త over కొత్త, గ్రహించు over అర్థం చేసుకో, నిర్వహించు over చేయి, ప్రారంభించు over మొదలుపెట్టు.",
    "Odia": "Use formal written Odia (ଶିଷ୍ଟ ଭାଷା) with ତତ୍ସମ Sanskrit-origin words as used in Odisha PSC/government exam papers. Prefer ନିମ୍ନରେ over ତଳେ, ନୂତନ over ନୂଆ, ଅବଗତ ହୁଅ over ବୁଝ, ସମ୍ପାଦନ କର over କର, ପ୍ରଦର୍ଶନ over ଦେଖାଅ.",
    "Hindi": "Use formal Shuddh Hindi with Sanskrit-origin (तत्सम) vocabulary as used in UPSC/SSC government exam papers. Prefer निम्नलिखित over नीचे दिया, उपर्युक्त over ऊपर दिया, संलग्न over साथ में, अभ्यर्थी over उम्मीदवार.",
    "Kannada": "Use formal written Kannada (ಶಿಷ್ಟ ಭಾಷೆ) as used in Karnataka PSC/government exam papers. Prefer ಕೆಳಗಿನ over ಕೆಳಗೆ, ನೂತನ over ಹೊಸ, ನಿರ್ವಹಿಸು over ಮಾಡು, ಪ್ರಾರಂಭಿಸು over ಶುರು ಮಾಡು.",
    "Tamil": "Use formal written Tamil (செந்தமிழ்) as used in TNPSC/government exam papers. Prefer கீழ்க்காண்பவை over கீழே உள்ளது, புதிய over புது, நிர்வகி over செய், தொடங்கு over ஆரம்பி.",
    "Malayalam": "Use formal written Malayalam (ഗ്രന്ഥഭാഷ) as used in Kerala PSC/government exam papers. Prefer താഴെ പറയുന്നവ over താഴെ ഉള്ളത്, നൂതന over പുതിയ, നിർവഹിക്കുക over ചെയ്യുക.",
    "Bengali": "Use formal written Bengali (সাধু ভাষা) as used in WBPSC/government exam papers. Prefer নিম্নলিখিত over নিচের, নূতন over নতুন, সম্পাদন করুন over করুন, অবগত হন over বুঝুন.",
    "Marathi": "Use formal written Marathi as used in MPSC/Maharashtra government exam papers. Prefer खालीलपैकी over खाली, नवीन over नव, कार्यान्वित करा over करा.",
    "Gujarati": "Use formal written Gujarati as used in GPSC/Gujarat government exam papers. Prefer નીચે મુજબ over નીચે, નવીન over નવું, સંચાલન કરો over કરો.",
    "Punjabi": "Use formal written Punjabi (ਸਾਹਿਤਕ ਭਾਸ਼ਾ) as used in PPSC/Punjab government exam papers. Prefer ਹੇਠਾਂ ਦਿੱਤੇ over ਹੇਠਾਂ, ਨਵੀਨ over ਨਵਾਂ, ਸੰਚਾਲਨ ਕਰੋ over ਕਰੋ.",
}


async def call_gemini_with_timeout(client, model, contents, config, timeout=240):
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
        raise TranslationError(f"Gemini API call timed out after {timeout} seconds")


class TranslationService:
    """Translates extracted Markdown content using Google Gemini."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_MODEL

    def _pre_process_fragments(self, text: str) -> str:
        """Heuristically merge obvious OCR sentence fragments before sending to Gemini."""
        import re
        
        # 1. Merge split ordinals (e.g., "1 \n st" -> "1st")
        text = re.sub(r'\b(\d+)\s*\n+\s*(st|nd|rd|th)\b', r'\1\2', text, flags=re.IGNORECASE)
        
        # 2. Condense multiple blank lines to make processing easier
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        lines = text.split('\n')
        merged_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # If empty, keep it (might be discarded if we merge across it later)
            if not stripped:
                merged_lines.append(line)
                continue
                
            if merged_lines:
                # Find the last non-empty line
                last_text_idx = -1
                for i in range(len(merged_lines)-1, -1, -1):
                    if merged_lines[i].strip():
                        last_text_idx = i
                        break
                        
                if last_text_idx != -1:
                    prev_line = merged_lines[last_text_idx]
                    prev_stripped = prev_line.strip()
                    
                    # Don't merge if previous line was a table row, header, or ends with terminal punctuation
                    if not prev_stripped.startswith('|') and not prev_stripped.startswith('#') and not re.search(r'[.!?:]\s*$', prev_stripped):
                        
                        is_short_fragment = bool(
                            len(stripped) <= 25 
                            and re.match(r'^([a-z]+|\d+\^?\{?(st|nd|rd|th)\}?|[\d\.\%\+\-\*\/\^\(\)\{\}\\\$]+)$', stripped, re.IGNORECASE)
                        )
                        
                        starts_lowercase = bool(
                            re.match(r'^[a-z]', stripped) 
                            and not re.match(r'^[a-d]\)', stripped, re.IGNORECASE)
                            and not re.match(r'^[ivx]+\.', stripped, re.IGNORECASE)
                        )
                        
                        # Added 'of' to the list of words that often precede inline math
                        prev_ends_incomplete = bool(re.search(r'\b(the|and|or|of|in|to|is|are|a|an|if|for|with|by|from)\s*$', prev_stripped, re.IGNORECASE))
                        
                        if is_short_fragment or starts_lowercase or prev_ends_incomplete:
                            # Merge with the last non-empty line
                            merged_lines[last_text_idx] = merged_lines[last_text_idx].rstrip() + " " + stripped
                            
                            # Remove any blank lines that were between them
                            if last_text_idx < len(merged_lines) - 1:
                                merged_lines = merged_lines[:last_text_idx + 1]
                            continue
            
            merged_lines.append(line)
            
        return '\n'.join(merged_lines)

    async def translate_markdown(
        self,
        markdown_content: str,
        target_language_code: str,
        page_number: int = 1,
    ) -> str:
        """
        Translate Markdown content from English to target Indian language.
        
        Args:
            markdown_content: Extracted Markdown from GLM-OCR
            target_language_code: Language code (e.g., 'te', 'hi')
            page_number: Page number for logging
        
        Returns:
            Translated Markdown string
        """
        if not markdown_content or not markdown_content.strip():
            return ""

        markdown_content = self._pre_process_fragments(markdown_content)

        target_language = get_language_name(target_language_code)

        language_style_note = LANGUAGE_STYLE_NOTES.get(
            target_language,
            f"Use formal written {target_language} as used in government competitive exam papers. Prefer Sanskrit-origin/tatsama vocabulary over colloquial forms."
        )

        prompt = f"""You are an expert translator specializing in translating English educational/exam documents to {target_language}.

TASK: Translate the following extracted Markdown content from English to {target_language}.
However, instead of just returning the translation, you must generate a BILINGUAL document. 
For every text block (question, direction, option), output the CORRECTED English text (repairing any remaining OCR line breaks or fragments) followed immediately by its {target_language} translation on a new line.

TRANSLATION STYLE:
- Generate {target_language} in FORMAL COMPETITIVE EXAMINATION style used in SSC/Banking/State PSC exams.
- Use standard written {target_language}. Avoid conversational or spoken tone.
- {language_style_note}
- Avoid literal word-by-word translation. Use structured exam phrasing that sounds natural in {target_language}.
- Technical terms commonly used in exams (like "compound interest", "ratio", "percentage") should use the standard {target_language} equivalents used in government exam papers.

CRITICAL RULES:
1. Translate ALL human-readable text to {target_language} — sentences, instructions, directions, question text. Remember to keep the English version and append the {target_language} version right below it.
2. **MERGE FRAGMENTED SENTENCES (CRITICAL)**: The input OCR text is sometimes fragmented (e.g., "i. If the \\n 1st \\n and \\n 2nd \\n digits..."). You MUST reconstruct and merge these fragments into proper, continuous English sentences BEFORE translating. Output the MERGED, repaired English sentence followed by its translation. Do NOT output fragmented English pieces line-by-line.
3. **INLINE MATH MUST STAY INLINE**: NEVER isolate inline math, positions (e.g., `16^{{th}}`), or numbers on new lines. They MUST be embedded continuously inside the sentence, both in the English version and the {target_language} version. If a sentence has a number in the middle, DO NOT break the sentence.
4. **IGNORE HEADERS/LOGOS**: Completely EXCLUDE any institute names (e.g., 'Sreedhar\\'s CCE'), logos, contact details, phone numbers, or branch addresses at the top or bottom of the page. Do NOT translate or include them in your output. Start directly with the test name, directions, or exam content.
5. PRESERVE all Markdown formatting exactly (headers, bold, italic, lists, links, table syntax).
5. **TABLE TRANSLATION**: Tables are critical — follow these rules strictly:
   - PRESERVE the Markdown table pipe syntax EXACTLY: `| header1 | header2 |`, `|---|---|`, `| data1 | data2 |`.
   - Create BILINGUAL cells inside the table by putting the English text and the {target_language} text in the same cell separated by `<br>`.
   - Keep numbers, dates, and abbreviations inside cells unchanged.
   - DO NOT break the table structure — each row must have the same number of `|` pipes.
   - Example: `| Year | Students |` → `| Year<br>సంవత్సరం | Students<br>విద్యార్థులు |` (for Telugu)
5. **PRESERVE IMAGE TAGS**: Keep ALL image references in the format `![image](crop:[ymin, xmin, ymax, xmax])` EXACTLY as they appear. Do NOT modify, translate, or remove these tags. They are critical for image embedding.
6. DO NOT translate mathematical symbols, formulas, numbers, dates, measurements, and proper nouns (SBI, RBI, LIC etc.).
7. **MCQ OPTIONS (MULTIPLE CHOICE QUESTIONS)**: For options like `A) Option text` or `1) Option text`, you MUST output BOTH the English version and the {target_language} version. Keep the option label (`A)`, `1)`, etc.) unchanged but attach the translation to it.
   - Example: 
     `A) Rangbang`
     `A) รังบัง` (translation in the target language)
8. **FIX MATH FRACTIONS**: OCR sometimes badly extracts visual fractions as `33^1 \\underline{{3}}` or `33^1_3`. Fix these into proper LaTeX: `$33\\frac{{1}}{{3}}$`.
8. **MATH EXPRESSIONS**: Wrap ALL mathematical expressions, equations, and formulas in LaTeX `$...$`. Examples:
   - `? × 65 ÷ 72 = 195 × 352 ÷ 192` → `$? \\times 65 \\div 72 = 195 \\times 352 \\div 192$`
   - `√256 × ³√1728 = ? × ⁴√4096` → `$\\sqrt{{256}} \\times \\sqrt[3]{{1728}} = ? \\times \\sqrt[4]{{4096}}$`
   - `35% of 180 + 18² = (27)^(5/3) + ?²` → `$35\\% \\text{{ of }} 180 + 18^2 = (27)^{{5/3}} + ?^2$`
9. **HYBRID MATH / ENGLISH OPERATORS**: If a mathematical equation contains English connecting words like 'of' (e.g., `35% of 180` or `?% of 135`), DO NOT translate the word 'of' into {target_language}. Treat the entire string as a rigid math formula and wrap it in MathJax: `$35\\% \\text{{ of }} 180$`.
10. **LITERAL DOLLAR SIGNS**: If you see a literal dollar sign `$` representing money or used in a sequence of symbols (like `3 € $ 1 6 8`), you MUST escape it as `\\$` (e.g., `3 € \\$ 1 6 8`) so it isn't confused with a math block.
12. PRESERVE the exact order, structure, and spacing of content. Stack the BILINGUAL content as `English Version \n {target_language} Version`. Do not mix them in the same line unless it is inside a table cell.
13. Keep question numbers (Q1, Q2, 31., 32., etc.) unchanged. Keep one question number for both the English and the target language translation (e.g., `31. ` before the English text, and no number before the translated text).
14. Output ONLY the BILINGUAL Markdown — no explanations, no wrapping!

MARKDOWN CONTENT TO TRANSLATE:
---
{markdown_content}
---

TRANSLATED CONTENT IN {target_language}:"""

        try:
            logger.info(
                f"Translating page {page_number} to {target_language} "
                f"({len(markdown_content)} chars)..."
            )

            response = await call_gemini_with_timeout(
                self.client,
                self.model,
                prompt,
                types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                ),
                timeout=240
            )

            translated = response.text
            if not translated:
                raise TranslationError(
                    f"Empty translation response for page {page_number}"
                )

            # Clean up: remove any wrapping ```markdown blocks the model might add
            translated = translated.strip()
            if translated.startswith("```markdown"):
                translated = translated[len("```markdown"):].strip()
            if translated.startswith("```"):
                translated = translated[3:].strip()
            if translated.endswith("```"):
                translated = translated[:-3].strip()

            logger.info(
                f"Translation complete for page {page_number}: "
                f"{len(translated)} chars"
            )
            return translated

        except TranslationError:
            raise
        except Exception as e:
            raise TranslationError(
                f"Translation failed for page {page_number}: {e}"
            )
