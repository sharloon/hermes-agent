"""Conversation API: create sessions, send messages, stream responses, list history."""

import json
import os
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

router = APIRouter()

# ── Schemas ───────────────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None   # None = new session
    file_ids: Optional[List[str]] = []  # user files to include in context
    skill_id: Optional[str] = None     # skill to use as context
    stream: bool = True                # enable streaming response (SSE deltas)


class SessionSummary(BaseModel):
    id: str
    title: Optional[str]
    started_at: float
    message_count: int


class MessageItem(BaseModel):
    role: str
    content: Optional[str]
    timestamp: float


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session_db() -> SessionDB:
    from hermes_constants import get_hermes_home
    return SessionDB(get_hermes_home() / "state.db")


def _sync_private_skills_to_fs(user_id: str, db: UserDataDB) -> None:
    """Sync user's private skills to filesystem so Hermes can discover them.

    New simplified approach:
    - All skills stored in unified ~/.hermes/skills/private/{skill_id}/ directory
    - Database is the single source of truth for visibility/status
    - Frontmatter in SKILL.md reflects current database state
    - No file movement on publish/unpublish - only database updates + frontmatter refresh
    - Also sync all published public skills to ensure their frontmatter is current
    """
    from hermes_constants import get_hermes_home
    import shutil
    import yaml
    from agent.skill_utils import parse_frontmatter

    skills_dir = get_hermes_home() / "skills"
    private_dir = skills_dir / "private"

    # Create private directory
    private_dir.mkdir(parents=True, exist_ok=True)

    # Track which skill_ids we've written
    written_ids = set()

    # Helper: write skill file with updated frontmatter
    def _write_skill_with_frontmatter(skill_id: str, full_skill: dict, owner_id: str):
        skill_file = private_dir / skill_id / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)

        content = full_skill.get("skill_content", "")
        existing_fm, body = parse_frontmatter(content)

        # Update frontmatter with current database state
        updated_fm = {
            "id": skill_id,
            "name": full_skill.get("name", "unnamed"),
            "owner_id": owner_id,
            "visibility": full_skill.get("visibility", "private"),
            "status": full_skill.get("status", "draft"),
            "description": full_skill.get("description", ""),
        }
        # Preserve any other existing frontmatter fields
        for key, value in existing_fm.items():
            if key not in updated_fm:
                updated_fm[key] = value

        fm_yaml = yaml.dump(updated_fm, default_flow_style=False, sort_keys=False)
        new_content = f"---\n{fm_yaml}---\n\n{body.strip()}"
        skill_file.write_text(new_content, encoding="utf-8")
        return skill_id

    # 1. Sync current user's skills (both private and published)
    user_skills = db.list_skills(owner_id=user_id)
    for skill in user_skills:
        skill_id = skill["id"]
        full_skill = db.get_skill(skill_id)
        if full_skill:
            written_ids.add(_write_skill_with_frontmatter(skill_id, full_skill, user_id))

    # 2. Also sync all published public skills (to ensure frontmatter is current)
    # This ensures other users' published skills have correct visibility in filesystem
    public_skills = db.list_skills(visibility="public", status="published")
    for skill in public_skills:
        skill_id = skill["id"]
        owner_id = skill.get("owner_id", "")
        if skill_id not in written_ids:  # Don't re-sync if already synced
            full_skill = db.get_skill(skill_id)
            if full_skill:
                written_ids.add(_write_skill_with_frontmatter(skill_id, full_skill, owner_id))

    # Clean up orphan files (skills in filesystem but not in database)
    for existing_dir in private_dir.iterdir():
        if existing_dir.is_dir() and existing_dir.name not in written_ids:
            orphan_skill = db.get_skill(existing_dir.name)
            if orphan_skill:
                # Skill exists in database - keep it (might be another user's private skill)
                continue
            # Skill not in database - delete orphan
            shutil.rmtree(existing_dir, ignore_errors=True)




def _load_agent_config() -> dict:
    """Load minimal agent config from environment / hermes config.yaml."""
    try:
        from hermes_cli.config import load_config, load_env
        cfg = load_config()
        # Load .env into os.environ so subsequent os.getenv() calls see the values
        for k, v in load_env().items():
            if k not in os.environ:
                os.environ[k] = v
    except Exception:
        cfg = {}

    # Support multiple LLM providers
    model_cfg = cfg.get("model", {})
    if isinstance(model_cfg, dict):
        # New format: {default: "model-name", provider: "alibaba", base_url: "..."}
        model = model_cfg.get("default", "claude-sonnet-4-6")
        provider = model_cfg.get("provider", "anthropic")
        base_url = model_cfg.get("base_url")
    else:
        # Old format: model is a string
        model = model_cfg
        provider = "anthropic"
        base_url = None

    # Try to get API key from multiple sources based on provider
    if provider == "alibaba":
        api_key = os.getenv("DASHSCOPE_API_KEY") or cfg.get("api_key", "")
        base_url = base_url or os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    elif provider == "custom":
        # api_key may be stored directly in config.yaml under model.api_key
        api_key = (
            model_cfg.get("api_key") if isinstance(model_cfg, dict) else None
        ) or os.getenv("OPENAI_API_KEY") or cfg.get("api_key", "")
        base_url = base_url or os.getenv("OPENAI_BASE_URL")
        if not api_key:
            api_key = "custom"  # some local endpoints don't require a real key
    else:
        # Default to Anthropic/OpenAI compatible
        api_key = (
            os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_TOKEN")
            or os.getenv("OPENAI_API_KEY")
            or cfg.get("api_key", "")
        )
        base_url = base_url or os.getenv("OPENAI_BASE_URL")

    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "provider": provider,
    }


