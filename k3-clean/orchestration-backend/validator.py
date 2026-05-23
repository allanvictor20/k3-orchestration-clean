from models import AgentResult, OrchestrationResponse


def score_result(result: AgentResult) -> float:
    """
    Basic confidence score for a single agent result (0.0 – 1.0).
    V2: use an LLM judge for semantic quality scoring.
    """
    if not result.success:
        return 0.0

    score = 1.0

    # Penalise very short outputs (likely truncated or errored silently)
    if len(result.output.strip()) < 50:
        score -= 0.4

    # Penalise high latency (>10s suggests a timeout or retry)
    if result.latency_ms > 10_000:
        score -= 0.2

    # Penalise zero token usage (provider may have returned empty)
    if result.token_usage == 0:
        score -= 0.3

    return max(0.0, round(score, 2))


def validate_response(response: OrchestrationResponse) -> dict:
    """
    Returns a validation summary attached to a completed orchestration response.
    """
    scores = {r.subtask_id: score_result(r) for r in response.subtask_results}
    avg_score = (
        sum(scores.values()) / len(scores) if scores else 0.0
    )
    low_confidence = [sid for sid, s in scores.items() if s < 0.5]

    return {
        "overall_confidence": round(avg_score, 2),
        "per_subtask_scores": scores,
        "low_confidence_subtasks": low_confidence,
        "passed": avg_score >= 0.5,
    }
