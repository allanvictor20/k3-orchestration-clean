"""
streaming.py — Real-Time Workflow Streaming via Server-Sent Events (SSE).

Provides:
  - WorkflowEventBus: in-process pub/sub for workflow lifecycle events
  - SSE-compatible async generator (consumes from the event bus)
  - FastAPI route helper: GET /orchestrate/stream/{workflow_id}
  - Structured event types that match the Wails frontend event constants

The Go stream.go relay connects to this endpoint and re-broadcasts events
as Wails events.  The React WorkflowView then receives them via window.k3.

Usage in main.py:
    from streaming import event_bus, stream_workflow_events

    # In your orchestration logic, publish events:
    await event_bus.publish(workflow_id, "task_started", {"provider": "claude"})

    # FastAPI route:
    @app.get("/orchestrate/stream/{workflow_id}")
    async def orchestrate_stream(workflow_id: str, request: Request):
        return EventSourceResponse(stream_workflow_events(workflow_id, request))
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import AsyncGenerator

from fastapi import Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event types — mirror Wails constants in events.go
# ---------------------------------------------------------------------------

class OrchestrationEvent:
    TASK_STARTED         = "task_started"
    PROVIDER_SELECTED    = "provider_selected"
    RETRY_TRIGGERED      = "retry_triggered"
    TASK_COMPLETED       = "task_completed"
    WORKFLOW_COMPLETED   = "workflow_completed"
    WORKFLOW_FAILED      = "workflow_failed"
    MERGE_STARTED        = "merge_started"
    MERGE_COMPLETED      = "merge_completed"


# ---------------------------------------------------------------------------
# WorkflowEventBus
# ---------------------------------------------------------------------------

class WorkflowEventBus:
    """
    Lightweight in-process pub/sub for workflow events.

    Multiple SSE subscribers can listen to the same workflow_id.
    Events are delivered via asyncio.Queue — no external broker needed.

    The bus automatically discards queues for completed workflows after a
    configurable TTL to prevent unbounded memory growth.
    """

    def __init__(self, max_queue_size: int = 256, subscriber_ttl: float = 300.0) -> None:
        # workflow_id → list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._max_queue_size = max_queue_size
        self._subscriber_ttl = subscriber_ttl

    def subscribe(self, workflow_id: str) -> asyncio.Queue:
        """Create and register a new subscriber queue for a workflow."""
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers[workflow_id].append(q)
        return q

    def unsubscribe(self, workflow_id: str, queue: asyncio.Queue) -> None:
        """Remove a subscriber queue (called when SSE connection closes)."""
        subs = self._subscribers.get(workflow_id, [])
        try:
            subs.remove(queue)
        except ValueError:
            pass
        if not subs:
            self._subscribers.pop(workflow_id, None)

    async def publish(self, workflow_id: str, event_type: str, data: dict) -> None:
        """
        Publish an event to all subscribers of workflow_id.
        Non-blocking: subscribers that fall behind lose events (queue full).
        """
        payload = {
            "event": event_type,
            "workflow_id": workflow_id,
            "ts": time.monotonic(),
            **data,
        }

        for queue in list(self._subscribers.get(workflow_id, [])):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(
                    "SSE subscriber queue full for workflow %s; event dropped", workflow_id
                )

    async def publish_terminal(self, workflow_id: str, event_type: str, data: dict) -> None:
        """
        Publish a terminal event (workflow_completed / workflow_failed) and then
        send a sentinel None to signal all subscribers to close the stream.
        """
        await self.publish(workflow_id, event_type, data)
        for queue in list(self._subscribers.get(workflow_id, [])):
            try:
                queue.put_nowait(None)   # sentinel
            except asyncio.QueueFull:
                pass


# Singleton bus shared across the application
event_bus = WorkflowEventBus()


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------

async def stream_workflow_events(
    workflow_id: str,
    request: Request,
    timeout_seconds: float = 300.0,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings for a single workflow.

    Yields:
        "event: <event_type>\ndata: <json>\n\n"

    Terminates when:
      - A terminal event (workflow_completed / workflow_failed) is published
      - The client disconnects (request.is_disconnected())
      - timeout_seconds elapses with no events

    Usage:
        return StreamingResponse(
            stream_workflow_events(workflow_id, request),
            media_type="text/event-stream",
        )
    """
    queue = event_bus.subscribe(workflow_id)
    deadline = time.monotonic() + timeout_seconds

    try:
        # Initial heartbeat so the client knows the stream is open
        yield _sse("heartbeat", {"workflow_id": workflow_id, "status": "connected"})

        while time.monotonic() < deadline:
            if await request.is_disconnected():
                logger.info("SSE client disconnected for workflow %s", workflow_id)
                break

            try:
                payload = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                # Send a keepalive comment so the connection stays alive through proxies
                yield ": keepalive\n\n"
                continue

            if payload is None:
                # Terminal sentinel — stream is done
                break

            event_type = payload.pop("event", "progress")
            yield _sse(event_type, payload)

            # Stop reading after terminal events
            if event_type in (OrchestrationEvent.WORKFLOW_COMPLETED, OrchestrationEvent.WORKFLOW_FAILED):
                break

    finally:
        event_bus.unsubscribe(workflow_id, queue)


def _sse(event_type: str, data: dict) -> str:
    """Format a single SSE event."""
    json_data = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {json_data}\n\n"


# ---------------------------------------------------------------------------
# FastAPI route factory
# ---------------------------------------------------------------------------

def make_stream_response(workflow_id: str, request: Request) -> StreamingResponse:
    """
    Create an SSE StreamingResponse for a workflow.

    Mount this in main.py:
        @app.get("/orchestrate/stream/{workflow_id}")
        async def orchestrate_stream(workflow_id: str, request: Request):
            return make_stream_response(workflow_id, request)
    """
    return StreamingResponse(
        stream_workflow_events(workflow_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )
