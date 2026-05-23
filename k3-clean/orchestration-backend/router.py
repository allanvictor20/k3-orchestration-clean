from models import SubTask, ExecutionPlan
from memory import PerformanceMemory


# Static routing map — best provider per task type (MVP defaults)
STATIC_ROUTING: dict[str, str] = {
    "coding":      "anthropic",   # Claude: strongest at code generation
    "reasoning":   "openai",      # GPT-4o: structured reasoning and analysis
    "research":    "perplexity",  # Perplexity: real-time web research
    "translation": "sunbird",     # Sunbird: African language translation
    "writing":     "anthropic",   # Claude: long-form writing and synthesis
}

# Cost estimates per provider (USD per task, rough)
COST_PER_TASK: dict[str, float] = {
    "anthropic":  0.003,
    "openai":     0.004,
    "perplexity": 0.001,
    "sunbird":    0.000,
    "gemini":     0.002,
}

# Latency estimates per provider (ms, rough)
LATENCY_PER_TASK: dict[str, int] = {
    "anthropic":  3000,
    "openai":     4000,
    "perplexity": 5000,
    "sunbird":    2000,
    "gemini":     3500,
}

_memory = PerformanceMemory()


async def route_subtasks(subtasks: list[SubTask]) -> dict[str, str]:
    """
    Returns routing_map: {subtask_id: provider_name}.
    Checks performance memory first; falls back to static routing.
    """
    routing_map: dict[str, str] = {}
    for subtask in subtasks:
        preferred = await _memory.get_best_provider(subtask.type)
        routing_map[subtask.id] = preferred or STATIC_ROUTING.get(subtask.type, "anthropic")
    return routing_map


def group_for_parallel(subtasks: list[SubTask]) -> list[list[str]]:
    """
    MVP: all subtasks run in a single parallel group.
    V2: dependency graph resolution (e.g. translation waits for writing output).
    """
    return [[t.id for t in subtasks]]


def estimate_cost(subtasks: list[SubTask], routing_map: dict[str, str]) -> float:
    return sum(
        COST_PER_TASK.get(routing_map.get(t.id, "anthropic"), 0.003)
        for t in subtasks
    )


def estimate_latency(subtasks: list[SubTask], parallel_groups: list[list[str]], routing_map: dict[str, str]) -> int:
    """
    Parallel groups run concurrently — total latency is the slowest task per group,
    summed across sequential groups.

    Uses the actual routing_map so that Perplexity tasks (5000ms) are correctly
    reflected in the estimate rather than always defaulting to Anthropic (3000ms).
    """
    if not parallel_groups:
        return 5000

    total = 0
    for group in parallel_groups:
        if not group:
            continue
        group_latency = max(
            LATENCY_PER_TASK.get(routing_map.get(tid, "anthropic"), 3000)
            for tid in group
        )
        total += group_latency
    return total


async def plan_execution(subtasks: list[SubTask]) -> ExecutionPlan:
    """Builds a full ExecutionPlan from classified subtasks."""
    routing_map = await route_subtasks(subtasks)
    parallel_groups = group_for_parallel(subtasks)

    return ExecutionPlan(
        workflow_id=subtasks[0].parent_workflow_id if subtasks else "",
        subtasks=subtasks,
        routing_map=routing_map,
        estimated_cost_usd=estimate_cost(subtasks, routing_map),
        estimated_latency_ms=estimate_latency(subtasks, parallel_groups, routing_map),
        parallel_groups=parallel_groups,
    )
