"""
normalizer.py — Provider Response Normalization Layer.

Every AI provider returns results in a slightly different schema.
This module normalises all of them into one canonical NormalizedResponse,
making merger.py, validator.py, audit.py, and the frontend all work with
a single consistent structure.

Normalised schema:
    {
        "provider":      str,        # "anthropic" | "openai" | "perplexity" | …
        "status":        str,        # "success" | "failed" | "partial"
        "content":       str,        # extracted text output
        "latency_ms":    int,
        "tokens":        int,        # total tokens consumed (input + output)
        "confidence":    float,      # 0.0–1.0 (heuristic; V2: LLM judge)
        "error":         str | None,
        "raw":           dict,       # original provider payload (for debugging)
    }
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from typing import Any, Optional

from models import AgentResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalised response dataclass
# ---------------------------------------------------------------------------

@dataclass
class NormalizedResponse:
    provider:   str
    status:     str          # "success" | "failed" | "partial"
    content:    str
    latency_ms: int
    tokens:     int
    confidence: float        # 0.0–1.0
    error:      Optional[str] = None
    raw:        Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def is_usable(self) -> bool:
        """True if the response has enough content to be worth merging."""
        return self.is_success and len(self.content.strip()) >= 20


# ---------------------------------------------------------------------------
# Normalise from AgentResult (the internal model used by executor.py)
# ---------------------------------------------------------------------------

def normalize_agent_result(result: AgentResult) -> NormalizedResponse:
    """
    Convert an AgentResult (as returned by executor.py) into a NormalizedResponse.

    This is the primary entry point.  All other normalize_* helpers below are
    used when you have raw API payloads (e.g. during testing or future direct
    provider integration).
    """
    if not result.success:
        return NormalizedResponse(
            provider=result.provider,
            status="failed",
            content="",
            latency_ms=result.latency_ms,
            tokens=result.token_usage,
            confidence=0.0,
            error=result.error,
            raw={"subtask_id": result.subtask_id},
        )

    content = result.output.strip()
    confidence = _heuristic_confidence(content, result.latency_ms, result.token_usage)

    return NormalizedResponse(
        provider=result.provider,
        status="success" if confidence >= 0.3 else "partial",
        content=content,
        latency_ms=result.latency_ms,
        tokens=result.token_usage,
        confidence=confidence,
        raw={"subtask_id": result.subtask_id},
    )


def normalize_batch(results: list[AgentResult]) -> list[NormalizedResponse]:
    """Normalize a list of AgentResult objects."""
    return [normalize_agent_result(r) for r in results]


# ---------------------------------------------------------------------------
# Raw provider payload normalizers
# (used when calling providers outside of executor.py, e.g. in tests)
# ---------------------------------------------------------------------------

def normalize_anthropic(raw: dict[str, Any], latency_ms: int = 0) -> NormalizedResponse:
    """
    Anthropic Claude response shape:
        {"content": [{"type": "text", "text": "…"}], "usage": {"input_tokens": N, "output_tokens": M}}
    """
    try:
        blocks = raw.get("content", [])
        text = " ".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        ).strip()
        usage = raw.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return NormalizedResponse(
            provider="anthropic",
            status="success" if text else "partial",
            content=text,
            latency_ms=latency_ms,
            tokens=tokens,
            confidence=_heuristic_confidence(text, latency_ms, tokens),
            raw=raw,
        )
    except Exception as exc:
        logger.warning("normalize_anthropic failed: %s", exc)
        return _error_response("anthropic", str(exc), raw)


def normalize_openai(raw: dict[str, Any], latency_ms: int = 0) -> NormalizedResponse:
    """
    OpenAI / GPT response shape:
        {"choices": [{"message": {"content": "…"}}], "usage": {"total_tokens": N}}
    """
    try:
        choices = raw.get("choices", [])
        text = choices[0]["message"]["content"].strip() if choices else ""
        tokens = raw.get("usage", {}).get("total_tokens", 0)
        return NormalizedResponse(
            provider="openai",
            status="success" if text else "partial",
            content=text,
            latency_ms=latency_ms,
            tokens=tokens,
            confidence=_heuristic_confidence(text, latency_ms, tokens),
            raw=raw,
        )
    except Exception as exc:
        logger.warning("normalize_openai failed: %s", exc)
        return _error_response("openai", str(exc), raw)


def normalize_perplexity(raw: dict[str, Any], latency_ms: int = 0) -> NormalizedResponse:
    """
    Perplexity response shape (same as OpenAI chat completions):
        {"choices": [{"message": {"content": "…"}}], "usage": {"total_tokens": N}}
    Also accepts {"answer": "…"} for older API versions.
    """
    try:
        # Newer API (chat completions compatible)
        if "choices" in raw:
            return normalize_openai({**raw}, latency_ms)

        # Older / alternate shape
        text = raw.get("answer", raw.get("text", "")).strip()
        tokens = raw.get("usage", {}).get("total_tokens", 0)
        return NormalizedResponse(
            provider="perplexity",
            status="success" if text else "partial",
            content=text,
            latency_ms=latency_ms,
            tokens=tokens,
            confidence=_heuristic_confidence(text, latency_ms, tokens),
            raw=raw,
        )
    except Exception as exc:
        logger.warning("normalize_perplexity failed: %s", exc)
        return _error_response("perplexity", str(exc), raw)


def normalize_gemini(raw: dict[str, Any], latency_ms: int = 0) -> NormalizedResponse:
    """
    Google Gemini response shape:
        {"candidates": [{"content": {"parts": [{"text": "…"}]}}],
         "usageMetadata": {"totalTokenCount": N}}
    Also accepts simple {"text": "…"} shape.
    """
    try:
        candidates = raw.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = " ".join(p.get("text", "") for p in parts).strip()
        else:
            text = raw.get("text", "").strip()

        usage = raw.get("usageMetadata", {})
        tokens = usage.get("totalTokenCount", usage.get("total_tokens", 0))

        return NormalizedResponse(
            provider="gemini",
            status="success" if text else "partial",
            content=text,
            latency_ms=latency_ms,
            tokens=tokens,
            confidence=_heuristic_confidence(text, latency_ms, tokens),
            raw=raw,
        )
    except Exception as exc:
        logger.warning("normalize_gemini failed: %s", exc)
        return _error_response("gemini", str(exc), raw)


def normalize_sunbird(raw: dict[str, Any], latency_ms: int = 0) -> NormalizedResponse:
    """
    Sunbird (African language) response shape:
        {"translation": "…"} or {"output": "…"} or {"text": "…"}
    """
    try:
        text = (
            raw.get("translation")
            or raw.get("output")
            or raw.get("text")
            or ""
        ).strip()

        return NormalizedResponse(
            provider="sunbird",
            status="success" if text else "partial",
            content=text,
            latency_ms=latency_ms,
            tokens=0,           # Sunbird doesn't report tokens
            confidence=0.9 if text else 0.0,   # Translation is binary: works or doesn't
            raw=raw,
        )
    except Exception as exc:
        logger.warning("normalize_sunbird failed: %s", exc)
        return _error_response("sunbird", str(exc), raw)


# Registry: provider_name → normalizer function
_NORMALIZERS: dict[str, Any] = {
    "anthropic":  normalize_anthropic,
    "openai":     normalize_openai,
    "perplexity": normalize_perplexity,
    "gemini":     normalize_gemini,
    "sunbird":    normalize_sunbird,
}


def normalize_raw(provider: str, raw: dict[str, Any], latency_ms: int = 0) -> NormalizedResponse:
    """
    Dispatch-normalise a raw provider payload by provider name.
    Falls back to a generic extractor if the provider is unknown.
    """
    fn = _NORMALIZERS.get(provider)
    if fn:
        return fn(raw, latency_ms)

    # Generic fallback: try common content keys
    logger.warning("normalize_raw: unknown provider '%s'; using generic extractor", provider)
    text = (
        raw.get("content")
        or raw.get("text")
        or raw.get("answer")
        or raw.get("output")
        or raw.get("result")
        or ""
    )
    if isinstance(text, list):
        text = " ".join(str(t) for t in text)
    text = str(text).strip()

    return NormalizedResponse(
        provider=provider,
        status="success" if text else "partial",
        content=text,
        latency_ms=latency_ms,
        tokens=0,
        confidence=_heuristic_confidence(text, latency_ms, 0),
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _heuristic_confidence(content: str, latency_ms: int, tokens: int) -> float:
    """
    Simple heuristic confidence score (0.0–1.0).
    V2: replace with an LLM judge for semantic quality.
    """
    if not content:
        return 0.0

    score = 1.0
    length = len(content.strip())

    # Very short content likely truncated or errored silently
    if length < 20:
        score -= 0.6
    elif length < 80:
        score -= 0.2

    # High latency suggests a timeout or retry
    if latency_ms > 15_000:
        score -= 0.3
    elif latency_ms > 8_000:
        score -= 0.1

    # Zero tokens: provider returned empty or usage wasn't reported
    if tokens == 0:
        score -= 0.15

    # Repetition penalty: >30% of content is the same word
    words = re.findall(r"\w+", content.lower())
    if len(words) > 10:
        most_common_freq = max(words.count(w) for w in set(words))
        if most_common_freq / len(words) > 0.3:
            score -= 0.25

    return max(0.0, round(score, 2))


def _error_response(provider: str, error: str, raw: Optional[dict]) -> NormalizedResponse:
    return NormalizedResponse(
        provider=provider,
        status="failed",
        content="",
        latency_ms=0,
        tokens=0,
        confidence=0.0,
        error=error,
        raw=raw,
    )
