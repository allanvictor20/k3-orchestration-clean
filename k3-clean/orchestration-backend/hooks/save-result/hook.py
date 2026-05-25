"""
save-result hook — runs AFTER orchestration.
Use this to save results to external systems (Notion, Sheets, etc.)

context keys available:
  workflow_id    — the workflow ID
  final_output   — the final response text
  providers_used — list of providers that ran
  total_cost_usd — cost of this workflow
  session_id     — session ID if applicable
"""

TRIGGERS = ["after_orchestration"]


async def run(context: dict) -> dict:
    # Example: save to a file
    # with open(f"results/{context['workflow_id']}.txt", "w") as f:
    #     f.write(context.get("final_output", ""))
    return context
