import aiosqlite
from datetime import datetime

DB_PATH = "orchestration.db"


class PerformanceMemory:
    """
    Tracks provider performance per task type.
    Used by the router to prefer historically faster/more reliable providers.
    Requires at least 5 successful runs before overriding static routing.
    """

    async def record(
        self,
        provider: str,
        task_type: str,
        latency_ms: int,
        success: bool,
    ):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO provider_performance "
                "(provider, task_type, latency_ms, success, timestamp) VALUES (?, ?, ?, ?, ?)",
                (provider, task_type, latency_ms, int(success), datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def get_best_provider(self, task_type: str) -> str | None:
        """
        Returns the provider with the best average latency for this task type.
        Only considers the last 100 successful executions.
        Returns None if fewer than 5 data points exist (not enough to override static routing).
        """
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                SELECT provider, AVG(latency_ms) AS avg_lat, COUNT(*) AS cnt
                FROM (
                    SELECT provider, latency_ms FROM provider_performance
                    WHERE task_type = ? AND success = 1
                    ORDER BY timestamp DESC LIMIT 100
                )
                GROUP BY provider
                HAVING cnt >= 5
                ORDER BY avg_lat ASC
                LIMIT 1
                """,
                (task_type,),
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_stats(self, task_type: str | None = None) -> list[dict]:
        """Returns performance stats for display in the dashboard."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if task_type:
                cursor = await db.execute(
                    """
                    SELECT provider, task_type,
                           AVG(latency_ms) AS avg_latency_ms,
                           COUNT(*) AS total_runs,
                           SUM(success) AS successes
                    FROM provider_performance
                    WHERE task_type = ?
                    GROUP BY provider, task_type
                    ORDER BY avg_latency_ms ASC
                    """,
                    (task_type,),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT provider, task_type,
                           AVG(latency_ms) AS avg_latency_ms,
                           COUNT(*) AS total_runs,
                           SUM(success) AS successes
                    FROM provider_performance
                    GROUP BY provider, task_type
                    ORDER BY task_type, avg_latency_ms ASC
                    """
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
