"""Translation service using Google Gemini."""

import asyncio
import logging
import json
import re
from typing import Optional

from google import genai
from google.genai import types

from app.config import settings
from app.core.exceptions import TranslationError
from app.models.enums import get_language_name
from app.utils.gemini_utils import call_gemini_with_timeout

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

# Unicode ranges for each Indic script — used for post-processing validation
SCRIPT_UNICODE_RANGES = {
    "Telugu":     (0x0C00, 0x0C7F),
    "Tamil":      (0x0B80, 0x0BFF),
    "Kannada":    (0x0C80, 0x0CFF),
    "Malayalam":  (0x0D00, 0x0D7F),
    "Devanagari": (0x0900, 0x097F),   # Hindi, Marathi
    "Bengali":    (0x0980, 0x09FF),
    "Gujarati":   (0x0A80, 0x0AFF),
    "Gurmukhi":   (0x0A00, 0x0A7F),   # Punjabi
    "Oriya":      (0x0B00, 0x0B7F),   # Odia
    "Arabic":     (0x0600, 0x06FF),   # Urdu
}

# Maps a target language to the script name it uses
LANGUAGE_TO_SCRIPT = {
    "Telugu": "Telugu",
    "Tamil": "Tamil",
    "Kannada": "Kannada",
    "Malayalam": "Malayalam",
    "Hindi": "Devanagari",
    "Marathi": "Devanagari",
    "Bengali": "Bengali",
    "Gujarati": "Gujarati",
    "Punjabi": "Gurmukhi",
    "Odia": "Oriya",
    "Urdu": "Arabic",
}

# Explicit negative constraints to prevent cross-language script leakage
LANGUAGE_PURITY_RULES = {
    "Telugu": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Telugu script (తెలుగు లిపి). "
        "ABSOLUTELY FORBIDDEN scripts — if you write even ONE character from these, the translation is REJECTED: "
        "Tamil (தமிழ்), Kannada (ಕನ್ನಡ), Malayalam (മലയാളം). "
        "Common hallucination mistakes you MUST avoid: "
        "WRONG Tamil words: கூட்டல் (koodal), கழித்தல் (kazhithal), பெருக்கல் (perukkal), வகுத்தல் (vaguthal). "
        "CORRECT Telugu words: కూడిక (koodika), తీసివేత (teesiveta), గుణకారం (gunakaram), భాగహారం (bhagaharam). "
        "Every word of your translation must be readable by a Telugu speaker with NO Tamil/Kannada/Malayalam characters."
    ),
    "Tamil": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Tamil script (தமிழ் எழுத்து). "
        "ABSOLUTELY FORBIDDEN: Telugu (తెలుగు), Kannada (ಕನ್ನಡ), Malayalam (മലയാളം) characters."
    ),
    "Kannada": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Kannada script (ಕನ್ನಡ ಲಿಪಿ). "
        "ABSOLUTELY FORBIDDEN: Telugu (తెలుగు), Tamil (தமிழ்), Malayalam (മലയാളം) characters."
    ),
    "Malayalam": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Malayalam script (മലയാളം ലിപി). "
        "ABSOLUTELY FORBIDDEN: Telugu (తెలుగు), Tamil (தமிழ்), Kannada (ಕನ್ನಡ) characters."
    ),
    "Hindi": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Devanagari script (देवनागरी लिपि). "
        "ABSOLUTELY FORBIDDEN: Telugu, Tamil, Kannada, Malayalam, Bengali, Gujarati characters."
    ),
    "Bengali": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Bengali script (বাংলা লিপি). "
        "ABSOLUTELY FORBIDDEN: Devanagari (हिन्दी), Oriya, Telugu, Tamil characters."
    ),
    "Odia": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Odia script (ଓଡ଼ିଆ ଲିପି). "
        "ABSOLUTELY FORBIDDEN: Bengali (বাংলা), Devanagari (हिन्दी), Telugu, Tamil characters."
    ),
    "Marathi": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Devanagari script (देवनागरी लिपि) with Marathi vocabulary. "
        "ABSOLUTELY FORBIDDEN: Telugu, Tamil, Kannada, Malayalam, Bengali, Gujarati characters. "
        "Use Marathi-specific vocabulary — do NOT substitute Hindi words. Example: use 'करणे' (Marathi) not 'करना' (Hindi)."
    ),
    "Gujarati": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Gujarati script (ગુજરાતી લિપિ). "
        "ABSOLUTELY FORBIDDEN: Devanagari (हिन्दी), Telugu, Tamil, Bengali characters."
    ),
    "Punjabi": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Gurmukhi script (ਗੁਰਮੁਖੀ ਲਿਪੀ). "
        "ABSOLUTELY FORBIDDEN: Devanagari (हिन्दी), Telugu, Tamil, Bengali characters."
    ),
    "Urdu": (
        "STRICT LANGUAGE PURITY (CRITICAL): Your ENTIRE output MUST use ONLY Arabic/Nastaliq script (اردو نستعلیق). "
        "ABSOLUTELY FORBIDDEN: Devanagari (हिन्दी), Telugu, Tamil, Bengali characters. "
        "Write in right-to-left Urdu script throughout."
    ),
}


