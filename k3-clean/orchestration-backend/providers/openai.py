import os
from openai import AsyncOpenAI
from .base import BaseProvider, register_provider


class OpenAIProvider(BaseProvider):
    name = "openai"
    cost_per_1k_tokens = 0.004

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def complete(self, prompt: str, max_tokens: int = 1000) -> tuple[str, int]:
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content
        tokens = response.usage.total_tokens
        return text, tokens


register_provider(OpenAIProvider())
