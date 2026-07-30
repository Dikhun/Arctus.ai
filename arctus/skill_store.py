"""Codified Agent Skill Store (Meta-Tools).

When the multi-agent system successfully builds and tests a complex
sub-module (e.g., JWT Authentication, Stripe Webhook Handler), the verified
execution script/code block is saved into a local Skill Library. Future
tasks can reuse these verified skills instead of rebuilding from scratch.

Storage: file-per-skill under ~/.config/arctus-ai/skills/<name>/
  <name>/code.py          # the verified code block
  <name>/metadata.json    # tags, tier, verification status, uses_count
A manifest index at ~/.config/arctus-ai/skills/skills.json enables fast lookup.

API:
    store = SkillStore()
    store.save("jwt-auth", code, description="...", tags=["auth","jwt"])
    skills = store.search("authentication")   # fuzzy match
    skill = store.load("jwt-auth")
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, asdict, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import CONFIG_DIR

logger = logging.getLogger("arctus.skill_store")

SKILLS_DIR = CONFIG_DIR / "skills"
MANIFEST_FILE = SKILLS_DIR / "skills.json"


@dataclass
class Skill:
    name: str
    code: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    tier: str = "strong"
    verification_status: str = "verified"   # verified | unverified | failed
    created_at: float = 0.0
    session_id: str = ""
    uses_count: int = 0

    def to_metadata(self) -> Dict[str, Any]:
        """Metadata dict (excludes the code, which lives in code.py)."""
        d = asdict(self)
        d.pop("code", None)
        return d

    @classmethod
    def from_metadata(cls, name: str, meta: Dict[str, Any], code: str = "") -> "Skill":
        return cls(
            name=name,
            code=code,
            description=meta.get("description", ""),
            tags=meta.get("tags", []),
            tier=meta.get("tier", "strong"),
            verification_status=meta.get("verification_status", "unverified"),
            created_at=meta.get("created_at", 0.0),
            session_id=meta.get("session_id", ""),
            uses_count=meta.get("uses_count", 0),
        )


class SkillStore:
    """File-per-skill library with a manifest index for fast lookup."""

    def __init__(self) -> None:
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_manifest()

    def _ensure_manifest(self) -> None:
        if not MANIFEST_FILE.exists():
            MANIFEST_FILE.write_text(
                json.dumps({"skills": [], "version": 1}, indent=2),
                encoding="utf-8",
            )

    def _load_manifest(self) -> Dict[str, Any]:
        try:
            return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"skills": [], "version": 1}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    @staticmethod
    def _slugify(name: str) -> str:
        """Make a filesystem-safe skill name."""
        slug = re.sub(r"[^a-z0-9-]+", "-", name.lower().strip()).strip("-")
        return slug or "unnamed-skill"

    def save(
        self,
        name: str,
        code: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        tier: str = "strong",
        verification_status: str = "verified",
        session_id: str = "",
    ) -> Skill:
        """Save a verified code block as a reusable skill."""
        slug = self._slugify(name)
        skill_dir = SKILLS_DIR / slug
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Preserve uses_count if the skill already exists.
        existing = self.load(slug)
        uses_count = existing.uses_count if existing and existing.verification_status == verification_status else 0

        skill = Skill(
            name=slug, code=code, description=description,
            tags=tags or [], tier=tier,
            verification_status=verification_status,
            created_at=time.time(), session_id=session_id,
            uses_count=uses_count,
        )

        # Write code + metadata.
        (skill_dir / "code.py").write_text(code, encoding="utf-8")
        (skill_dir / "metadata.json").write_text(
            json.dumps(skill.to_metadata(), indent=2), encoding="utf-8",
        )

        # Update manifest index.
        manifest = self._load_manifest()
        skills_list: List[Dict[str, Any]] = manifest.get("skills", [])
        skills_list = [s for s in skills_list if s.get("name") != slug]
        skills_list.append(skill.to_metadata())
        manifest["skills"] = skills_list
        manifest["updated_at"] = time.time()
        self._save_manifest(manifest)

        logger.info("Skill saved: %s (%d tags, %d chars, status=%s)",
                     slug, len(skill.tags), len(code), verification_status)
        return skill

    def load(self, name: str) -> Optional[Skill]:
        """Load a skill by name. Returns None if not found."""
        slug = self._slugify(name)
        skill_dir = SKILLS_DIR / slug
        if not skill_dir.exists():
            return None
        try:
            meta = json.loads((skill_dir / "metadata.json").read_text(encoding="utf-8"))
            code = (skill_dir / "code.py").read_text(encoding="utf-8")
            return Skill.from_metadata(slug, meta, code)
        except Exception as e:
            logger.warning("Failed to load skill %s: %s", slug, e)
            return None

    def search(
    self, query: str, tags: Optional[List[str]] = None, top_k: int = 5,
) -> List[Skill]:
    """Fuzzy-search skills by name/description/tags."""
    manifest = self._load_manifest()
    entries: List[Dict[str, Any]] = manifest.get("skills", [])
    query_lower = query.lower()
    scored: List[tuple] = []

    # Safely sanitize input tags
    wanted_tags = [t.lower() for t in tags if t] if tags else []

    for entry in entries:
        name = entry.get("name", "")
        desc = entry.get("description", "")
        
        # FIX: Ensure entry_tags is always a list of lowercased strings
        raw_tags = entry.get("tags") or []
        entry_tags = [str(t).lower() for t in raw_tags if t is not None]

        # Tag filter (exact)
        if wanted_tags:
            if not any(t in entry_tags for t in wanted_tags):
                continue

        # Fuzzy score calculation
        name_score = SequenceMatcher(None, query_lower, name.lower()).ratio()
        desc_score = SequenceMatcher(None, query_lower, desc.lower()).ratio()
        
        tag_score = max(
            (SequenceMatcher(None, query_lower, t).ratio() for t in entry_tags),
            default=0.0,
        )
        score = max(name_score, desc_score * 0.8, tag_score * 0.7)
        scored.append((score, name))

    scored.sort(reverse=True)
    results: List[Skill] = []
    for score, name in scored[:top_k]:
        skill = self.load(name)
        if skill:
            results.append(skill)
            
    return results

   def increment_use(self, name: str) -> None:
        """Bump the uses_count when a skill is reused (feedback loop)."""
        slug = self._slugify(name)
        skill = self.load(slug)
        if not skill:
            return
        skill.uses_count += 1
        skill_dir = SKILLS_DIR / slug
        (skill_dir / "metadata.json").write_text(
            json.dumps(skill.to_metadata(), indent=2), encoding="utf-8",
        )
        # Update manifest entry too.
        manifest = self._load_manifest()
        for entry in manifest.get("skills", []):
            if entry.get("name") == slug:
                entry["uses_count"] = skill.uses_count
        self._save_manifest(manifest)

    def delete(self, name: str) -> bool:
        """Remove a skill."""
        import shutil
        slug = self._slugify(name)
        skill_dir = SKILLS_DIR / slug
        existed = skill_dir.exists()
        if existed:
            shutil.rmtree(skill_dir, ignore_errors=True)
            manifest = self._load_manifest()
            manifest["skills"] = [s for s in manifest.get("skills", []) if s.get("name") != slug]
            self._save_manifest(manifest)
        return existed