# call_gemini_with_timeout is now imported from app.utils.gemini_utils


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
        translation_mode: str = "bilingual",
    ) -> str:
        """
        Dispatcher method that routes to either the monolingual or bilingual translation pipeline.
        """
        if translation_mode == "monolingual":
            return await self._translate_monolingual(markdown_content, target_language_code, page_number)
        else:
            return await self._translate_bilingual(markdown_content, target_language_code, page_number)

    async def _translate_bilingual(
        self,
        markdown_content: str,
        target_language_code: str,
        page_number: int = 1,
    ) -> str:
        if not markdown_content or not markdown_content.strip():
            return ""

        markdown_content = self._pre_process_fragments(markdown_content)
        target_language = get_language_name(target_language_code)
        language_style_note = LANGUAGE_STYLE_NOTES.get(
            target_language,
            f"Use formal written {target_language} as used in government competitive exam papers. Prefer Sanskrit-origin/tatsama vocabulary over colloquial forms."
        )
        language_purity_note = LANGUAGE_PURITY_RULES.get(target_language, "")

        prompt = f"""You are an expert translator specializing in translating English educational/exam documents to {target_language}.

TASK: Translate the following extracted Markdown content from English to {target_language}.
However, instead of just returning the translation, you must generate a BILINGUAL document. 
For EVERY question, header, instruction, or paragraph: output the ENTIRE question/text block in English first, followed by a blank line, and then the ENTIRE translated block in {target_language} immediately below it.
You MUST interleave English and {target_language} QUESTION BY QUESTION (or paragraph by paragraph). Do NOT group all English text at the top and all {target_language} text at the bottom.

TRANSLATION STYLE:
- Generate {target_language} in FORMAL COMPETITIVE EXAMINATION style used in SSC/Banking/State PSC exams.
- Use standard written {target_language}. Avoid conversational or spoken tone.
- {language_style_note}
- {language_purity_note}
- Avoid literal word-by-word translation. Use structured exam phrasing that sounds natural in {target_language}.
- Technical terms commonly used in exams (like "compound interest", "ratio", "percentage") should use the standard {target_language} equivalents used in government exam papers.

CRITICAL RULES:
1. **QUESTION-BY-QUESTION INTERLEAVING**: You MUST pair the English text and its {target_language} translation together for every individual question. 
   - **CRITICAL ORDERING**: For each question, output the English Question Text AND English Options first. Then, output the Translated Question Text AND Translated Options immediately below it.
   - **ANTI-TRUNCATION (CRITICAL)**: You MUST translate ALL questions. Do NOT stop halfway.
2. **MERGE FRAGMENTED SENTENCES**: The input OCR text is sometimes fragmented. Reconstruct and merge these fragments into proper, continuous English sentences BEFORE displaying the English version and generating the {target_language} translation.
3. **INLINE MATH MUST STAY INLINE**: NEVER isolate inline math, positions (e.g., `16^{{th}}`), or numbers on new lines. They MUST be embedded continuously inside the sentence.
4. **IGNORE HEADERS/LOGOS**: Completely EXCLUDE any institute names, logos, contact details, phone numbers, or branch addresses at the top or bottom of the page. Do NOT translate or include them in your output. Start directly with the test name, directions, or exam content.
5. **TABLE TRANSLATION**: Tables are critical — follow these rules strictly:
   - PRESERVE the Markdown table pipe syntax EXACTLY: `| header1 | header2 |`, `|---|---|`, `| data1 | data2 |`.
   - Create BILINGUAL cells inside the table by putting the English text and the {target_language} text in the same cell separated by `<br>`.
   - Keep numbers, dates, and abbreviations inside cells unchanged.
   - DO NOT break the table structure — each row must have the same number of `|` pipes.
   - Example: `| Year | Students |` → `| Year<br>సంవత్సరం | Students<br>విద్యార్థులు |` (for Telugu)
6. PRESERVE all Markdown formatting exactly (headers, bold, italic, lists, links, table syntax).
7. **MCQ OPTIONS (MULTIPLE CHOICE QUESTIONS)**: For options like `A) Option text`, you MUST output English options WITH the English Question Text, and {target_language} options WITH the {target_language} Question Text.

EXAMPLE OUTPUT FORMAT:
[English Question 1 Text]
[English Question 1 Options]

[Translated {target_language} Question 1 Text]
[Translated {target_language} Question 1 Options]

[English Question 2 Text]
[English Question 2 Options]

[Translated {target_language} Question 2 Text]
[Translated {target_language} Question 2 Options]

   - Example CORRECT Format for Options:
     `A) Rangbang`
     `B) Another Option`
     `C) Third Option`
     `D) Fourth Option`
     
     `A)` (translation of Rangbang in {target_language})
     `B)` (translation of Another Option in {target_language})
     `C)` (translation of Third Option in {target_language})
     `D)` (translation of Fourth Option in {target_language})
8. **PRESERVE IMAGE TOKENS**: You will see image layout tokens in the text like `<IMG_1234ABCD>`. These represent complex diagrams or tables. You MUST copy these exact tokens into BOTH your English and {target_language} output at the exact location where they visually belong.
9. DO NOT translate mathematical symbols, formulas, numbers, dates, measurements, and proper nouns (SBI, RBI, LIC etc.).
10. **FIX MATH FRACTIONS**: OCR sometimes badly extracts visual fractions as `33^1 \\underline{{3}}` or `33^1_3`. Fix these into proper LaTeX: `$33\\frac{{1}}{{3}}$`.
11. **MATH EXPRESSIONS**: Wrap ALL mathematical expressions, equations, and formulas in LaTeX `$...$`. Examples:
   - `? × 65 ÷ 72 = 195 × 352 ÷ 192` → `$? \\times 65 \\div 72 = 195 \\times 352 \\div 192$`
   - `√256 × ³√1728 = ? × ⁴√4096` → `$\\sqrt{{256}} \\times \\sqrt[3]{{1728}} = ? \\times \\sqrt[4]{{4096}}$`
   - `35% of 180 + 18² = (27)^(5/3) + ?²` → `$35\\% \\text{{ of }} 180 + 18^2 = (27)^{{5/3}} + ?^2$`
12. PRESERVE the exact order, structure, and spacing of content. Ensure the FULL English text block comes first, followed by the FULL {target_language} text block. Do not mix them sentence-by-sentence.
13. Keep question numbers (Q1, Q2, 31., 32., etc.) unchanged. Keep one question number for both the English and the target language translation (e.g., `31. ` before the English text, and no number before the translated text).
14. Output ONLY the BILINGUAL Markdown — no explanations, no wrapping!
15. **HYBRID MATH / ENGLISH OPERATORS**: If a mathematical equation contains English connecting words like 'of' (e.g., `35% of 180` or `?% of 135`), DO NOT translate the word 'of' into {target_language}. Treat the entire string as a rigid math formula and wrap it in MathJax: `$35\\% \\text{{ of }} 180$`.
16. **LITERAL DOLLAR SIGNS**: If you see a literal dollar sign `$` representing money or used in a sequence of symbols (like `3 € $ 1 6 8`), you MUST escape it as `\\$` (e.g., `3 € \\$ 1 6 8`) so it isn't confused with a math block.

MARKDOWN CONTENT TO TRANSLATE (BILINGUAL MODE):
---
{markdown_content}
---

TRANSLATED CONTENT IN BILINGUAL FORMAT:"""

        return await self._execute_translation_call(prompt, page_number, target_language, len(markdown_content))


    async def _translate_monolingual(
        self,
        markdown_content: str,
        target_language_code: str,
        page_number: int = 1,
    ) -> str:
        if not markdown_content or not markdown_content.strip():
            return ""

        markdown_content = self._pre_process_fragments(markdown_content)
        target_language = get_language_name(target_language_code)
        language_style_note = LANGUAGE_STYLE_NOTES.get(
            target_language,
            f"Use formal written {target_language} as used in government competitive exam papers. Prefer Sanskrit-origin/tatsama vocabulary over colloquial forms."
        )
        language_purity_note = LANGUAGE_PURITY_RULES.get(target_language, "")

        prompt = f"""You are an expert translator specializing in translating English educational/exam documents to {target_language}.

TASK: Translate the following extracted Markdown content from English to {target_language}.
However, instead of returning bilingual text, you must generate a document ONLY in {target_language}. Do NOT include the original English text in the output.

TRANSLATION STYLE:
- Generate {target_language} in FORMAL COMPETITIVE EXAMINATION style used in SSC/Banking/State PSC exams.
- Use standard written {target_language}. Avoid conversational or spoken tone.
- {language_style_note}
- {language_purity_note}
- Avoid literal word-by-word translation. Use structured exam phrasing that sounds natural in {target_language}.
- Technical terms commonly used in exams (like "compound interest", "ratio", "percentage") should use the standard {target_language} equivalents used in government exam papers.

CRITICAL RULES:
1. Translate ALL human-readable text to {target_language} — sentences, instructions, directions, question text. REPLACE the English text entirely with the {target_language} text.
2. **MERGE FRAGMENTED SENTENCES (CRITICAL)**: The input OCR text is sometimes fragmented. You MUST reconstruct and merge these fragments into proper, continuous sentences BEFORE translating. Output ONLY the properly MERGED and TRANSLATED sentence in {target_language}.
3. **INLINE MATH MUST STAY INLINE**: NEVER isolate inline math, positions (e.g., `16^{{th}}`), or numbers on new lines. They MUST be embedded continuously inside the sentence. If a sentence has a number in the middle, DO NOT break the sentence.
4. **IGNORE HEADERS/LOGOS**: Completely EXCLUDE any institute names (e.g., 'Sreedhar\\'s CCE'), logos, contact details, phone numbers, or branch addresses at the top or bottom of the page. Do NOT translate or include them in your output. Start directly with the test name, directions, or exam content.
5. **TABLE TRANSLATION**: Tables are critical — follow these rules strictly:
   - PRESERVE the Markdown table pipe syntax EXACTLY: `| header1 | header2 |`, `|---|---|`, `| data1 | data2 |`.
   - Create cells with ONLY the {target_language} text. DO NOT include English text.
   - Example: `| Year | Students |` → `| సంవత్సరం | విద్యార్థులు |` (for Telugu)
6. PRESERVE all Markdown formatting exactly (headers, bold, italic, lists, links, table syntax).
7. **MCQ OPTIONS (MULTIPLE CHOICE QUESTIONS)**: For options like `A) Option text` or `1) Option text`, you MUST output ONLY the {target_language} version. Keep the option label (`A)`, `1)`, etc.) unchanged.
    - Example: `A) Rangbang` → `A)` (translated text in {target_language})
8. **PRESERVE IMAGE TOKENS**: You will see image layout tokens in the text like `<IMG_1234ABCD>`. These represent complex diagrams or tables. You MUST copy these exact tokens into your {target_language} output at the exact location where they visually belong.
9. DO NOT translate mathematical symbols, formulas, numbers, dates, measurements, and proper nouns (SBI, RBI, LIC etc.).
10. **FIX MATH FRACTIONS**: OCR sometimes badly extracts visual fractions as `33^1 \\underline{{3}}` or `33^1_3`. Fix these into proper LaTeX: `$33\\frac{{1}}{{3}}$`.
11. **MATH EXPRESSIONS**: Wrap ALL mathematical expressions, equations, and formulas in LaTeX `$...$`. Examples:
   - `? × 65 ÷ 72 = 195 × 352 ÷ 192` → `$? \\times 65 \\div 72 = 195 \\times 352 \\div 192$`
   - `√256 × ³√1728 = ? × ⁴√4096` → `$\\sqrt{{256}} \\times \\sqrt[3]{{1728}} = ? \\times \\sqrt[4]{{4096}}$`
   - `35% of 180 + 18² = (27)^(5/3) + ?²` → `$35\\% \\text{{ of }} 180 + 18^2 = (27)^{{5/3}} + ?^2$`
12. PRESERVE the exact order, structure, and spacing of content. Output ONLY the {target_language} Version.
13. Keep question numbers (Q1, Q2, 31., 32., etc.) unchanged. Example: `31. ` before the translated text.
14. Output ONLY the {target_language} Markdown — no explanations, no wrapping!
15. **HYBRID MATH / ENGLISH OPERATORS**: If a mathematical equation contains English connecting words like 'of' (e.g., `35% of 180` or `?% of 135`), DO NOT translate the word 'of' into {target_language}. Treat the entire string as a rigid math formula and wrap it in MathJax: `$35\\% \\text{{ of }} 180$`.
16. **LITERAL DOLLAR SIGNS**: If you see a literal dollar sign `$` representing money or used in a sequence of symbols (like `3 € $ 1 6 8`), you MUST escape it as `\\$` (e.g., `3 € \\$ 1 6 8`) so it isn't confused with a math block.

MARKDOWN CONTENT TO TRANSLATE (MONOLINGUAL MODE):
---
{markdown_content}
---

TRANSLATED CONTENT IN {target_language} ONLY:"""

        return await self._execute_translation_call(prompt, page_number, target_language, len(markdown_content))


    def _clean_hallucinated_scripts(self, text: str, target_language: str) -> tuple[str, list[str]]:
        """
        Detect and remove characters from unauthorized Indic scripts.
        
        Returns:
            (cleaned_text, list_of_violations) — violations is a list of
            (script_name, offending_chars) strings for logging.
        """
        target_script = LANGUAGE_TO_SCRIPT.get(target_language)
        if not target_script:
            return text, []

        violations = []

        for script_name, (range_start, range_end) in SCRIPT_UNICODE_RANGES.items():
            # Skip the target language's own script
            if script_name == target_script:
                continue

            # Build regex for this script's Unicode range using chr()
            range_pattern = f'[{chr(range_start)}-{chr(range_end)}]+'
            pattern = re.compile(range_pattern)
            found = pattern.findall(text)

            if found:
                violations.append(f"{script_name}: {'|'.join(found[:5])}")
                # Remove the offending characters
                text = pattern.sub('', text)

        # Clean up: remove leftover double spaces from stripped characters
        text = re.sub(r'  +', ' ', text)

        return text, violations

    async def _execute_translation_call(self, prompt: str, page_number: int, target_language: str, content_length: int) -> str:
        max_attempts = 3
        last_violations = []
        current_prompt = prompt

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    f"Translating page {page_number} to {target_language} "
                    f"({content_length} chars) — attempt {attempt}/{max_attempts}..."
                )

                # Use lower temperature on retries for more deterministic output
                temperature = 0.1 if attempt == 1 else (0.05 if attempt == 2 else 0.02)

                response = await call_gemini_with_timeout(
                    self.client,
                    self.model,
                    current_prompt,
                    types.GenerateContentConfig(
                        temperature=temperature,
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

                # Post-processing: detect and strip unauthorized scripts
                cleaned, violations = self._clean_hallucinated_scripts(translated, target_language)

                if violations:
                    logger.warning(
                        f"Page {page_number}, attempt {attempt}: "
                        f"LANGUAGE CONTAMINATION DETECTED — {'; '.join(violations)}"
                    )
                    last_violations = violations

                    if attempt < max_attempts:
                        # Build a stronger retry prompt with explicit violation feedback
                        violation_feedback = (
                            f"\n\nCRITICAL CORRECTION — YOUR PREVIOUS OUTPUT CONTAINED ERRORS:\n"
                            f"Your previous translation included characters from WRONG scripts: "
                            f"{'; '.join(violations)}.\n"
                            f"You MUST output ONLY {target_language} script characters.\n"
                            f"Here is your cleaned output for reference — fix the contaminated parts "
                            f"and re-translate properly:\n---\n{cleaned[:2000]}\n---\n"
                            f"Output the CORRECTED translation in PURE {target_language} only:"
                        )
                        current_prompt = prompt + violation_feedback
                        logger.info(
                            f"Page {page_number}: Retrying with violation feedback "
                            f"(augmented prompt by {len(violation_feedback)} chars)..."
                        )
                        continue
                    else:
                        # Final attempt — use the cleaned version
                        logger.warning(
                            f"Page {page_number}: Using cleaned translation after {max_attempts} attempts. "
                            f"Stripped contamination: {'; '.join(last_violations)}"
                        )
                        translated = cleaned
                else:
                    if attempt > 1:
                        logger.info(
                            f"Page {page_number}: Retry attempt {attempt} produced clean translation!"
                        )

                logger.info(
                    f"Translation complete for page {page_number}: "
                    f"{len(translated)} chars"
                )

                return translated

            except TranslationError:
                raise
            except TimeoutError as e:
                logger.error(f"Translation timed out for page {page_number}: {str(e)}")
                if attempt == max_attempts:
                    raise TranslationError(f"Failed to translate page {page_number}: {str(e)}")
                logger.info(f"Page {page_number}: Retrying after timeout...")
            except Exception as e:
                logger.error(f"Translation failed for page {page_number}: {str(e)}")
                if attempt == max_attempts:
                    raise TranslationError(f"Failed to translate page {page_number}: {str(e)}")
                logger.info(f"Page {page_number}: Retrying after error...")

        # Should never reach here, but just in case
        raise TranslationError(f"Translation failed for page {page_number} after {max_attempts} attempts")
