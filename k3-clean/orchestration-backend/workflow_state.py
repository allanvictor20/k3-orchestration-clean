"""
workflow_state.py — Centralized, canonical orchestration state object.

Every module that needs to read or update workflow progress should import
WorkflowState from here rather than building its own ad-hoc dictionaries.

Design goals:
- Single source of truth for a workflow's lifecycle
- Immutable workflow_id and prompt (set at creation)
- Thread-safe field updates via dataclass replace semantics
- Serialisable to dict / JSON for audit storage and Wails event payloads
- Supports partial results (some subtasks may fail while others succeed)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from models import SubTask, AgentResult, ExecutionPlan


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkflowStatus(str, Enum):
    """High-level lifecycle state of a workflow."""
    PENDING     = "pending"      # Just created, not yet classified
    CLASSIFYING = "classifying"  # Classifier is running
    PLANNING    = "planning"     # Router is building the execution plan
    EXECUTING   = "executing"    # Subtasks are running
    MERGING     = "merging"      # Merger is synthesising results
    COMPLETED   = "completed"    # Final output ready
    FAILED      = "failed"       # Unrecoverable failure


class SubtaskStatus(str, Enum):
    """Per-subtask execution state."""
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCEEDED = "succeeded"
    FAILED    = "failed"
    RETRYING  = "retrying"
    SKIPPED   = "skipped"   # Provider unavailable, subtask skipped in degraded mode


# ---------------------------------------------------------------------------
# Per-subtask tracking record
# ---------------------------------------------------------------------------

@dataclass
class SubtaskState:
    subtask_id: str
    description: str
    task_type: str
    assigned_provider: str
    status: SubtaskStatus = SubtaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[AgentResult] = None
    started_at: Optional[float] = None   # time.monotonic() timestamp
    completed_at: Optional[float] = None
    last_error: Optional[str] = None

    @property
    def latency_ms(self) -> Optional[int]:
        if self.started_at is not None and self.completed_at is not None:
            return int((self.completed_at - self.started_at) * 1000)
        return None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["latency_ms"] = self.latency_ms
        return d


# ---------------------------------------------------------------------------
# Main workflow state
# ---------------------------------------------------------------------------

@dataclass
class WorkflowState:
    """
    Canonical runtime state for a single orchestration workflow.

    Lifecycle:
        WorkflowState.create(prompt) → classifying → planning → executing
            → merging → completed | failed
    """

    # Identity (immutable after creation)
    workflow_id: str
    prompt: str
    language: str = "en"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Lifecycle
    status: WorkflowStatus = WorkflowStatus.PENDING
    status_detail: Optional[str] = None   # Human-readable status message

    # Subtask tracking
    subtasks: list[SubtaskState] = field(default_factory=list)

    # Execution results
    raw_results: list[AgentResult] = field(default_factory=list)
    final_output: Optional[str] = None

    # Metrics
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    providers_used: list[str] = field(default_factory=list)

    # Audit trail (list of {"step": str, "ts": float, "data": dict})
    audit_trail: list[dict] = field(default_factory=list)

    # Timing
    _start_time: float = field(default_factory=time.monotonic, repr=False)

    # ---------------------------------------------------------------------------
    # Factory
    # ---------------------------------------------------------------------------

    @classmethod
    def create(cls, prompt: str, language: str = "en", workflow_id: Optional[str] = None) -> "WorkflowState":
        """Create a fresh workflow state for a new orchestration request."""
        return cls(
            workflow_id=workflow_id or str(uuid.uuid4()),
            prompt=prompt,
            language=language,
        )

    # ---------------------------------------------------------------------------
    # Status transitions
    # ---------------------------------------------------------------------------

    def transition(self, new_status: WorkflowStatus, detail: Optional[str] = None) -> None:
        self.status = new_status
        self.status_detail = detail
        self._audit("status_transition", {"status": new_status.value, "detail": detail})

    def mark_classifying(self) -> None:
        self.transition(WorkflowStatus.CLASSIFYING, "Decomposing prompt into subtasks")

    def mark_planning(self, plan: ExecutionPlan) -> None:
        self.transition(WorkflowStatus.PLANNING, "Building execution plan")
        self._audit("plan_ready", {
            "subtask_count": len(plan.subtasks),
            "routing_map": plan.routing_map,
            "estimated_cost_usd": plan.estimated_cost_usd,
            "estimated_latency_ms": plan.estimated_latency_ms,
        })

    def mark_executing(self, subtasks: list[SubTask], routing_map: dict[str, str]) -> None:
        self.transition(WorkflowStatus.EXECUTING, "Running subtasks across providers")
        self.subtasks = [
            SubtaskState(
                subtask_id=t.id,
                description=t.description,
                task_type=t.type,
                assigned_provider=routing_map.get(t.id, "anthropic"),
            )
            for t in subtasks
        ]

    def mark_merging(self) -> None:
        self.transition(WorkflowStatus.MERGING, "Synthesising provider outputs")

    def mark_completed(self, final_output: str, cost: float, latency_ms: int, providers: list[str]) -> None:
        self.final_output = final_output
        self.total_cost_usd = cost
        self.total_latency_ms = latency_ms
        self.providers_used = providers
        self.transition(WorkflowStatus.COMPLETED, "Orchestration complete")

    def mark_failed(self, reason: str) -> None:
        self.transition(WorkflowStatus.FAILED, reason)

    # ---------------------------------------------------------------------------
    # Subtask helpers
    # ---------------------------------------------------------------------------

    def get_subtask(self, subtask_id: str) -> Optional[SubtaskState]:
        for s in self.subtasks:
            if s.subtask_id == subtask_id:
                return s
        return None

    def subtask_started(self, subtask_id: str, provider: str) -> None:
        s = self.get_subtask(subtask_id)
        if s:
            s.status = SubtaskStatus.RUNNING
            s.assigned_provider = provider
            s.started_at = time.monotonic()
            self._audit("subtask_started", {"subtask_id": subtask_id, "provider": provider})

    def subtask_succeeded(self, result: AgentResult) -> None:
        s = self.get_subtask(result.subtask_id)
        if s:
            s.status = SubtaskStatus.SUCCEEDED
            s.result = result
            s.completed_at = time.monotonic()
            self.raw_results.append(result)
            self._audit("subtask_succeeded", {
                "subtask_id": result.subtask_id,
                "provider": result.provider,
                "latency_ms": result.latency_ms,
            })

    def subtask_failed(self, subtask_id: str, error: str, retrying: bool = False) -> None:
        s = self.get_subtask(subtask_id)
        if s:
            s.status = SubtaskStatus.RETRYING if retrying else SubtaskStatus.FAILED
            s.last_error = error
            s.completed_at = time.monotonic()
            if retrying:
                s.retry_count += 1
            self._audit("subtask_failed", {
                "subtask_id": subtask_id,
                "error": error,
                "retrying": retrying,
                "retry_count": s.retry_count if s else 0,
            })

    def subtask_skipped(self, subtask_id: str, reason: str) -> None:
        s = self.get_subtask(subtask_id)
        if s:
            s.status = SubtaskStatus.SKIPPED
            s.last_error = reason
            self._audit("subtask_skipped", {"subtask_id": subtask_id, "reason": reason})

    # ---------------------------------------------------------------------------
    # Serialisation
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise for audit storage, API responses, and Wails event payloads."""
        return {
            "workflow_id": self.workflow_id,
            "prompt": self.prompt,
            "language": self.language,
            "created_at": self.created_at,
            "status": self.status.value,
            "status_detail": self.status_detail,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "final_output": self.final_output,
            "total_cost_usd": self.total_cost_usd,
            "total_latency_ms": self.total_latency_ms,
            "providers_used": self.providers_used,
            "audit_trail": self.audit_trail,
        }

    @property
    def success_count(self) -> int:
        return sum(1 for s in self.subtasks if s.status == SubtaskStatus.SUCCEEDED)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.subtasks if s.status == SubtaskStatus.FAILED)

    @property
    def is_degraded(self) -> bool:
        """True if at least one subtask failed but at least one succeeded."""
        return self.failed_count > 0 and self.success_count > 0

    # ---------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------

    def _audit(self, step: str, data: dict) -> None:
        self.audit_trail.append({
            "step": step,
            "ts": time.monotonic() - self._start_time,
            "data": data,
        })
