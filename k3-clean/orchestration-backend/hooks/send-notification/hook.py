"""
send-notification hook — runs AFTER orchestration.
Use this to send emails, Slack messages, or other notifications
when a workflow completes.
"""

TRIGGERS = ["after_orchestration"]


async def run(context: dict) -> dict:
    # Example: print a notification (replace with real notification logic)
    # print(f"Workflow {context['workflow_id']} completed!")
    return context
