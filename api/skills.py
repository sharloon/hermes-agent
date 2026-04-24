"""Skills API: private skill CRUD + publish to public space."""

import io
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from hermes_state import UserDataDB
from hermes_constants import get_hermes_home
from api.deps import get_current_user, get_user_db, require_admin

router = APIRouter()

# ── Schemas ───────────────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    skill_content: str  # full SKILL.md content


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    skill_content: Optional[str] = None


class SkillInfo(BaseModel):
    id: str
    owner_id: str
    name: str
    description: Optional[str]
    visibility: str
    status: str
    created_at: float
    updated_at: float


class SkillDetail(SkillInfo):
    skill_content: str
    published_at: Optional[float]


# ── Helpers ───────────────────────────────────────────────────────────────────

_SKILL_CONTENT_MAX = 64_000  # ~16K tokens, generous for a SKILL.md


def _validate_content(content: str):
    if len(content) > _SKILL_CONTENT_MAX:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Skill content exceeds {_SKILL_CONTENT_MAX} character limit",
        )


# ── Private skill endpoints ───────────────────────────────────────────────────

@router.post("", response_model=SkillDetail, status_code=201)
def create_skill(
    req: SkillCreate,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    _validate_content(req.skill_content)
    skill_id = str(uuid.uuid4())
    skill = db.create_skill(
        skill_id=skill_id,
        owner_id=current_user["id"],
        name=req.name.strip(),
        description=req.description or "",
        skill_content=req.skill_content,
    )
    return skill


# ── Zip upload for complete skill directory ─────────────────────────────────────

# Allowed skill subdirectories and file patterns
_SKILL_ALLOWED_DIRS = frozenset({"references", "reference", "scripts", "script", "templates", "template"})
_SKILL_MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10 MB limit for zip
_SKILL_MAX_FILES = 50  # Max files in a zip


def _validate_skill_zip(zip_bytes: bytes) -> tuple[str, dict[str, bytes]]:
    """Validate zip structure and return (skill_name, files_dict).

    files_dict: {relative_path: file_bytes}
    """
    if len(zip_bytes) > _SKILL_MAX_ZIP_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Zip exceeds {_SKILL_MAX_ZIP_SIZE // 1024 // 1024} MB limit",
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid zip file",
        )

    # Check file count
    file_list = [f for f in zf.namelist() if not f.endswith("/")]
    if len(file_list) > _SKILL_MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zip contains more than {_SKILL_MAX_FILES} files",
        )

    # First pass: detect top-level directory to strip (if all files share it)
    # e.g., zip created with "zip -r skill.zip my-skill/" results in "my-skill/SKILL.md"
    top_level_dir: Optional[str] = None
    all_parts = []
    for name in file_list:
        parts = Path(name).parts
        if parts and parts[0] == ".":
            parts = parts[1:]
        # Skip hidden files and __MACOSX etc
        if any(p.startswith(".") or p.startswith("__") for p in parts):
            continue
        all_parts.append(parts)

    # Check if all files share a common top-level directory that should be stripped
    if all_parts and all(len(p) >= 2 for p in all_parts):
        candidate = all_parts[0][0]
        # Strip if: (1) not in allowed dirs, (2) all files share it, (3) one file is SKILL.md at level 2
        has_skill_md_at_level_2 = any(
            len(p) >= 2 and p[1] == "SKILL.md" and p[0] == candidate
            for p in all_parts
        ) or any(
            len(p) >= 2 and p[-1] == "SKILL.md" and p[0] == candidate
            for p in all_parts
        )
        all_share_top = all(p[0] == candidate for p in all_parts)
        if candidate not in _SKILL_ALLOWED_DIRS and all_share_top and has_skill_md_at_level_2:
            top_level_dir = candidate

    files_dict: dict[str, bytes] = {}
    skill_md_found = False
    skill_name = None

    for name in file_list:
        parts = Path(name).parts
        if parts and parts[0] == ".":
            parts = parts[1:]

        # Skip hidden files and __MACOSX etc
        if any(p.startswith(".") or p.startswith("__") for p in parts):
            continue

        # Strip detected top-level directory
        if top_level_dir and parts and parts[0] == top_level_dir:
            parts = parts[1:]

        if not parts:
            continue

        rel_path = str(Path(*parts)) if parts else name

        # Validate remaining directory components (now should be references/scripts/templates or empty)
        for part in parts[:-1]:  # Check directories
            if part not in _SKILL_ALLOWED_DIRS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid directory '{part}'. Allowed: references, scripts, templates",
                )

        # Check for path traversal
        if ".." in rel_path or rel_path.startswith("/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid path in zip (path traversal detected)",
                )

        content = zf.read(name)
        if parts[-1] == "SKILL.md":
            skill_md_found = True
            # Parse frontmatter to get skill name
            from agent.skill_utils import parse_frontmatter
            fm, _ = parse_frontmatter(content.decode("utf-8", errors="replace"))
            skill_name = fm.get("name") or "unnamed"

        files_dict[rel_path] = content

    if not skill_md_found:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Zip must contain a SKILL.md file",
        )

    return skill_name or "unnamed", files_dict


