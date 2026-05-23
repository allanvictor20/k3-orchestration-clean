import re
from models import SubTask


TASK_PATTERNS: dict[str, list[str]] = {
    "research": [
        r"\bresearch\b", r"\bfind out\b", r"\blook up\b",
        r"\bsearch for\b", r"\bwhat is\b", r"\bwho is\b",
        r"\blatest\b", r"\bcurrent\b", r"\bnews\b", r"\btrends\b",
    ],
    "coding": [
        r"\bcode\b", r"\bimplement\b", r"\bbuild\b",
        r"\bwrite a function\b", r"\bscript\b", r"\bapi\b",
        r"\bprogram\b", r"\bdebug\b", r"\bfix the\b",
    ],
    "reasoning": [
        r"\bstrategy\b", r"\bplan\b", r"\banalyse\b", r"\banalyze\b",
        r"\bevaluate\b", r"\bdecide\b", r"\badvise\b", r"\brecommend\b",
        r"\bcompare\b", r"\bpros and cons\b",
    ],
    "translation": [
        r"\btranslate\b", r"\bluganda\b", r"\bswahili\b",
        r"\bkirundi\b", r"\blocal language\b", r"\bacholi\b",
        r"\brunyankole\b", r"\bkinyarwanda\b",
    ],
    "writing": [
        r"\bwrite\b", r"\bdraft\b", r"\bsummarise\b", r"\bsummarize\b",
        r"\breport\b", r"\bdocument\b", r"\bessay\b", r"\bpresentation\b",
        r"\bemail\b", r"\bletter\b",
    ],
}


async def classify_task(prompt: str, workflow_id: str = "") -> list[SubTask]:
    """
    Decomposes a prompt into typed subtasks.

    MVP: keyword regex matching — fast, zero cost, no external call.
    V2: replace body with a Claude structured-output call for higher accuracy.
    """
    prompt_lower = prompt.lower()
    detected_types: list[str] = []

    for task_type, patterns in TASK_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, prompt_lower):
                detected_types.append(task_type)
                break

    # Always guarantee at least one subtask
    if not detected_types:
        detected_types = ["reasoning"]

    subtasks: list[SubTask] = []
    for i, task_type in enumerate(detected_types):
        subtasks.append(SubTask(
            parent_workflow_id=workflow_id,
            type=task_type,
            description=f"{task_type.title()} component of: {prompt}",
            priority=i + 1,
        ))

    return subtasks
