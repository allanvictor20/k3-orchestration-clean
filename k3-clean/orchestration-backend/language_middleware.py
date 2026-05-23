"""
language_middleware.py — Language Detection & Bidirectional Translation.

Handles:
  - Detecting whether a prompt is in a local language (Luganda, Swahili, etc.)
  - Translating prompts into English before orchestration
  - Translating the final English response back to the user's chosen language
  - Supporting explicit input_language / output_language selection from the UI

Supported languages:
  en  — English (no translation needed)
  lg  — Luganda
  sw  — Swahili
  ach — Acholi
  nyn — Runyankole
  kin — Kinyarwanda
"""

from __future__ import annotations

import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES: dict[str, dict] = {
    "en":  {"sunbird_code": "eng", "name": "English"},
    "lg":  {"sunbird_code": "lug", "name": "Luganda"},
    "sw":  {"sunbird_code": "swa", "name": "Swahili"},
    "ach": {"sunbird_code": "ach", "name": "Acholi"},
    "nyn": {"sunbird_code": "nyn", "name": "Runyankole"},
    "kin": {"sunbird_code": "kin", "name": "Kinyarwanda"},
}

# Human-readable language names for the UI
LANGUAGE_OPTIONS: list[dict] = [
    {"code": code, "name": info["name"]}
    for code, info in SUPPORTED_LANGUAGES.items()
]


# ---------------------------------------------------------------------------
# Auto-detection patterns (used when input_language = "auto")
# ---------------------------------------------------------------------------

LUGANDA_KEYWORDS = [
    "nkwagala", "webale", "ssebo", "nnyabo", "kiki", "oliwa",
    "ndi", "nga", "naye", "kale", "gyendi", "mpa", "nsaba",
    "njagala", "nkola", "tulaba", "tukola", "leero", "enkya",
    "jjo", "kitalo", "simanyi", "nkubuulira", "nsaba", "nkusiima",
]

LANGUAGE_TRIGGER_PATTERNS: dict[str, list[str]] = {
    "lg":  [r"\bluganda\b", r"\bmu luganda\b", r"\bin luganda\b"],
    "sw":  [r"\bswahili\b", r"\bkiswahili\b", r"\bkwa kiswahili\b"],
    "ach": [r"\bacholi\b", r"\bluo\b"],
    "nyn": [r"\brunyankole\b", r"\bnkore\b"],
    "kin": [r"\bkinyarwanda\b", r"\brwanda\b"],
}


def detect_language(prompt: str) -> str:
    """
    Auto-detect language from prompt text.
    Returns a language code ('lg', 'sw', etc.) or 'en' for English.
    """
    prompt_lower = prompt.lower()

    # Check for explicit language-request phrases
    for lang_code, patterns in LANGUAGE_TRIGGER_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, prompt_lower):
                return lang_code

    # Check for actual Luganda vocabulary in the prompt
    luganda_hits = sum(1 for word in LUGANDA_KEYWORDS if word in prompt_lower)
    if luganda_hits >= 2:
        return "lg"

    return "en"


# ---------------------------------------------------------------------------
# Sunbird translation
# ---------------------------------------------------------------------------

async def _call_sunbird(text: str, source_lang: str, target_lang: str) -> str:
    """
    Calls the Sunbird AI translation API.
    source_lang and target_lang are Sunbird codes (e.g. 'lug', 'eng').
    Returns translated text, or the original text on failure.
    """
    if source_lang == target_lang:
        return text

    api_key = os.environ.get("SUNBIRD_API_KEY", "")
    if not api_key:
        logger.warning("SUNBIRD_API_KEY not set — skipping translation")
        return text

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sunbird.ai/tasks/translate",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "source_language": source_lang,
                    "target_language": target_lang,
                    "text": text,
                },
                timeout=20.0,
            )
            response.raise_for_status()
            data = response.json()
            translated = data.get("output", {}).get("translated_text", text)
            logger.info(
                "Sunbird translated %s→%s (%d chars → %d chars)",
                source_lang, target_lang, len(text), len(translated)
            )
            return translated
    except Exception as exc:
        logger.error("Sunbird translation failed: %s — returning original text", exc)
        return text


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

async def prepare_prompt(
    prompt: str,
    input_language: str = "en",
    output_language: str = "en",
) -> dict:
    """
    Prepares a prompt for orchestration:
      1. Resolves the actual language (auto-detect if input_language='auto')
      2. Translates the prompt to English if needed
      3. Returns a context dict that must be passed to translate_response_back()

    Returns:
        {
            "english_prompt":         str,   # what goes into orchestration
            "original_prompt":        str,   # what the user actually typed
            "resolved_input_language": str,  # actual detected/chosen lang code
            "output_language":         str,  # what language to respond in
            "needs_translation_in":    bool,
            "needs_translation_out":   bool,
            "sunbird_input_code":      str,
            "sunbird_output_code":     str,
        }
    """
    # Resolve input language
    if input_language == "auto":
        resolved_input = detect_language(prompt)
    else:
        resolved_input = input_language if input_language in SUPPORTED_LANGUAGES else "en"

    resolved_output = output_language if output_language in SUPPORTED_LANGUAGES else "en"

    needs_in  = resolved_input != "en"
    needs_out = resolved_output != "en"

    input_sunbird  = SUPPORTED_LANGUAGES.get(resolved_input,  {}).get("sunbird_code", "eng")
    output_sunbird = SUPPORTED_LANGUAGES.get(resolved_output, {}).get("sunbird_code", "eng")

    # Translate prompt to English if needed
    if needs_in:
        english_prompt = await _call_sunbird(prompt, input_sunbird, "eng")
    else:
        english_prompt = prompt

    return {
        "english_prompt":          english_prompt,
        "original_prompt":         prompt,
        "resolved_input_language": resolved_input,
        "output_language":         resolved_output,
        "needs_translation_in":    needs_in,
        "needs_translation_out":   needs_out,
        "sunbird_input_code":      input_sunbird,
        "sunbird_output_code":     output_sunbird,
    }


async def translate_response_back(english_response: str, lang_context: dict) -> str:
    """
    Translates the final English orchestration output back to the user's
    chosen output language. If output_language is English, returns as-is.
    """
    if not lang_context.get("needs_translation_out"):
        return english_response

    output_sunbird = lang_context.get("sunbird_output_code", "eng")
    return await _call_sunbird(english_response, "eng", output_sunbird)