def _build_file_context(file_ids: List[str], user_id: str, db: UserDataDB) -> str:
    """Build a brief file listing to inject into the user message."""
    if not file_ids:
        return ""
    lines = ["[Attached files from your private space:]"]
    for fid in file_ids:
        rec = db.get_user_file(fid)
        if rec and rec["user_id"] == user_id:
            lines.append(f"- {rec['filename']} (id={fid}, type={rec['content_type']})")
    if len(lines) == 1:
        return ""
    lines.append(
        "[Use the read_user_file tool with the file IDs above to read their contents.]"
    )
    return "\n".join(lines)


def _build_skill_context(skill_id: str, user_id: str, db: UserDataDB) -> str:
    """Build skill context to inject into the user message."""
    if not skill_id:
        return ""
    skill = db.get_skill(skill_id)
    if not skill:
        return ""
    # Check access: own skill or public skill
    if skill["owner_id"] != user_id and skill.get("visibility") != "public":
        return ""
    skill_content = skill.get("skill_content", "")
    if not skill_content:
        return ""
    skill_name = skill.get("name", "unnamed")
    return f"""[使用技能 '{skill_name}' 来完成任务]

以下是该技能的完整内容：

{skill_content}

---
请按照上述技能的指引来处理用户的请求。
"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/send")
def send_message(
    req: SendMessageRequest,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Send a message and stream the agent response as SSE.

    When stream=True (default): sends 'delta' events with text chunks,
    then a final 'done' event.
    When stream=False: waits for complete response, sends single 'done' event.
    """
    from run_agent import AIAgent

    cfg = _load_agent_config()
    if not cfg["api_key"]:
        provider_name = cfg.get("provider", "LLM provider")
        raise HTTPException(
            status_code=503,
            detail=f"API key not configured for {provider_name}. Please check your ~/.hermes/.env file."
        )

    session_db = _get_session_db()
    session_id = req.session_id or str(uuid.uuid4())
    user_id = current_user["id"]

    # Build message with optional file and skill context
    user_message = req.message
    skill_ctx = _build_skill_context(req.skill_id, user_id, db)
    if skill_ctx:
        user_message = f"{skill_ctx}\n\n{user_message}"
    file_ctx = _build_file_context(req.file_ids or [], user_id, db)
    if file_ctx:
        user_message = f"{file_ctx}\n\n{user_message}"

    # Queue for streaming deltas (None sentinel marks completion)
    delta_queue: queue.Queue = queue.Queue()
    result_holder: dict = {"final_response": "", "error": None}

    def stream_callback(text: str) -> None:
        """Put text delta in queue for SSE generator."""
        if text:
            delta_queue.put(text)

    def run_agent_thread():
        """Run AIAgent in background thread, feed deltas to queue."""
        user_id_var.set(user_id)
        try:
            _sync_private_skills_to_fs(user_id, db)

            agent_kwargs = {
                "api_key": cfg["api_key"],
                "model": cfg["model"],
                "session_id": session_id,
                "user_id": user_id,
                "platform": "api",
                "session_db": session_db,
                "skip_context_files": True,
                "enabled_toolsets": ["hermes-api-server", "user_files"],
            }

            if cfg.get("base_url"):
                agent_kwargs["base_url"] = cfg["base_url"]

            agent = AIAgent(**agent_kwargs)

            # Use stream_callback only when streaming is enabled
            callback = stream_callback if req.stream else None
            result = agent.run_conversation(
                user_message=user_message,
                stream_callback=callback,
            )

            result_holder["final_response"] = result.get("final_response", "")
        except Exception as e:
            import traceback
            result_holder["error"] = f"{str(e)}\n{traceback.format_exc()}"
        finally:
            # Signal completion
            delta_queue.put(None)
            session_db.close()

    def event_stream():
        """SSE generator: read from queue and emit events."""
        # Start agent thread
        thread = threading.Thread(target=run_agent_thread)
        thread.start()

        try:
            while True:
                item = delta_queue.get(timeout=300)  # 5 min timeout
                if item is None:
                    # Completion sentinel
                    break
                # Emit delta event
                yield f"data: {json.dumps({'type': 'delta', 'content': item})}\n\n"

            # Final event
            if result_holder["error"]:
                yield f"data: {json.dumps({'type': 'error', 'detail': result_holder['error']})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'content': result_holder['final_response'], 'session_id': session_id})}\n\n"
        except queue.Empty:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Response timeout'})}\n\n"
        finally:
            thread.join(timeout=1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("", response_model=List[SessionSummary])
def list_sessions(
    current_user: dict = Depends(get_current_user),
):
    """List the current user's conversation sessions."""
    session_db = _get_session_db()
    try:
        rows = session_db._conn.execute(
            "SELECT id, title, started_at, message_count FROM sessions "
            "WHERE user_id = ? AND source = 'api' "
            "ORDER BY started_at DESC LIMIT 50",
            (current_user["id"],),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        session_db.close()


@router.get("/{session_id}/messages", response_model=List[MessageItem])
def get_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return messages for a session owned by the current user."""
    session_db = _get_session_db()
    try:
        session = session_db.get_session(session_id)
        if not session or session.get("user_id") != current_user["id"]:
            raise HTTPException(status_code=404, detail="Session not found")
        rows = session_db._conn.execute(
            "SELECT role, content, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        session_db.close()
