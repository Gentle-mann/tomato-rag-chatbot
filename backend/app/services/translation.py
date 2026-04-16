"""Multilingual translation service with Nepali support."""

import re
from typing import Dict, Optional
import structlog
import litellm

from app.config import settings

logger = structlog.get_logger()

# Agricultural terminology glossary (English -> Nepali)
AGRICULTURE_GLOSSARY = {
    "tomato": "गोलभेडा",
    "seedling": "बिरुवा",
    "transplant": "रोप्नु",
    "fertilizer": "मल",
    "irrigation": "सिंचाइ",
    "harvest": "बाली",
    "pest": "कीरा",
    "disease": "रोग",
    "soil": "माटो",
    "compost": "कम्पोस्ट मल",
    "nitrogen": "नाइट्रोजन",
    "phosphorus": "फस्फोरस",
    "potassium": "पोटासियम",
    "pruning": "काट्छाट",
    "staking": "भ्याङ लगाउने",
    "mulching": "मल्चिङ",
    "greenhouse": "हरितगृह",
    "organic": "जैविक",
    "seed": "बीउ",
    "fruit": "फल",
    "leaf": "पात",
    "root": "जरा",
    "stem": "डाँठ",
    "flower": "फूल",
    "cultivation": "खेती",
    "temperature": "तापक्रम",
    "humidity": "आर्द्रता",
    "watering": "पानी दिने",
}

# Japanese -> English agricultural terms
JA_EN_GLOSSARY = {
    "トマト": "tomato",
    "苗": "seedling",
    "定植": "transplanting",
    "肥料": "fertilizer",
    "灌水": "irrigation",
    "収穫": "harvest",
    "害虫": "pest",
    "病気": "disease",
    "土壌": "soil",
    "剪定": "pruning",
    "種子": "seed",
    "果実": "fruit",
    "葉": "leaf",
    "根": "root",
    "茎": "stem",
    "花": "flower",
    "栽培": "cultivation",
    "温度": "temperature",
    "湿度": "humidity",
}


