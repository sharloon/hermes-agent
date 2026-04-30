"""User private file space - Container Integrated.

Files are stored in the user's container workspace directory:
~/.hermes/user-workspaces/{user_id}/workspace/

Users can:
- Upload files to their workspace
- List files in workspace
- Download files from workspace
- Delete files from workspace
"""

import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from hermes_constants import get_hermes_home
from hermes_state import UserDataDB
from api.deps import get_current_user, get_user_db
from api.user_containers import get_or_create_user_container

router = APIRouter()
logger = logging.getLogger(__name__)

# Max upload size: 50 MB
MAX_FILE_BYTES = 50 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",        # .xlsx
    # Allow common code files
    "application/octet-stream",  # For .py, .js, etc.
}


def _get_user_workspace_dir(user_id: str) -> Path:
    """Get user's workspace directory on host."""
    return get_hermes_home() / "user-workspaces" / user_id / "workspace"


class FileInfo(BaseModel):
    id: str
    filename: str
    content_type: Optional[str]
    size_bytes: Optional[int]
    uploaded_at: float
    path: Optional[str] = None  # Relative path in workspace


class UploadResponse(BaseModel):
    success: bool
    file_id: str
    filename: str
    message: Optional[str] = None


@router.post("", response_model=UploadResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    path: Optional[str] = None,  # Target path in workspace (e.g., "src/main.py")
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Upload a file to user's workspace.

    Args:
        file: The file to upload
        path: Optional target path in workspace (default: uploads/{filename})
    """
    user_id = current_user["id"]

    # Validate content type (relaxed for code files)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        # Allow if filename has allowed extension
        filename = file.filename or ""
        allowed_extensions = {
            ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
            ".cpp", ".c", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
            ".kt", ".scala", ".r", ".m", ".sh", ".bash", ".zsh",
            ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg",
            ".md", ".txt", ".json", ".csv", ".html", ".css", ".scss",
            ".pdf", ".docx", ".xlsx", ".png", ".jpg", ".jpeg", ".gif", ".webp",
        }
        ext = os.path.splitext(filename)[1].lower()
        if ext not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File type '{file.content_type}' is not allowed",
            )

    # Read file data
    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit",
        )

    # Determine target path
    filename = file.filename or "upload"
    file_id = str(uuid.uuid4())

    # Sanitize filename/path
    safe_filename = os.path.basename(filename)
    if path:
        # Use provided path, but sanitize
        safe_path = path.lstrip("/").replace("..", "")
        target_rel_path = safe_path
    else:
        # Default: put in uploads directory
        target_rel_path = f"uploads/{file_id}/{safe_filename}"

    # Write to host workspace directory
    workspace_dir = _get_user_workspace_dir(user_id)
    target_path = workspace_dir / target_rel_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(data)

    # Record in database
    db.add_user_file(
        file_id=file_id,
        user_id=user_id,
        filename=safe_filename,
        content_type=file.content_type,
        storage_path=str(target_path),
        size_bytes=len(data),
    )

    logger.info(f"Uploaded file {safe_filename} ({len(data)} bytes) to workspace for user {user_id}")

    return UploadResponse(
        success=True,
        file_id=file_id,
        filename=safe_filename,
        message=f"File uploaded to workspace/{target_rel_path}",
    )


@router.get("", response_model=List[FileInfo])
def list_files(
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """List user's uploaded files."""
    records = db.list_user_files(current_user["id"])

    # Add relative path
    workspace_dir = _get_user_workspace_dir(current_user["id"])
    result = []
    for r in records:
        storage_path = Path(r.get("storage_path", ""))
        rel_path = None
        if storage_path.exists():
            try:
                rel_path = str(storage_path.relative_to(workspace_dir))
            except ValueError:
                rel_path = str(storage_path)

        result.append(FileInfo(
            id=r["id"],
            filename=r["filename"],
            content_type=r.get("content_type"),
            size_bytes=r.get("size_bytes"),
            uploaded_at=r.get("uploaded_at", 0),
            path=rel_path,
        ))

    return result


@router.get("/{file_id}")
def download_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Download a file from user's workspace."""
    record = db.get_user_file(file_id)
    if not record or record["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="File not found")

    path = Path(record["storage_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=path,
        filename=record["filename"],
        media_type=record.get("content_type") or "application/octet-stream",
    )


@router.get("/workspace/{rel_path:path}")
def download_by_path(
    rel_path: str,
    current_user: dict = Depends(get_current_user),
):
    """Download a file by its relative path in workspace.

    Example: /api/v1/files/workspace/uploads/abc123/document.pdf
    """
    user_id = current_user["id"]
    workspace_dir = _get_user_workspace_dir(user_id)

    # Sanitize path
    safe_path = rel_path.lstrip("/").replace("..", "")
    full_path = workspace_dir / safe_path

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Ensure file is within workspace (security check)
    try:
        full_path.resolve().relative_to(workspace_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    filename = os.path.basename(safe_path)
    return FileResponse(
        path=full_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Delete a file from user's workspace."""
    record = db.get_user_file(file_id)
    if not record or record["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from disk
    path = Path(record["storage_path"])
    if path.exists():
        path.unlink()
        # Try to remove empty parent directories
        try:
            parent = path.parent
            while parent != _get_user_workspace_dir(current_user["id"]):
                if parent.is_dir() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                else:
                    break
        except OSError:
            pass

    db.soft_delete_file(file_id, current_user["id"])
    logger.info(f"Deleted file {record['filename']} for user {current_user['id']}")


@router.get("/browse/{subdir:path}")
def browse_directory(
    subdir: str = "",
    current_user: dict = Depends(get_current_user),
):
    """Browse files in user's workspace directory.

    Returns list of files and subdirectories in the specified subdirectory.
    """
    user_id = current_user["id"]
    workspace_dir = _get_user_workspace_dir(user_id)

    # Sanitize path
    safe_subdir = subdir.lstrip("/").replace("..", "")
    target_dir = workspace_dir / safe_subdir

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="Directory not found")

    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    # Security check
    try:
        target_dir.resolve().relative_to(workspace_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    # List contents
    items = []
    for item in target_dir.iterdir():
        rel_path = str(item.relative_to(workspace_dir))
        items.append({
            "name": item.name,
            "path": rel_path,
            "type": "directory" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else None,
        })

    # Sort: directories first, then files
    items.sort(key=lambda x: (x["type"] == "file", x["name"]))

    return {
        "directory": safe_subdir or "/",
        "items": items,
    }