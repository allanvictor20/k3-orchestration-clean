"""
retry.py — Execution Recovery Layer.

Transforms the backend from fragile orchestration into resilient orchestration.

Provides:
  - Configurable per-subtask retry with exponential backoff
  - Automatic fallback to an alternate provider on repeated failure
  - Timeout detection and enforcement
  - Partial workflow continuation (failed subtasks do not block succeeded ones)
  - Structured retry events emitted for audit and streaming

Usage in executor.py:
    from retry import RetryEngine

    engine = RetryEngine()
    result = await engine.execute_with_retry(subtask, primary_provider, routing_map)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from models import SubTask, AgentResult
from providers.base import get_provider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Per-provider fallback chain.  When a provider fails, the engine tries the
# next provider in that provider's chain before giving up on the subtask.
FALLBACK_CHAINS: dict[str, list[str]] = {
    "anthropic":  ["openai", "gemini"],
    "openai":     ["anthropic", "gemini"],
    "perplexity": ["anthropic", "openai"],
    "gemini":     ["anthropic", "openai"],
    "sunbird":    ["anthropic"],          # no direct equivalent; Claude can translate
}

# Task-type-aware fallbacks (override generic chain when task type is known)
TASK_FALLBACKS: dict[str, list[str]] = {
    "translation": ["sunbird", "anthropic"],
    "research":    ["perplexity", "anthropic"],
    "coding":      ["anthropic", "openai"],
    "reasoning":   ["openai", "anthropic"],
    "writing":     ["anthropic", "openai"],
}

# Per-subtask execution timeout (seconds).  Prevents hung providers from
# blocking the entire workflow indefinitely.
DEFAULT_TIMEOUT_SECONDS: float = 45.0

# Default retry settings
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BASE_BACKOFF: float = 1.0    # seconds; doubles on each retry
DEFAULT_MAX_BACKOFF: float = 16.0


# ---------------------------------------------------------------------------
# Retry event (for audit + streaming)
# ---------------------------------------------------------------------------

@dataclass
class RetryEvent:
    subtask_id: str
    attempt: int
    provider: str
    error: str
    fallback_provider: Optional[str]
    timestamp: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        return {
            "subtask_id": self.subtask_id,
            "attempt": self.attempt,
            "provider": self.provider,
            "error": self.error,
            "fallback_provider": self.fallback_provider,
        }


# Callable type for retry event listeners (e.g. audit logger, SSE emitter)
RetryListener = Callable[[RetryEvent], Awaitable[None]]


# ---------------------------------------------------------------------------
# RetryEngine
# ---------------------------------------------------------------------------

class RetryEngine:
    """
    Resilient subtask execution with retry and provider fallback.

    Attributes:
        max_retries:       Maximum retry attempts per subtask.
        timeout_seconds:   Timeout per individual provider call.
        on_retry:          Optional async callback called on every retry event.
    """

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        on_retry: Optional[RetryListener] = None,
    ) -> None:
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.on_retry = on_retry

    async def execute_with_retry(
        self,
        subtask: SubTask,
        primary_provider: str,
        task_type: Optional[str] = None,
    ) -> AgentResult:
        """
        Execute a subtask against primary_provider, with automatic retry and
        fallback to alternate providers on failure.

        Returns an AgentResult.  The result's success=False if all attempts
        exhausted — callers must handle degraded workflows gracefully.
        """
        providers_to_try = self._build_provider_sequence(
            primary_provider, task_type or subtask.type
        )
        last_error = "Unknown error"

        for attempt, provider_name in enumerate(providers_to_try, start=1):
            try:
                result = await asyncio.wait_for(
                    self._call_provider(subtask, provider_name),
                    timeout=self.timeout_seconds,
                )

                if result.success:
                    if attempt > 1:
                        logger.info(
                            "subtask succeeded on attempt %d via %s",
                            attempt, provider_name,
                            extra={"subtask_id": subtask.id},
                        )
                    return result

                # Provider returned a response but success=False (soft failure)
                last_error = result.error or "Provider returned failure"
                logger.warning(
                    "provider %s soft-failed subtask %s: %s",
                    provider_name, subtask.id, last_error
                )

            except asyncio.TimeoutError:
                last_error = f"Provider {provider_name} timed out after {self.timeout_seconds}s"
                logger.warning("timeout: subtask %s via %s", subtask.id, provider_name)

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "exception executing subtask %s via %s: %s",
                    subtask.id, provider_name, exc
                )

            # Determine next provider for event metadata
            next_provider = (
                providers_to_try[attempt]
                if attempt < len(providers_to_try)
                else None
            )

            retry_event = RetryEvent(
                subtask_id=subtask.id,
                attempt=attempt,
                provider=provider_name,
                error=last_error,
                fallback_provider=next_provider,
            )

            if self.on_retry:
                await self.on_retry(retry_event)

            # Apply backoff before next attempt (skip after last attempt)
            if attempt < len(providers_to_try):
                backoff = min(DEFAULT_BASE_BACKOFF * (2 ** (attempt - 1)), DEFAULT_MAX_BACKOFF)
                logger.info(
                    "retrying subtask %s in %.1fs with provider %s",
                    subtask.id, backoff, next_provider
                )
                await asyncio.sleep(backoff)

        # All providers exhausted
        logger.error(
            "subtask %s failed after %d attempts. Last error: %s",
            subtask.id, len(providers_to_try), last_error
        )
        return AgentResult(
            subtask_id=subtask.id,
            provider=primary_provider,
            output="",
            latency_ms=0,
            token_usage=0,
            cost_usd=0.0,
            success=False,
            error=f"All providers failed. Last error: {last_error}",
        )

    async def _call_provider(self, subtask: SubTask, provider_name: str) -> AgentResult:
        """
        Call a single provider for a single subtask and return an AgentResult.
        Does not handle retries — that is execute_with_retry's responsibility.
        """
        provider = get_provider(provider_name)
        start = time.monotonic()
        try:
            output, token_usage = await provider.complete(subtask.description)
            latency_ms = int((time.monotonic() - start) * 1000)
            return AgentResult(
                subtask_id=subtask.id,
                provider=provider_name,
                output=output,
                latency_ms=latency_ms,
                token_usage=token_usage,
                cost_usd=provider.estimate_cost(token_usage),
                success=True,
            )
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AgentResult(
                subtask_id=subtask.id,
                provider=provider_name,
                output="",
                latency_ms=latency_ms,
                token_usage=0,
                cost_usd=0.0,
                success=False,
                error=str(exc),
            )

    def _build_provider_sequence(self, primary: str, task_type: str) -> list[str]:
        """
        Build the ordered list of providers to attempt: [primary, fallback1, fallback2, …]

        Uses task-type-aware fallbacks when available, then falls back to the
        generic provider chain.  Deduplicates while preserving order.
        """
        # Start with task-type specific sequence if defined
        if task_type in TASK_FALLBACKS:
            base = list(TASK_FALLBACKS[task_type])
        else:
            # Generic: primary + provider's fallback chain
            base = [primary] + list(FALLBACK_CHAINS.get(primary, []))

        # Ensure primary is always first
        if primary in base:
            base.remove(primary)
        sequence = [primary] + base

        # Deduplicate preserving order, limit to max_retries + 1 total providers
        seen: set[str] = set()
        unique: list[str] = []
        for p in sequence:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        return unique[: self.max_retries + 1]


# ---------------------------------------------------------------------------
# Resilient plan executor (drop-in replacement for executor.execute_plan)
# ---------------------------------------------------------------------------

async def execute_plan_resilient(
    plan,          # models.ExecutionPlan
    retry_engine: Optional[RetryEngine] = None,
) -> list[AgentResult]:
    """
    Execute an ExecutionPlan using the RetryEngine for each subtask.

    Parallel groups still run concurrently.  Individual subtask failures are
    captured as AgentResult(success=False) rather than raising exceptions,
    enabling partial workflow continuation.

    This is the resilient replacement for executor.execute_plan().
    """
    if retry_engine is None:
        retry_engine = RetryEngine()

    all_results: list[AgentResult] = []
    subtask_index = {t.id: t for t in plan.subtasks}

    for group in plan.parallel_groups:
        group_tasks = [
            retry_engine.execute_with_retry(
                subtask_index[tid],
                plan.routing_map.get(tid, "anthropic"),
            )
            for tid in group
            if tid in subtask_index
        ]
        # return_exceptions=False because execute_with_retry never raises —
        # failures are returned as AgentResult(success=False)
        group_results = await asyncio.gather(*group_tasks, return_exceptions=False)
        all_results.extend(group_results)

    return all_results
