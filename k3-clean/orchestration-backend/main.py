from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import Optional

from database import init_db, save_workflow, complete_workflow, fail_workflow, get_workflow, list_workflows
from classifier import classify_task
from router import plan_execution
from executor import execute_plan
from merger import merge_results
from audit import AuditLogger, get_audit_trail
from memory import PerformanceMemory
from validator import validate_response
from models import (
    OrchestrationRequest, OrchestrationResponse,
    SessionCreate, SessionPromptRequest,
)
from providers.base import list_providers
from streaming import event_bus, make_stream_response, OrchestrationEvent
from workflow_state import WorkflowState
from language_middleware import prepare_prompt, translate_response_back, LANGUAGE_OPTIONS
from sessions import (
    create_session, get_session, list_sessions, archive_session,
    save_message, get_session_messages, build_context_prompt, auto_title_session,
)
from hooks import run_hooks, ensure_default_hooks
from mcp_client import init_mcp, mcp_registry

import providers  # noqa: F401 — triggers all register_provider() calls


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    ensure_default_hooks()
    init_mcp()
    yield


app = FastAPI(
    title="Maverix Orchestration Backend",
    description="Multi-agent AI orchestration for African institutions — with language support, sessions, hooks, and MCP tools",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_memory = PerformanceMemory()


# ===========================================================================
# Core orchestration (single request, no session)
# ===========================================================================

@app.post("/orchestrate", response_model=OrchestrationResponse)
async def orchestrate(request: OrchestrationRequest):
    """
    Main orchestration endpoint.

    1. Language middleware: detects/translates input → English
    2. Hook: before_orchestration (can enrich prompt)
    3. Classify → plan → execute in parallel → merge
    4. Hook: after_orchestration
    5. Language middleware: translates output → user's chosen language
    6. If session_id provided, saves to session history
    """

    # --- Language detection & translation IN ---
    lang_context = await prepare_prompt(
        request.prompt,
        input_language=request.input_language,
        output_language=request.output_language,
    )
    working_prompt = lang_context["english_prompt"]

    # --- Before-orchestration hook ---
    hook_context = {
        "prompt": working_prompt,
        "workflow_id": request.workflow_id,
        "session_id": request.session_id,
        "input_language": lang_context["resolved_input_language"],
        "output_language": lang_context["output_language"],
    }
    hook_context = await run_hooks("before_orchestration", hook_context)
    working_prompt = hook_context.get("prompt", working_prompt)

    # --- If in a session, inject conversation history ---
    if request.session_id:
        working_prompt = await build_context_prompt(request.session_id, working_prompt)

    state = WorkflowState.create(
        prompt=working_prompt,
        language=lang_context["resolved_input_language"],
        workflow_id=request.workflow_id,
    )
    audit = AuditLogger(request.workflow_id)
    await save_workflow(
        request.workflow_id,
        request.prompt,
        input_language=request.input_language,
        output_language=request.output_language,
        session_id=request.session_id,
    )

    try:
        await audit.log_prompt(request.prompt)

        # --- Classification ---
        state.mark_classifying()
        subtasks = await classify_task(working_prompt, workflow_id=request.workflow_id)
        await audit.log_classification(subtasks)

        # --- Planning ---
        plan = await plan_execution(subtasks)
        state.mark_planning(plan)
        await audit.log_plan(plan)

        for tid, provider in plan.routing_map.items():
            await event_bus.publish(request.workflow_id, OrchestrationEvent.PROVIDER_SELECTED, {
                "subtask_id": tid,
                "provider": provider,
            })

        # --- Execution ---
        state.mark_executing(subtasks, plan.routing_map)
        results = await execute_plan(plan, state=state)
        await audit.log_results(results)

        for result in results:
            task_type = next(
                (t.type for t in subtasks if t.id == result.subtask_id), "unknown"
            )
            await _memory.record(result.provider, task_type, result.latency_ms, result.success)

        # --- Merge ---
        state.mark_merging()
        await event_bus.publish(request.workflow_id, OrchestrationEvent.MERGE_STARTED, {})
        final = await merge_results(results, working_prompt, workflow_id=request.workflow_id)
        await audit.log_final(final)

        # --- Validate ---
        validation = validate_response(final)
        await audit.log_event("validation", validation)

        # --- Translate response back to user's language ---
        localised_output = await translate_response_back(final.final_output, lang_context)
        final.final_output = localised_output

        # --- Persist workflow ---
        result_dict = final.model_dump(mode="json")
        await complete_workflow(request.workflow_id, result_dict)

        state.mark_completed(
            final_output=final.final_output,
            cost=final.total_cost_usd,
            latency_ms=final.total_latency_ms,
            providers=final.providers_used,
        )

        # --- After-orchestration hook ---
        await run_hooks("after_orchestration", {
            "workflow_id": request.workflow_id,
            "session_id": request.session_id,
            "final_output": final.final_output,
            "providers_used": final.providers_used,
            "total_cost_usd": final.total_cost_usd,
            "total_latency_ms": final.total_latency_ms,
        })

        # --- Save to session if applicable ---
        if request.session_id:
            session = await get_session(request.session_id)
            if session:
                # Save user message
                await save_message(
                    request.session_id, "user", request.prompt,
                    input_language=request.input_language,
                    output_language=request.output_language,
                )
                # Save assistant response
                await save_message(
                    request.session_id, "assistant", final.final_output,
                    workflow_id=request.workflow_id,
                    input_language=request.input_language,
                    output_language=request.output_language,
                )
                # Auto-title session on first message
                if session.get("message_count", 0) == 0:
                    await auto_title_session(request.session_id, request.prompt)

        # --- SSE terminal event ---
        await event_bus.publish_terminal(
            request.workflow_id,
            OrchestrationEvent.WORKFLOW_COMPLETED,
            {
                "final_output_preview": final.final_output[:200],
                "total_cost_usd": final.total_cost_usd,
                "total_latency_ms": final.total_latency_ms,
                "providers_used": final.providers_used,
                "degraded": state.is_degraded,
                "input_language": lang_context["resolved_input_language"],
                "output_language": lang_context["output_language"],
            },
        )

        # Attach language info to response
        final.input_language = lang_context["resolved_input_language"]
        final.output_language = lang_context["output_language"]
        final.session_id = request.session_id

        return final

    except Exception as e:
        await audit.log_error(str(e))
        await fail_workflow(request.workflow_id, str(e))
        state.mark_failed(str(e))
        await event_bus.publish_terminal(
            request.workflow_id,
            OrchestrationEvent.WORKFLOW_FAILED,
            {"error": str(e)},
        )
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# SSE streaming
# ===========================================================================

@app.get("/orchestrate/stream/{workflow_id}")
async def orchestrate_stream(workflow_id: str, request: Request):
    """Real-time SSE stream for workflow progress."""
    return make_stream_response(workflow_id, request)


# ===========================================================================
# Sessions
# ===========================================================================

@app.post("/sessions")
async def create_new_session(body: SessionCreate):
    """Create a new conversation session."""
    session = await create_session(
        title=body.title,
        input_language=body.input_language,
        output_language=body.output_language,
    )
    return session


@app.get("/sessions")
async def list_all_sessions(limit: int = 20):
    """List active sessions."""
    return await list_sessions(limit=limit)


@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """Get a session with its message history."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_session_messages(session_id)
    return {**session, "messages": messages}


@app.post("/sessions/{session_id}/prompt")
async def session_prompt(session_id: str, body: SessionPromptRequest):
    """
    Send a prompt within an existing session.
    Language settings default to session defaults but can be overridden per message.
    """
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    import uuid
    request = OrchestrationRequest(
        workflow_id=str(uuid.uuid4()),
        prompt=body.prompt,
        input_language=body.input_language or session["input_language"],
        output_language=body.output_language or session["output_language"],
        session_id=session_id,
    )
    return await orchestrate(request)


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Archive a session."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await run_hooks("on_session_end", {"session_id": session_id})
    await archive_session(session_id)
    return {"archived": True, "session_id": session_id}


@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, limit: int = 50):
    """Get message history for a session."""
    return await get_session_messages(session_id, limit=limit)


# ===========================================================================
# Language support
# ===========================================================================

@app.get("/languages")
async def get_supported_languages():
    """Returns all supported languages for the UI language selector."""
    return {"languages": LANGUAGE_OPTIONS}


# ===========================================================================
# MCP tools
# ===========================================================================

@app.get("/mcp/tools")
async def list_mcp_tools():
    """Lists all available MCP tools across all connected servers."""
    return {"tools": mcp_registry.list_all_tools()}


@app.post("/mcp/tools/{server_name}/{tool_name}")
async def call_mcp_tool(server_name: str, tool_name: str, arguments: dict):
    """Manually call an MCP tool (for testing)."""
    result = await mcp_registry.call_tool(server_name, tool_name, arguments)
    if result is None:
        raise HTTPException(status_code=500, detail="Tool call failed")
    return {"result": result}


# ===========================================================================
# Existing endpoints (unchanged)
# ===========================================================================

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "providers_registered": list_providers(),
        "mcp_tools": len(mcp_registry.list_all_tools()),
    }


@app.get("/workflows/{workflow_id}")
async def get_workflow_detail(workflow_id: str):
    workflow = await get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@app.get("/workflows/{workflow_id}/audit")
async def get_workflow_audit(workflow_id: str):
    trail = await get_audit_trail(workflow_id)
    if not trail:
        raise HTTPException(status_code=404, detail="No audit trail found")
    return {"workflow_id": workflow_id, "events": trail}


@app.get("/workflows")
async def list_workflows_endpoint(limit: int = 20):
    return await list_workflows(limit=limit)


@app.get("/providers/status")
async def provider_status():
    load_errors = providers.get_load_errors()
    return {
        "registered": list_providers(),
        "load_errors": load_errors,
    }


@app.get("/providers/performance")
async def provider_performance(task_type: str | None = None):
    stats = await _memory.get_stats(task_type=task_type)
    return {"stats": stats}
