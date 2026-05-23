"""
executor.py — Resilient Subtask Execution Engine.

Replaces the original asyncio.gather() executor with one that:
  - Uses RetryEngine for per-subtask retry + provider fallback
  - Integrates with WorkflowState to emit per-subtask state transitions
  - Publishes real-time SSE events via the WorkflowEventBus
  - Supports partial workflow continuation (failed subtasks don't abort others)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from models import SubTask, AgentResult, ExecutionPlan
from providers.base import get_provider
from retry import RetryEngine, RetryEvent
from streaming import event_bus, OrchestrationEvent
from workflow_state import WorkflowState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry event listener — bridges RetryEngine → SSE + audit
# ---------------------------------------------------------------------------

def _make_retry_listener(workflow_id: str):
    """Return an async callback that publishes retry events to the event bus."""
    async def on_retry(event: RetryEvent) -> None:
        await event_bus.publish(
            workflow_id,
            OrchestrationEvent.RETRY_TRIGGERED,
            event.to_dict(),
        )
    return on_retry


# ---------------------------------------------------------------------------
# Single subtask execution (with state integration)
# ---------------------------------------------------------------------------

async def execute_subtask_tracked(
    subtask: SubTask,
    provider_name: str,
    workflow_id: str,
    state: Optional[WorkflowState],
    retry_engine: RetryEngine,
) -> AgentResult:
    """
    Execute one subtask with retry, state tracking, and SSE event emission.
    """
    # Notify state + SSE that this subtask is starting
    if state:
        state.subtask_started(subtask.id, provider_name)

    await event_bus.publish(workflow_id, OrchestrationEvent.TASK_STARTED, {
        "subtask_id": subtask.id,
        "provider": provider_name,
        "task_type": subtask.type,
        "description": subtask.description[:120],
    })

    result = await retry_engine.execute_with_retry(subtask, provider_name, subtask.type)

    if result.success:
        if state:
            state.subtask_succeeded(result)
        await event_bus.publish(workflow_id, OrchestrationEvent.TASK_COMPLETED, {
            "subtask_id": result.subtask_id,
            "provider": result.provider,
            "latency_ms": result.latency_ms,
            "tokens": result.token_usage,
            "success": True,
        })
    else:
        if state:
            state.subtask_failed(subtask.id, result.error or "Unknown failure")
        await event_bus.publish(workflow_id, OrchestrationEvent.TASK_COMPLETED, {
            "subtask_id": result.subtask_id,
            "provider": result.provider,
            "success": False,
            "error": result.error,
        })

    return result


# ---------------------------------------------------------------------------
# Plan executor (replaces original execute_plan)
# ---------------------------------------------------------------------------

async def execute_plan(
    plan: ExecutionPlan,
    state: Optional[WorkflowState] = None,
    max_retries: int = 3,
    timeout_seconds: float = 45.0,
) -> list[AgentResult]:
    """
    Execute an ExecutionPlan with resilient retry, fallback, and SSE streaming.

    Parallel groups still run concurrently via asyncio.gather().
    Individual subtask failures are captured as AgentResult(success=False)
    rather than crashing the entire workflow.

    Args:
        plan:            The execution plan from router.plan_execution()
        state:           Optional WorkflowState for live status updates
        max_retries:     Max attempts per subtask (including fallback providers)
        timeout_seconds: Per-provider-call timeout
    """
    workflow_id = plan.workflow_id

    retry_engine = RetryEngine(
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        on_retry=_make_retry_listener(workflow_id),
    )

    all_results: list[AgentResult] = []
    subtask_index = {t.id: t for t in plan.subtasks}

    for group in plan.parallel_groups:
        valid_ids = [tid for tid in group if tid in subtask_index and tid in plan.routing_map]

        if not valid_ids:
            continue

        group_tasks = [
            execute_subtask_tracked(
                subtask_index[tid],
                plan.routing_map[tid],
                workflow_id,
                state,
                retry_engine,
            )
            for tid in valid_ids
        ]

        # return_exceptions=False is correct: execute_subtask_tracked never raises
        group_results = await asyncio.gather(*group_tasks, return_exceptions=False)
        all_results.extend(group_results)

    success_count = sum(1 for r in all_results if r.success)
    fail_count = len(all_results) - success_count

    logger.info(
        "plan execution complete: %d succeeded, %d failed",
        success_count, fail_count,
        extra={"workflow_id": workflow_id},
    )

    return all_results
