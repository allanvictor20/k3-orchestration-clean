import os
from .base import BaseProvider, register_provider

# Uses the current google-genai SDK (not the older google-generativeai)
try:
    from google import genai
    from google.genai import types as genai_types
    _SDK = "new"
except ImportError:
    # Fallback to legacy SDK if new one not installed
    import google.generativeai as genai_legacy
    _SDK = "legacy"


class GeminiProvider(BaseProvider):
    name = "gemini"
    cost_per_1k_tokens = 0.002

    def __init__(self):
        if _SDK == "new":
            self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        else:
            genai_legacy.configure(api_key=os.environ["GEMINI_API_KEY"])
            self.model = genai_legacy.GenerativeModel("gemini-1.5-pro")

    async def complete(self, prompt: str, max_tokens: int = 1000) -> tuple[str, int]:
        if _SDK == "new":
            response = await self.client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            text = response.text
            tokens = (response.usage_metadata.total_token_count
                      if response.usage_metadata else len(prompt.split()) + len(text.split()))
        else:
            response = await self.model.generate_content_async(prompt)
            text = response.text
            tokens = len(prompt.split()) + len(text.split())
        return text, tokens


register_provider(GeminiProvider())
