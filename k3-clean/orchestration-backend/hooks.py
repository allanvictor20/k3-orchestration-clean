"""
hooks.py — Workflow Automation Hooks.

Hooks are Python scripts stored in the hooks/ folder.
Each hook is a folder containing a hook.py file with a run(context) function.

Hook triggers:
  before_orchestration  — runs before classification, can enrich the prompt
  after_orchestration   — runs after final response is produced
  on_session_start      — runs when a new session is created
  on_session_end        — runs when a session is archived
  on_provider_failure   — runs when a provider fails

Folder structure:
  hooks/
    enrich-context/
      hook.py          ← must define async def run(context: dict) -> dict
    save-result/
      hook.py
    send-notification/
      hook.py

The run(context) function:
  - Receives a context dict with relevant data for that trigger
  - Returns a dict (can include "prompt" key to override prompt for before_orchestration)
  - Errors are caught and logged — hooks never crash the main workflow
"""

from __future__ import annotations

import importlib.util
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HOOKS_DIR = Path(__file__).parent / "hooks"


# ---------------------------------------------------------------------------
# Hook discovery
# ---------------------------------------------------------------------------

def discover_hooks(trigger: str) -> list[Path]:
    """
    Returns paths to all hook.py files that apply to the given trigger.
    A hook applies if its hook.py defines the trigger in TRIGGERS list,
    or if no TRIGGERS list exists (applies to all triggers).
    """
    if not HOOKS_DIR.exists():
        return []

    applicable: list[Path] = []

    for hook_dir in sorted(HOOKS_DIR.iterdir()):
        hook_file = hook_dir / "hook.py"
        if not hook_file.exists():
            continue

        # Load the module temporarily to check TRIGGERS
        try:
            spec = importlib.util.spec_from_file_location(hook_dir.name, hook_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # Check TRIGGERS list if defined
            triggers = getattr(mod, "TRIGGERS", None)
            if triggers is None or trigger in triggers:
                applicable.append(hook_file)
        except Exception as exc:
            logger.warning("Could not inspect hook %s: %s", hook_dir.name, exc)

    return applicable


# ---------------------------------------------------------------------------
# Hook execution
# ---------------------------------------------------------------------------

async def run_hooks(trigger: str, context: dict) -> dict:
    """
    Discovers and runs all hooks for the given trigger.

    For 'before_orchestration': if a hook returns {"prompt": "..."}, the
    prompt in the context is updated and passed to subsequent hooks.

    Returns the (potentially modified) context dict.
    """
    hook_files = discover_hooks(trigger)

    if not hook_files:
        return context

    logger.info("Running %d hooks for trigger '%s'", len(hook_files), trigger)

    for hook_file in hook_files:
        hook_name = hook_file.parent.name
        start = time.monotonic()

        try:
            spec = importlib.util.spec_from_file_location(hook_name, hook_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "run"):
                logger.warning("Hook %s has no run() function — skipping", hook_name)
                continue

            result = mod.run(context)

            # Support both sync and async run()
            if hasattr(result, "__await__"):
                result = await result

            duration_ms = int((time.monotonic() - start) * 1000)

            if isinstance(result, dict):
                # Merge result back into context
                context.update(result)
                logger.info(
                    "Hook '%s' completed in %dms", hook_name, duration_ms
                )
            else:
                logger.warning(
                    "Hook '%s' returned non-dict result — ignoring", hook_name
                )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "Hook '%s' failed after %dms: %s", hook_name, duration_ms, exc
            )
            # Never let a hook crash the workflow — just continue

    return context


# ---------------------------------------------------------------------------
# Built-in hooks (created automatically in hooks/ folder)
# ---------------------------------------------------------------------------

def ensure_default_hooks():
    """Creates the default hook stubs if the hooks folder is empty."""
    HOOKS_DIR.mkdir(exist_ok=True)

    # Enrich-context hook
    enrich_dir = HOOKS_DIR / "enrich-context"
    enrich_dir.mkdir(exist_ok=True)
    enrich_hook = enrich_dir / "hook.py"
    if not enrich_hook.exists():
        enrich_hook.write_text('''\
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
      prompt         — the user\'s English prompt (after translation)
      session_id     — session ID if in a session
      workflow_id    — the workflow ID
      input_language — user\'s input language code
      output_language — user\'s desired output language code

    Return a dict. To modify the prompt, include {"prompt": new_prompt}.
    """
    # Example: append institution context to every prompt
    # context["prompt"] += "\\n\\nContext: User is at Makerere University, Uganda."
    return context
''')

    # Save-result hook
    save_dir = HOOKS_DIR / "save-result"
    save_dir.mkdir(exist_ok=True)
    save_hook = save_dir / "hook.py"
    if not save_hook.exists():
        save_hook.write_text('''\
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
    # with open(f"results/{context[\'workflow_id\']}.txt", "w") as f:
    #     f.write(context.get("final_output", ""))
    return context
''')

    # Send-notification hook
    notify_dir = HOOKS_DIR / "send-notification"
    notify_dir.mkdir(exist_ok=True)
    notify_hook = notify_dir / "hook.py"
    if not notify_hook.exists():
        notify_hook.write_text('''\
"""
send-notification hook — runs AFTER orchestration.
Use this to send emails, Slack messages, or other notifications
when a workflow completes.
"""

TRIGGERS = ["after_orchestration"]


async def run(context: dict) -> dict:
    # Example: print a notification (replace with real notification logic)
    # print(f"Workflow {context[\'workflow_id\']} completed!")
    return context
''')

    logger.info("Default hooks ensured in %s", HOOKS_DIR)
