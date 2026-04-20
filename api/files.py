"""User private file space: upload, list, delete."""

import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from hermes_constants import get_hermes_home
from hermes_state import UserDataDB
from api.deps import get_current_user, get_user_db

router = APIRouter()

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
}


def _user_upload_dir(user_id: str) -> Path:
    d = get_hermes_home() / "user-files" / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


class FileInfo(BaseModel):
    id: str
    filename: str
    content_type: Optional[str]
    size_bytes: Optional[int]
    uploaded_at: float


@router.post("", response_model=FileInfo, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' is not allowed",
        )

    data = await file.read()
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 50 MB limit",
        )

    file_id = str(uuid.uuid4())
    upload_dir = _user_upload_dir(current_user["id"]) / file_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / (file.filename or "upload")
    dest.write_bytes(data)

    record = db.add_user_file(
        file_id=file_id,
        user_id=current_user["id"],
        filename=file.filename or "upload",
        content_type=file.content_type,
        storage_path=str(dest),
        size_bytes=len(data),
    )
    return record


@router.get("", response_model=List[FileInfo])
def list_files(
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    return db.list_user_files(current_user["id"])


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    record = db.get_user_file(file_id)
    if not record or record["user_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from disk
    path = Path(record["storage_path"])
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()  # remove per-file dir if empty
    except OSError:
        pass

    db.soft_delete_file(file_id, current_user["id"])