class TranslationService:
    """
    Multi-tier translation service for multilingual support.

    Translation strategies:
    1. Direct translation via Google Cloud Translation API
    2. LLM-based translation for higher quality
    3. Pivot translation via Hindi for Nepali (linguistic similarity)
    """

    def __init__(self):
        self.google_client = None
        self._init_google_client()

    def _init_google_client(self):
        """Initialize Google Cloud Translation client if credentials available."""
        try:
            if settings.google_cloud_project:
                from google.cloud import translate_v2 as translate
                self.google_client = translate.Client()
                logger.info("Google Translation client initialized")
        except Exception as e:
            logger.warning("Google Translation not available", error=str(e))
            self.google_client = None

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        use_glossary: bool = True,
    ) -> str:
        """
        Translate text between languages.

        Supports: en (English), ne (Nepali), ja (Japanese)
        """
        if source_lang == target_lang:
            return text

        if not text.strip():
            return text

        # Apply glossary pre-processing for technical terms
        if use_glossary:
            text = self._apply_glossary_preprocessing(text, source_lang)

        # Try Google Translation first (fastest)
        if self.google_client:
            try:
                translated = await self._google_translate(text, source_lang, target_lang)
                if translated:
                    # Apply glossary post-processing
                    if use_glossary:
                        translated = self._apply_glossary_postprocessing(
                            translated, target_lang
                        )
                    return translated
            except Exception as e:
                logger.warning("Google Translation failed", error=str(e))

        # Fallback to LLM translation
        try:
            translated = await self._llm_translate(text, source_lang, target_lang)
            return translated
        except Exception as e:
            logger.error("LLM Translation failed", error=str(e))

        # Last resort: return original with language note
        return f"[Translation unavailable] {text}"

    async def _google_translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[str]:
        """Translate using Google Cloud Translation API."""
        if not self.google_client:
            return None

        # Map our language codes to Google's
        lang_map = {
            "en": "en",
            "ne": "ne",
            "ja": "ja",
            "hi": "hi",  # Hindi for pivot
        }

        source = lang_map.get(source_lang, source_lang)
        target = lang_map.get(target_lang, target_lang)

        # For Nepali, consider pivot through Hindi for better quality
        if target_lang == "ne" and source_lang not in ("ne", "hi"):
            # First translate to Hindi
            hindi_result = self.google_client.translate(
                text, source_language=source, target_language="hi"
            )
            # Then Hindi to Nepali
            result = self.google_client.translate(
                hindi_result["translatedText"],
                source_language="hi",
                target_language="ne",
            )
        else:
            result = self.google_client.translate(
                text, source_language=source, target_language=target
            )

        return result["translatedText"]

    async def _llm_translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> str:
        """Translate using LLM for higher quality."""
        lang_names = {
            "en": "English",
            "ne": "Nepali",
            "ja": "Japanese",
            "hi": "Hindi",
        }

        source_name = lang_names.get(source_lang, source_lang)
        target_name = lang_names.get(target_lang, target_lang)

        # Special instructions for Nepali
        special_instructions = ""
        if target_lang == "ne":
            special_instructions = """
Special instructions for Nepali translation:
- Use common Nepali agricultural terms
- Maintain technical accuracy for farming terminology
- Use Devanagari script
- Keep numbers in standard format"""

        prompt = f"""Translate the following text from {source_name} to {target_name}.
This is agricultural content about tomato cultivation.

{special_instructions}

Text to translate:
{text}

Translation:"""

        try:
            response = await litellm.acompletion(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=settings.llm_max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error("LLM translation error", error=str(e))
            raise

    def _apply_glossary_preprocessing(self, text: str, source_lang: str) -> str:
        """Mark technical terms for better translation."""
        if source_lang == "ja":
            # Mark Japanese terms for translation
            for ja_term, en_term in JA_EN_GLOSSARY.items():
                if ja_term in text:
                    text = text.replace(ja_term, f"{ja_term}({en_term})")

        return text

    def _apply_glossary_postprocessing(self, text: str, target_lang: str) -> str:
        """Replace technical terms with correct translations."""
        if target_lang == "ne":
            # Apply Nepali glossary
            for en_term, ne_term in AGRICULTURE_GLOSSARY.items():
                # Case-insensitive replacement
                pattern = re.compile(re.escape(en_term), re.IGNORECASE)
                text = pattern.sub(ne_term, text)

        return text

    async def detect_language(self, text: str) -> str:
        """Detect the language of input text."""
        if not text.strip():
            return "en"

        # Simple heuristics for our supported languages
        # Check for Japanese characters
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text):
            return "ja"

        # Check for Nepali/Devanagari characters
        if re.search(r'[\u0900-\u097F]', text):
            return "ne"

        # Use Google if available
        if self.google_client:
            try:
                result = self.google_client.detect_language(text)
                detected = result["language"]
                if detected in ("en", "ne", "ja"):
                    return detected
            except Exception:
                pass

        # Default to English
        return "en"

    async def translate_with_context(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: str,
    ) -> str:
        """
        Translate text with additional context for better accuracy.

        Useful for translating responses where the original question
        provides context.
        """
        if source_lang == target_lang:
            return text

        prompt = f"""Translate the following agricultural response from {source_lang} to {target_lang}.

Context (the question this responds to):
{context}

Response to translate:
{text}

Provide only the translation, maintaining technical accuracy for tomato cultivation terminology.

Translation:"""

        try:
            response = await litellm.acompletion(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=settings.llm_max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error("Context translation error", error=str(e))
            # Fallback to regular translation
            return await self.translate(text, source_lang, target_lang)


# Singleton instance
_translation_service: TranslationService | None = None


async def get_translation_service() -> TranslationService:
    """Get translation service instance."""
    global _translation_service
    if _translation_service is None:
        _translation_service = TranslationService()
    return _translation_service
