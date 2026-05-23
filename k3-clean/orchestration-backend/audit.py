import aiosqlite
import json
from datetime import datetime

DB_PATH = "orchestration.db"


class AuditLogger:
    """
    Writes structured audit events to SQLite for every step of a workflow.
    Enables governance, replay, and debugging of orchestration runs.
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
    
    async def log_event(self, event_type: str, payload: dict = {}):
        await self._log(event_type, payload)

    async def _log(self, event_type: str, payload: dict):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO audit_log (workflow_id, event_type, payload, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (
                    self.workflow_id,
                    event_type,
                    json.dumps(payload, default=str),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()

    async def log_prompt(self, prompt: str):
        await self._log("prompt_received", {"prompt": prompt})

    async def log_classification(self, subtasks):
        await self._log(
            "classification_complete",
            {"subtasks": [s.model_dump() for s in subtasks]},
        )

    async def log_plan(self, plan):
        await self._log(
            "plan_created",
            {
                "routing_map": plan.routing_map,
                "parallel_groups": plan.parallel_groups,
                "estimated_cost_usd": plan.estimated_cost_usd,
                "estimated_latency_ms": plan.estimated_latency_ms,
            },
        )

    async def log_results(self, results):
        await self._log(
            "execution_complete",
            {
                "results": [r.model_dump() for r in results],
                "success_count": sum(1 for r in results if r.success),
                "failure_count": sum(1 for r in results if not r.success),
            },
        )

    async def log_final(self, response):
        await self._log(
            "merge_complete",
            {
                "workflow_id": response.workflow_id,
                "total_cost_usd": response.total_cost_usd,
                "total_latency_ms": response.total_latency_ms,
                "providers_used": response.providers_used,
                "output_length": len(response.final_output),
            },
        )

    async def log_error(self, error: str):
        await self._log("error", {"error": error})


async def get_audit_trail(workflow_id: str) -> list[dict]:
    """Retrieves the full audit trail for a given workflow."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT event_type, payload, timestamp FROM audit_log "
            "WHERE workflow_id = ? ORDER BY id ASC",
            (workflow_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "event_type": row["event_type"],
                "payload": json.loads(row["payload"]),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]
