import httpx
import os
from .base import BaseProvider, register_provider


SUNBIRD_LANG_CODES: dict[str, str] = {
    "luganda":    "lug",
    "swahili":    "swa",
    "acholi":     "ach",
    "ateso":      "teo",
    "runyankole": "nyn",
    "kinyarwanda": "kin",
    "lingala":    "lin",
    "somali":     "som",
}


class SunbirdProvider(BaseProvider):
    name = "sunbird"
    cost_per_1k_tokens = 0.0    # free tier

    async def complete(self, prompt: str, max_tokens: int = 1000) -> tuple[str, int]:
        """
        Prompt format expected: "Translate to {language}: {text}"
        Parses the target language from the prompt, calls Sunbird API.
        """
        target_lang = "lug"        # default: Luganda
        text_to_translate = prompt

        for lang_name, code in SUNBIRD_LANG_CODES.items():
            if lang_name in prompt.lower():
                target_lang = code
                parts = prompt.split(":", 1)
                if len(parts) > 1:
                    text_to_translate = parts[1].strip()
                break

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sunbird.ai/tasks/translate",
                headers={
                    "Authorization": f"Bearer {os.environ['SUNBIRD_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "source_language": "eng",
                    "target_language": target_lang,
                    "text": text_to_translate,
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            translated = data.get("output", {}).get("translated_text", "")
            return translated, len(text_to_translate.split())


register_provider(SunbirdProvider())
