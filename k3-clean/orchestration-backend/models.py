from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class OrchestrationRequest(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    input_language: str = "en"    # language the user is typing in
    output_language: str = "en"   # language they want the answer in
    session_id: Optional[str] = None   # if part of a session
    context_path: Optional[str] = None


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_workflow_id: str
    type: str
    description: str
    priority: int = 1
    assigned_provider: Optional[str] = None


class ExecutionPlan(BaseModel):
    workflow_id: str
    subtasks: list[SubTask]
    routing_map: dict[str, str]
    estimated_cost_usd: float
    estimated_latency_ms: int
    parallel_groups: list[list[str]]


class AgentResult(BaseModel):
    subtask_id: str
    provider: str
    output: str
    latency_ms: int
    token_usage: int
    cost_usd: float
    success: bool
    error: Optional[str] = None


class OrchestrationResponse(BaseModel):
    workflow_id: str
    final_output: str
    subtask_results: list[AgentResult]
    total_cost_usd: float
    total_latency_ms: int
    providers_used: list[str]
    input_language: str = "en"
    output_language: str = "en"
    session_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Session models
# ---------------------------------------------------------------------------

class SessionCreate(BaseModel):
    title: Optional[str] = None
    input_language: str = "en"
    output_language: str = "en"


class SessionMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str           # "user" | "assistant"
    content: str
    workflow_id: Optional[str] = None
    input_language: str = "en"
    output_language: str = "en"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Session"
    input_language: str = "en"
    output_language: str = "en"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)
    status: str = "active"
    message_count: int = 0


class SessionPromptRequest(BaseModel):
    prompt: str
    input_language: Optional[str] = None    # overrides session default
    output_language: Optional[str] = None   # overrides session default


# ---------------------------------------------------------------------------
# Hook models
# ---------------------------------------------------------------------------

class HookResult(BaseModel):
    hook_name: str
    trigger: str
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
