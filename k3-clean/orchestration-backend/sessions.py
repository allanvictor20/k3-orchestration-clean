"""
sessions.py — Persistent Session Memory.

Provides:
  - Session creation and lifecycle management
  - Message history loading and saving
  - Context injection: prepends conversation history to new prompts
    so AI models have full context across multiple exchanges
  - Session listing, retrieval, and archival
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

import aiosqlite

DB_PATH = "orchestration.db"
logger = logging.getLogger(__name__)

# How many past messages to inject as context (most recent N exchanges)
MAX_CONTEXT_MESSAGES = 6


# ---------------------------------------------------------------------------
# Database setup (called from init_db in database.py)
# ---------------------------------------------------------------------------

async def init_sessions_db():
    """Creates session tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
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
    logger.info("Session tables initialised")


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------

async def create_session(
    title: Optional[str] = None,
    input_language: str = "en",
    output_language: str = "en",
) -> dict:
    """Creates a new session and returns it as a dict."""
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    resolved_title = title or "New Session"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO sessions
               (id, title, input_language, output_language, created_at, last_active, status)
               VALUES (?, ?, ?, ?, ?, ?, 'active')""",
            (session_id, resolved_title, input_language, output_language, now, now),
        )
        await db.commit()

    logger.info("Created session %s", session_id)
    return {
        "id": session_id,
        "title": resolved_title,
        "input_language": input_language,
        "output_language": output_language,
        "created_at": now,
        "last_active": now,
        "status": "active",
        "message_count": 0,
    }


async def get_session(session_id: str) -> Optional[dict]:
    """Returns a session dict, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        session = dict(row)

        # Count messages
        count_cursor = await db.execute(
            "SELECT COUNT(*) FROM session_messages WHERE session_id = ?", (session_id,)
        )
        count_row = await count_cursor.fetchone()
        session["message_count"] = count_row[0] if count_row else 0
        return session


async def list_sessions(limit: int = 20, status: str = "active") -> list[dict]:
    """Lists sessions ordered by last_active descending."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT s.*, COUNT(m.id) as message_count
               FROM sessions s
               LEFT JOIN session_messages m ON m.session_id = s.id
               WHERE s.status = ?
               GROUP BY s.id
               ORDER BY s.last_active DESC
               LIMIT ?""",
            (status, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def archive_session(session_id: str) -> bool:
    """Archives a session (soft delete)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET status = 'archived' WHERE id = ?", (session_id,)
        )
        await db.commit()
    logger.info("Archived session %s", session_id)
    return True


async def update_session_title(session_id: str, title: str) -> bool:
    """Updates the session title."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET title = ? WHERE id = ?", (title, session_id)
        )
        await db.commit()
    return True


# ---------------------------------------------------------------------------
# Message management
# ---------------------------------------------------------------------------

async def save_message(
    session_id: str,
    role: str,
    content: str,
    workflow_id: Optional[str] = None,
    input_language: str = "en",
    output_language: str = "en",
) -> str:
    """Saves a message and returns its ID."""
    message_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO session_messages
               (id, session_id, role, content, workflow_id, input_language, output_language, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (message_id, session_id, role, content, workflow_id,
             input_language, output_language, now),
        )
        # Update last_active on the session
        await db.execute(
            "UPDATE sessions SET last_active = ? WHERE id = ?", (now, session_id)
        )
        await db.commit()

    return message_id


async def get_session_messages(session_id: str, limit: int = 50) -> list[dict]:
    """Returns all messages for a session in chronological order."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM session_messages
               WHERE session_id = ?
               ORDER BY created_at ASC
               LIMIT ?""",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------

async def build_context_prompt(session_id: str, new_prompt: str) -> str:
    """
    Loads the most recent N message pairs from the session and prepends
    them to the new prompt so the AI has full conversation context.

    Returns the enriched prompt string.
    """
    messages = await get_session_messages(session_id, limit=MAX_CONTEXT_MESSAGES * 2)

    if not messages:
        return new_prompt

    # Build a readable conversation history block
    history_lines = []
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role_label}: {msg['content']}")

    history_block = "\n".join(history_lines)

    enriched = (
        f"[Conversation history]\n"
        f"{history_block}\n\n"
        f"[New message]\n"
        f"{new_prompt}"
    )

    logger.info(
        "Injected %d history messages into prompt for session %s",
        len(messages), session_id
    )
    return enriched


async def auto_title_session(session_id: str, first_prompt: str) -> None:
    """
    Sets a descriptive title based on the first user message.
    Truncates to 60 chars.
    """
    title = first_prompt.strip()[:60]
    if len(first_prompt.strip()) > 60:
        title += "…"
    await update_session_title(session_id, title)