class SkillZipUpload(BaseModel):
    id: str
    owner_id: str
    name: str
    description: Optional[str]
    visibility: str
    status: str
    created_at: float
    updated_at: float
    files: List[str]  # list of relative paths uploaded


@router.post("/upload-zip", response_model=SkillZipUpload, status_code=201)
async def upload_skill_zip(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Upload a complete skill as a zip archive.

    The zip must contain:
    - SKILL.md (required) with YAML frontmatter including 'name'
    - references/*.md (optional) - reference documents
    - scripts/* (optional) - executable scripts
    - templates/* (optional) - template files

    Files are extracted to ~/.hermes/skills/private/{skill_id}/
    """
    zip_bytes = await file.read()
    skill_name, files_dict = _validate_skill_zip(zip_bytes)

    skill_id = str(uuid.uuid4())
    skill_dir = get_hermes_home() / "skills" / "private" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Get SKILL.md content for database
    skill_content = files_dict.get("SKILL.md", b"").decode("utf-8")

    # Parse description from frontmatter
    from agent.skill_utils import parse_frontmatter
    fm, _ = parse_frontmatter(skill_content)
    description = fm.get("description", "")

    # Extract all files
    extracted_paths = []
    for rel_path, content in files_dict.items():
        target_path = skill_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        extracted_paths.append(rel_path)

    # Create database record
    skill = db.create_skill(
        skill_id=skill_id,
        owner_id=current_user["id"],
        name=skill_name.strip(),
        description=description or "",
        skill_content=skill_content,
    )

    return SkillZipUpload(
        id=skill_id,
        owner_id=current_user["id"],
        name=skill_name.strip(),
        description=description,
        visibility=skill.get("visibility", "private"),
        status=skill.get("status", "draft"),
        created_at=skill.get("created_at", time.time()),
        updated_at=skill.get("updated_at", time.time()),
        files=extracted_paths,
    )


@router.get("/upload-zip-preview")
async def preview_skill_zip(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Preview zip contents without creating skill. Returns file list and frontmatter."""
    zip_bytes = await file.read()
    skill_name, files_dict = _validate_skill_zip(zip_bytes)

    skill_content = files_dict.get("SKILL.md", b"").decode("utf-8")
    from agent.skill_utils import parse_frontmatter
    fm, body = parse_frontmatter(skill_content)

    return {
        "name": skill_name,
        "frontmatter": fm,
        "files": list(files_dict.keys()),
        "skill_content_preview": body[:500] + "..." if len(body) > 500 else body,
    }


@router.get("", response_model=List[SkillInfo])
def list_skills(
    visibility: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """List skills. visibility=private returns own skills; visibility=public returns all published."""
    if visibility == "public":
        return db.list_skills(visibility="public", status="published")
    # Default: own private skills
    return db.list_skills(owner_id=current_user["id"])


# ── All public skills (builtin + user published) ────────────────────────────────

class PublicSkillInfo(BaseModel):
    name: str
    description: Optional[str] = ""
    category: Optional[str] = None
    source: str  # "builtin" or "user_published"
    id: Optional[str] = None  # Only for user_published skills
    owner_id: Optional[str] = None  # Only for user_published skills
    can_remove: bool = False  # Only admin can remove user_published skills


@router.get("/all-public", response_model=List[PublicSkillInfo])
def list_all_public_skills():
    """Merge builtin skills + user published skills for PublicSkillsPage."""
    from tools.skills_tool import _find_all_skills

    # 1. Builtin skills from filesystem
    builtin_skills = _find_all_skills(skip_disabled=True)

    # 2. User published skills from database
    db = get_user_db()
    user_skills = db.list_skills(visibility="public", status="published")

    # 3. Merge with source marking
    result = []
    for s in builtin_skills:
        result.append({
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "category": s.get("category"),
            "source": "builtin",
            "id": None,
            "owner_id": None,
            "can_remove": False,
        })
    for s in user_skills:
        result.append({
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "category": "user_published",
            "source": "user_published",
            "id": s.get("id"),
            "owner_id": s.get("owner_id"),
            "can_remove": True,  # Admin can remove
        })

    return result


@router.get("/selectable", response_model=List[dict])
def list_selectable_skills(
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """List skills user can select for chat context (builtin + own skills + public skills)."""
    from tools.skills_tool import _find_all_skills

    result = []

    # 1. Builtin skills from filesystem
    builtin_skills = _find_all_skills(skip_disabled=True)
    for s in builtin_skills:
        skill_file = s.get("file")
        skill_content = ""
        if skill_file and skill_file.exists():
            try:
                skill_content = skill_file.read_text(encoding="utf-8")
            except Exception:
                pass
        result.append({
            "id": f"builtin:{s.get('name', '')}",
            "owner_id": "system",
            "name": s.get("name", ""),
            "description": s.get("description", ""),
            "visibility": "public",
            "status": "published",
            "skill_content": skill_content,
            "created_at": 0,
            "updated_at": 0,
            "published_at": None,
            "source": "builtin",
        })

    # 2. User's own skills (private + published)
    own_skills = db.list_skills(owner_id=current_user["id"])
    for skill_id in [s["id"] for s in own_skills]:
        skill = db.get_skill(skill_id)
        if skill:
            skill["source"] = "own"
            result.append(skill)

    # 3. Public skills from other users
    public_skills = db.list_skills(visibility="public", status="published")
    other_public = [s for s in public_skills if s["owner_id"] != current_user["id"]]
    for skill_id in [s["id"] for s in other_public]:
        skill = db.get_skill(skill_id)
        if skill:
            skill["source"] = "public"
            result.append(skill)

    return result


# ── Dynamic skill endpoints (must be after static routes) ──────────────────────

@router.get("/{skill_id}", response_model=SkillDetail)
def get_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    skill = db.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    # Allow access to own skills or published public skills
    if skill["owner_id"] != current_user["id"] and skill.get("visibility") != "public":
        raise HTTPException(status_code=403, detail="Access denied")
    return skill


@router.put("/{skill_id}", response_model=SkillDetail)
def update_skill(
    skill_id: str,
    req: SkillUpdate,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    skill = db.get_skill(skill_id)
    if not skill or skill["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill["status"] == "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot edit a published skill. Unpublish it first.",
        )
    updates = req.model_dump(exclude_none=True)
    if "skill_content" in updates:
        _validate_content(updates["skill_content"])
    updated = db.update_skill(skill_id, current_user["id"], **updates)
    return updated


@router.delete("/{skill_id}", status_code=204)
def delete_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    skill = db.get_skill(skill_id)
    if not skill or skill["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Skill not found")
    db.delete_skill(skill_id, current_user["id"])
    # Clean up filesystem: delete private/{skill_id}/ directory
    from hermes_constants import get_hermes_home
    import shutil
    skill_dir = get_hermes_home() / "skills" / "private" / skill_id
    if skill_dir.exists():
        shutil.rmtree(skill_dir, ignore_errors=True)


# ── Publish / unpublish ───────────────────────────────────────────────────────

@router.post("/{skill_id}/publish", response_model=SkillDetail)
def publish_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Submit a private skill to the public space (status: draft → published).

    Note: File remains in private/{skill_id}/ directory. Only database metadata changes.
    """
    skill = db.get_skill(skill_id)
    if not skill or skill["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill["status"] == "published":
        raise HTTPException(status_code=409, detail="Skill is already published")
    updated = db.update_skill(
        skill_id,
        current_user["id"],
        visibility="public",
        status="published",
        published_at=time.time(),
    )
    return updated


@router.post("/{skill_id}/unpublish", response_model=SkillDetail)
def unpublish_skill(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Retract a published skill back to private draft.

    Note: File remains in private/{skill_id}/ directory. Only database metadata changes.
    """
    skill = db.get_skill(skill_id)
    if not skill or skill["owner_id"] != current_user["id"]:
        raise HTTPException(status_code=404, detail="Skill not found")
    updated = db.update_skill(
        skill_id,
        current_user["id"],
        visibility="private",
        status="draft",
        published_at=None,
    )
    return updated


# ── Admin: remove user published skill ───────────────────────────────────────

@router.delete("/{skill_id}/admin-remove")
def admin_remove_skill(
    skill_id: str,
    admin: dict = Depends(require_admin),
    db: UserDataDB = Depends(get_user_db),
):
    """Admin unpublish a user's public skill (reverts to private draft)."""
    skill = db.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Revert to private draft (not delete)
    db.update_skill(
        skill_id,
        skill["owner_id"],
        visibility="private",
        status="draft",
        published_at=None,
    )

    # Clean up filesystem (optional: update frontmatter)
    from hermes_constants import get_hermes_home
    from agent.skill_utils import parse_frontmatter
    import yaml
    skill_dir = get_hermes_home() / "skills" / "private" / skill_id
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        try:
            content = skill_file.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(content)
            fm["visibility"] = "private"
            fm["status"] = "draft"
            fm_yaml = yaml.dump(fm, default_flow_style=False, sort_keys=False)
            new_content = f"---\n{fm_yaml}---\n\n{body.strip()}"
            skill_file.write_text(new_content, encoding="utf-8")
        except Exception:
            pass  # Ignore filesystem errors

    return {"ok": True, "skill_id": skill_id}


# ── Skill files management ──────────────────────────────────────────────────────

class SkillFileInfo(BaseModel):
    path: str
    size: int
    is_dir: bool


@router.get("/{skill_id}/files", response_model=List[SkillFileInfo])
def list_skill_files(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """List all files in a skill directory."""
    skill = db.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill["owner_id"] != current_user["id"] and skill.get("visibility") != "public":
        raise HTTPException(status_code=403, detail="Access denied")

    skill_dir = get_hermes_home() / "skills" / "private" / skill_id
    if not skill_dir.exists():
        return []

    files = []
    for path in skill_dir.rglob("*"):
        rel_path = str(path.relative_to(skill_dir))
        # Skip hidden files
        if any(p.startswith(".") for p in path.parts):
            continue
        files.append(SkillFileInfo(
            path=rel_path,
            size=path.stat().st_size if path.is_file() else 0,
            is_dir=path.is_dir(),
        ))
    return files


@router.get("/{skill_id}/files/{file_path:path}")
def get_skill_file(
    skill_id: str,
    file_path: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Get content of a specific file in a skill directory."""
    skill = db.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill["owner_id"] != current_user["id"] and skill.get("visibility") != "public":
        raise HTTPException(status_code=403, detail="Access denied")

    skill_dir = get_hermes_home() / "skills" / "private" / skill_id
    target_file = skill_dir / file_path

    # Security checks
    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")
    if not target_file.resolve().is_relative_to(skill_dir.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")
    if target_file.is_dir():
        raise HTTPException(status_code=400, detail="Path is a directory")

    from fastapi.responses import Response
    content = target_file.read_bytes()
    # Guess content type
    import mimetypes
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"
    return Response(content=content, media_type=content_type)


@router.get("/{skill_id}/download")
def download_skill_zip(
    skill_id: str,
    current_user: dict = Depends(get_current_user),
    db: UserDataDB = Depends(get_user_db),
):
    """Download a skill as a zip archive (builtin or user skill)."""
    from tools.skills_tool import _find_all_skills, SKILLS_DIR
    from agent.skill_utils import get_external_skills_dirs
    from fastapi.responses import StreamingResponse

    skill_name = None
    skill_dir = None

    # Handle builtin skills (id format: "builtin:name")
    if skill_id.startswith("builtin:"):
        skill_name = skill_id[7:]  # Remove "builtin:" prefix

        # Find the skill directory in skills dirs
        dirs_to_scan = []
        if SKILLS_DIR.exists():
            dirs_to_scan.append(SKILLS_DIR)
        dirs_to_scan.extend(get_external_skills_dirs())

        for scan_dir in dirs_to_scan:
            # Look for skill by directory name or SKILL.md frontmatter name
            for skill_md in scan_dir.rglob("SKILL.md"):
                skill_candidate_dir = skill_md.parent
                # Check directory name
                if skill_candidate_dir.name == skill_name:
                    skill_dir = skill_candidate_dir
                    break
                # Check frontmatter name
                try:
                    content = skill_md.read_text(encoding="utf-8")[:2000]
                    from agent.skill_utils import parse_frontmatter
                    fm, _ = parse_frontmatter(content)
                    if fm.get("name") == skill_name:
                        skill_dir = skill_candidate_dir
                        break
                except Exception:
                    continue
            if skill_dir:
                break

        if not skill_dir:
            raise HTTPException(status_code=404, detail="Builtin skill not found")

    else:
        # Handle user skills
        skill = db.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        # Allow download for own skills or public skills
        if skill["owner_id"] != current_user["id"] and skill.get("visibility") != "public":
            raise HTTPException(status_code=403, detail="Access denied")

        skill_name = skill.get("name", skill_id)
        skill_dir = get_hermes_home() / "skills" / "private" / skill_id

        if not skill_dir.exists():
            raise HTTPException(status_code=404, detail="Skill directory not found")

    # Create zip in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in skill_dir.rglob("*"):
            if path.is_file() and not any(p.startswith(".") for p in path.parts):
                rel_path = str(path.relative_to(skill_dir))
                zf.write(path, rel_path)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={skill_name}.zip"},
    )
