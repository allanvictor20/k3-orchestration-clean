import aiosqlite
import json
from datetime import datetime

DB_PATH = "orchestration.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Existing tables
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                input_language TEXT DEFAULT 'en',
                output_language TEXT DEFAULT 'en',
                session_id TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS provider_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                task_type TEXT NOT NULL,
                latency_ms INTEGER,
                success INTEGER,
                timestamp TEXT NOT NULL
            )
        """)
        # Session tables
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT 'New Session',
                input_language TEXT NOT NULL DEFAULT 'en',
                output_language TEXT NOT NULL DEFAULT 'en',
                created_at TEXT NOT NULL,
                last_active TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS session_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                workflow_id TEXT,
                input_language TEXT DEFAULT 'en',
                output_language TEXT DEFAULT 'en',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        await db.commit()


async def save_workflow(
    workflow_id: str,
    prompt: str,
    input_language: str = "en",
    output_language: str = "en",
    session_id: str = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO workflows
               (id, prompt, status, input_language, output_language, session_id, created_at)
               VALUES (?, ?, 'running', ?, ?, ?, ?)""",
            (workflow_id, prompt, input_language, output_language,
             session_id, datetime.utcnow().isoformat()),
        )
        await db.commit()


async def complete_workflow(workflow_id: str, result: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE workflows SET status='completed', result=?, completed_at=? WHERE id=?",
            (json.dumps(result), datetime.utcnow().isoformat(), workflow_id),
        )
        await db.commit()


async def fail_workflow(workflow_id: str, error: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE workflows SET status='failed', result=?, completed_at=? WHERE id=?",
            (json.dumps({"error": error}), datetime.utcnow().isoformat(), workflow_id),
        )
        await db.commit()


async def get_workflow(workflow_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data = dict(row)
        if data.get("result"):
            data["result"] = json.loads(data["result"])
        return data


async def list_workflows(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT id, prompt, status, input_language, output_language,
                      session_id, created_at, completed_at
               FROM workflows
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
