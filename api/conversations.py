"""Conversation API - Container Orchestrated Agent Execution.

This module handles conversation requests by dispatching them to
per-user Docker containers that run complete Hermes Agent instances.

Architecture:
- User logs in → Container created/restarted
- User sends message → Message dispatched to container
- Container runs Hermes Agent → Returns response
- Response streamed back to user

Data flow:
┌─────────────────────────────────────────────────────┐
│  User Browser                                        │
│     ↓ HTTP POST /api/v1/conversations/send          │
│  Host API Server                                     │
│     ↓ get_or_create_user_container(user_id)         │
│  User Container                                      │
│     ↓ execute_agent(message, session_id)            │
│  Hermes Agent (in container)                         │
│     ↓ Direct LLM API call (API Key from mounted .env)│
│  LLM Provider                                        │
│     ↓ Returns LLM response                           │
│  User Container → Host API Server → User Browser    │
└─────────────────────────────────────────────────────┘
"""

import json
import logging
import queue
import threading
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from hermes_state import SessionDB, UserDataDB
from hermes_user_context import user_id_var
from api.deps import get_current_user, get_user_db
from api.user_containers import get_or_create_user_container

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # None = new session
    file_ids: Optional[List[str]] = []  # Files attached to message
    skill_id: Optional[str] = None  # Skill to use


class SessionSummary(BaseModel):
    id: str
    title: Optional[str]
    started_at: float
    message_count: int


class MessageItem(BaseModel):
    role: str
    content: Optional[str]
    timestamp: float


class UpdateTitleRequest(BaseModel):
    title: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session_db() -> SessionDB:
    """Get session database (for metadata tracking on host)."""
    from hermes_constants import get_hermes_home
    return SessionDB(get_hermes_home() / "state.db")


def _sync_private_skills_to_container(user_id: str, container, db: UserDataDB):
    """Sync user's private skills to container.

    Skills are stored in the database and need to be written to
    the container's skill directory.
    """
    skills = db.list_skills(owner_id=user_id)
    for skill in skills:
        skill_id = skill["id"]
        full_skill = db.get_skill(skill_id)
        if full_skill and full_skill.get("visibility") == "private":
            # Write skill content to container's skill directory
            skill_content = full_skill.get("skill_content", "")
            skill_name = full_skill.get("name", skill_id)

            # Create skill directory and file
            skill_dir = f"/root/.hermes/skills/private/{skill_id}"
            container.execute_command(f"mkdir -p {skill_dir}")

            # Write SKILL.md
            skill_file = f"{skill_dir}/SKILL.md"
            # Use heredoc to write content
            escaped_content = skill_content.replace("'", "'\\''")
            container.execute_command(f"cat > {skill_file} << 'SKILL_EOF'\n{skill_content}\nSKILL_EOF")


# ── Endpoints ───────────────────────────────────────────────────────────────────

