"""Skills API: private skill CRUD + publish to public space."""

import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from hermes_state import UserDataDB
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
