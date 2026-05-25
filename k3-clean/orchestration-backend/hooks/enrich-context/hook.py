"""
enrich-context hook — runs BEFORE orchestration.
Add extra context to the prompt before it is classified and routed.

Edit this file to inject institution-specific context,
user preferences, or external data into every prompt.
"""

TRIGGERS = ["before_orchestration"]


async def run(context: dict) -> dict:
    """
    context keys available:
      prompt         — the user's English prompt (after translation)
      session_id     — session ID if in a session
      workflow_id    — the workflow ID
      input_language — user's input language code
      output_language — user's desired output language code

    Return a dict. To modify the prompt, include {"prompt": new_prompt}.
    """
    # Example: append institution context to every prompt
    # context["prompt"] += "\n\nContext: User is at Makerere University, Uganda."
    return context
