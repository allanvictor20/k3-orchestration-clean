from dotenv import load_dotenv
load_dotenv()
import time
from models import AgentResult, OrchestrationResponse
from providers.anthropic import AnthropicProvider


async def merge_results(
    results: list[AgentResult],
    original_prompt: str,
    workflow_id: str = "",
) -> OrchestrationResponse:
    """
    Uses Claude to synthesise all agent outputs into one coherent response.
    Failed subtasks are noted but do not block the merge.
    workflow_id is passed explicitly to avoid the fragile split() reconstruction.
    """
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    if not successful:
        return OrchestrationResponse(
            workflow_id=workflow_id,
            final_output=(
                "All subtasks failed. Please check your provider API keys "
                "and ensure the .env file is configured correctly."
            ),
            subtask_results=results,
            total_cost_usd=0.0,
            total_latency_ms=0,
            providers_used=[],
        )

    # Build synthesis prompt
    outputs_section = "\n\n".join([
        f"[{r.provider.upper()} — task: {r.subtask_id[:8]}]\n{r.output}"
        for r in successful
    ])

    failed_note = ""
    if failed:
        failed_note = (
            f"\n\nNote: {len(failed)} subtask(s) failed and were excluded from synthesis."
        )

    synthesis_prompt = f"""You are synthesising multiple AI outputs into one unified response.

Original user request:
{original_prompt}

Outputs from specialised agents:
{outputs_section}{failed_note}

Instructions:
- Combine these outputs into one coherent, well-structured response
- Resolve any contradictions by noting them explicitly
- Remove redundancy
- Preserve all important information
- Write in clear, professional English
- Do not mention internal agent names or the orchestration process

Unified response:"""

    provider = AnthropicProvider()
    start = time.monotonic()
    final_text, tokens = await provider.complete(synthesis_prompt, max_tokens=2000)
    merge_latency = int((time.monotonic() - start) * 1000)

    total_cost = sum(r.cost_usd for r in results) + provider.estimate_cost(tokens)
    total_latency = (max(r.latency_ms for r in results) if results else 0) + merge_latency

    return OrchestrationResponse(
        workflow_id=workflow_id,
        final_output=final_text,
        subtask_results=results,
        total_cost_usd=round(total_cost, 6),
        total_latency_ms=total_latency,
        providers_used=list({r.provider for r in successful}),
    )
