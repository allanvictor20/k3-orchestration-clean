from abc import ABC, abstractmethod

_registry: dict[str, "BaseProvider"] = {}


class BaseProvider(ABC):
    name: str
    cost_per_1k_tokens: float = 0.003

    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 1000) -> tuple[str, int]:
        """Returns (output_text, token_count)."""
        ...

    def estimate_cost(self, token_count: int) -> float:
        return (token_count / 1000) * self.cost_per_1k_tokens


def register_provider(provider: "BaseProvider"):
    _registry[provider.name] = provider


def get_provider(name: str) -> "BaseProvider":
    if name not in _registry:
        raise ValueError(
            f"Provider '{name}' not registered. Available: {list(_registry.keys())}"
        )
    return _registry[name]


def list_providers() -> list[str]:
    return list(_registry.keys())
