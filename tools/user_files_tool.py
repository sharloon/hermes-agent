"""User private file tools — lets the AI agent list and read user-uploaded files."""

import json
import logging
from pathlib import Path

from hermes_user_context import get_current_user_id
from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

# ── Schemas ───────────────────────────────────────────────────────────────────

LIST_USER_FILES_SCHEMA = {
    "name": "list_user_files",
    "description": (
        "List files the current user has uploaded to their private space. "
        "Returns file IDs, names, types, and sizes."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

READ_USER_FILE_SCHEMA = {
    "name": "read_user_file",
    "description": (
        "Read the content of a file from the current user's private space. "
        "Supports plain text, Markdown, CSV, JSON, and PDF (text extraction). "
        "For images, returns a description of the image path for vision analysis."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file ID returned by list_user_files.",
            },
            "offset": {
                "type": "integer",
                "description": "Line offset for large text files (default 0).",
            },
            "limit": {
                "type": "integer",
                "description": "Max lines to return (default 500).",
            },
        },
        "required": ["file_id"],
    },
}

# ── Helpers ───────────────────────────────────────────────────────────────────

_TEXT_TYPES = {
    "text/plain", "text/markdown", "text/csv", "application/json",
}
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_MAX_CHARS = 80_000


def _get_db():
    from hermes_state import UserDataDB
    from api.deps import get_user_db
    return get_user_db()


def _read_text(path: Path, offset: int, limit: int) -> str:
    lines = path.read_text(errors="replace").splitlines()
    chunk = lines[offset: offset + limit]
    text = "\n".join(chunk)
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n[truncated]"
    return text


def _read_pdf(path: Path) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        pages = [p.extract_text() or "" for p in reader.pages]
        text = "\n\n".join(pages)
        if len(text) > _MAX_CHARS:
            text = text[:_MAX_CHARS] + "\n[truncated]"
        return text
    except ImportError:
        return f"[PDF reading requires pypdf: pip install pypdf]\nFile path: {path}"
    except Exception as e:
        return f"[PDF read error: {e}]"


# ── Handlers ──────────────────────────────────────────────────────────────────

def _list_user_files(args: dict, **kw) -> str:
    user_id = get_current_user_id()
    if not user_id:
        return tool_error("list_user_files is only available in API mode (not CLI)")
    db = _get_db()
    files = db.list_user_files(user_id)
    if not files:
        return json.dumps({"files": [], "message": "No files uploaded yet."})
    return json.dumps({
        "files": [
            {
                "id": f["id"],
                "filename": f["filename"],
                "content_type": f["content_type"],
                "size_bytes": f["size_bytes"],
            }
            for f in files
        ]
    })


def _read_user_file(args: dict, **kw) -> str:
    user_id = get_current_user_id()
    if not user_id:
        return tool_error("read_user_file is only available in API mode (not CLI)")

    file_id = args.get("file_id", "").strip()
    if not file_id:
        return tool_error("file_id is required")

    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", 500))

    db = _get_db()
    record = db.get_user_file(file_id)
    if not record or record["user_id"] != user_id:
        return tool_error(f"File '{file_id}' not found")

    path = Path(record["storage_path"])
    if not path.exists():
        return tool_error(f"File '{record['filename']}' is missing from storage")

    ct = record.get("content_type") or ""

    if ct == "application/pdf":
        content = _read_pdf(path)
    elif ct in _TEXT_TYPES or ct.startswith("text/"):
        content = _read_text(path, offset, limit)
    elif ct in _IMAGE_TYPES:
        return json.dumps({
            "filename": record["filename"],
            "content_type": ct,
            "storage_path": str(path),
            "note": "Image file — use vision_analyze tool with this path to analyze the image.",
        })
    else:
        # Try reading as text anyway
        try:
            content = _read_text(path, offset, limit)
        except Exception as e:
            return tool_error(f"Cannot read file type '{ct}': {e}")

    return json.dumps({
        "filename": record["filename"],
        "content_type": ct,
        "content": content,
    })


# ── Registration ──────────────────────────────────────────────────────────────

registry.register(
    name="list_user_files",
    toolset="user_files",
    schema=LIST_USER_FILES_SCHEMA,
    handler=_list_user_files,
    check_fn=None,
    emoji="📁",
)

registry.register(
    name="read_user_file",
    toolset="user_files",
    schema=READ_USER_FILE_SCHEMA,
    handler=_read_user_file,
    check_fn=None,
    emoji="📄",
)
