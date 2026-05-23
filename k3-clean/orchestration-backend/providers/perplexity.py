import httpx
import os
from .base import BaseProvider, register_provider


class PerplexityProvider(BaseProvider):
    name = "perplexity"
    cost_per_1k_tokens = 0.001

    async def complete(self, prompt: str, max_tokens: int = 1000) -> tuple[str, int]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}"},
                json={
                    "model": "llama-3.1-sonar-large-128k-online",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", len(prompt.split()))
            return text, tokens


register_provider(PerplexityProvider())