@router.post("/send")
def send_message(
    req: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Send a message and get response from containerized agent.

    The agent runs in a Docker container with user-specific data isolation.
    """
    user_id = current_user["id"]

    # Get or create user container
    try:
        container = get_or_create_user_container(user_id)
    except Exception as e:
        logger.error(f"Failed to get container for user {user_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to create user environment: {e}"
        )

    session_id = req.session_id or str(uuid.uuid4())

    # Sync private skills to container
    try:
        _sync_private_skills_to_container(user_id, container, db)
    except Exception as e:
        logger.warning(f"Failed to sync skills: {e}")

    # Execute agent in container
    result_queue: queue.Queue = queue.Queue()

    def run_agent_thread():
        """Run agent in container."""
        user_id_var.set(user_id)
        try:
            # Container reads config.yaml and .env from mounted /root/.hermes/
            result = container.execute_agent(
                message=req.message,
                session_id=session_id,
                skill_id=req.skill_id,
                timeout=300,
            )
            result_queue.put(result)

            # Auto-title for new session
            if not req.session_id and req.message:
                try:
                    title = req.message.strip().replace("\n", " ")[:60]
                    if len(req.message.strip()) > 60:
                        title = title.rstrip() + "..."

                    # Set title in container's session DB
                    container.execute_command(
                        f"cd /root/.hermes && sqlite3 sessions.db "
                        f"'UPDATE sessions SET title=\"{title}\" WHERE id=\"{session_id}\"'"
                    )
                except Exception as e:
                    logger.warning(f"Failed to set title: {e}")

        except Exception as e:
            import traceback
            result_queue.put({
                "success": False,
                "error": f"{str(e)}\n{traceback.format_exc()}",
            })

    def event_stream():
        """SSE generator."""
        thread = threading.Thread(target=run_agent_thread)
        thread.start()

        try:
            # Wait for result (with timeout)
            result = result_queue.get(timeout=300)

            if result.get("success"):
                yield f"data: {json.dumps({'type': 'done', 'content': result.get('content'), 'session_id': session_id})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'detail': result.get('error')})}\n\n"
        except queue.Empty:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Response timeout'})}\n\n"
        finally:
            thread.join(timeout=1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("", response_model=List[SessionSummary])
def list_sessions(
    current_user: dict = Depends(get_current_user),
):
    """List user's conversation sessions."""
    user_id = current_user["id"]

    # Get container to query sessions from container's DB
    try:
        container = get_or_create_user_container(user_id)
        result = container.execute_command(
            "cd /root/.hermes && sqlite3 sessions.db "
            "'SELECT id, title, started_at, message_count FROM sessions "
            "WHERE source=\"api\" ORDER BY started_at DESC LIMIT 50'"
        )

        # Parse result
        sessions = []
        for line in result.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 4:
                    sessions.append({
                        "id": parts[0],
                        "title": parts[1] if parts[1] else None,
                        "started_at": float(parts[2]) if parts[2] else 0,
                        "message_count": int(parts[3]) if parts[3] else 0,
                    })
        return sessions
    except Exception as e:
        logger.warning(f"Failed to list sessions: {e}")
        return []


@router.get("/{session_id}/messages", response_model=List[MessageItem])
def get_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get messages for a session."""
    user_id = current_user["id"]

    try:
        container = get_or_create_user_container(user_id)
        result = container.execute_command(
            f"cd /root/.hermes && sqlite3 sessions.db "
            f"'SELECT role, content, timestamp FROM messages "
            f"WHERE session_id=\"{session_id}\" ORDER BY timestamp'"
        )

        messages = []
        for line in result.strip().split("\n"):
            if line:
                parts = line.split("|")
                if len(parts) >= 3:
                    messages.append({
                        "role": parts[0],
                        "content": parts[1] if parts[1] else None,
                        "timestamp": float(parts[2]) if parts[2] else 0,
                    })
        return messages
    except Exception as e:
        logger.warning(f"Failed to get messages: {e}")
        return []


@router.patch("/{session_id}/title")
def update_title(
    session_id: str,
    req: UpdateTitleRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update session title."""
    user_id = current_user["id"]

    try:
        container = get_or_create_user_container(user_id)
        escaped_title = req.title.replace('"', '\\"')
        container.execute_command(
            f"cd /root/.hermes && sqlite3 sessions.db "
            f"'UPDATE sessions SET title=\"{escaped_title}\" WHERE id=\"{session_id}\"'"
        )
        return {"ok": True, "title": req.title}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{session_id}/stop")
def stop_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Stop any running agent for this session."""
    # Agent runs in container - stopping is handled by container timeout
    return {"ok": True, "message": "Session will stop on idle timeout"}


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a session."""
    user_id = current_user["id"]

    try:
        container = get_or_create_user_container(user_id)
        container.execute_command(
            f"cd /root/.hermes && sqlite3 sessions.db "
            f"'DELETE FROM messages WHERE session_id=\"{session_id}\"; "
            f"DELETE FROM sessions WHERE id=\"{session_id}\"'"
        )
        return {"ok": True, "message": "Session deleted"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))