import anthropic
import os
from .base import BaseProvider, register_provider


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    cost_per_1k_tokens = 0.003   # claude-sonnet approximate

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    async def complete(self, prompt: str, max_tokens: int = 1000) -> tuple[str, int]:
        message = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
        tokens = message.usage.input_tokens + message.usage.output_tokens
        return text, tokens


register_provider(AnthropicProvider())
