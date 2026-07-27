"""File-backed session state.

Each session is a JSON file under ~/.config/arctus-ai/sessions/<id>.json.
State survives process restarts and is easy to inspect / clear by hand.

Monthly usage counters are stored under ~/.config/arctus-ai/usage/<id>/<month>.json
so they survive process restarts and can be audited.
"""
from __future__ import annotations

import json
import time
import calendar
from pathlib import Path
from typing import List, Dict, Any

from .config import SESSIONS_DIR


USAGE_DIR = SESSIONS_DIR.parent / "usage"


def _path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _usage_path(session_id: str, month_key: str) -> Path:
    """month_key is 'YYYY-MM'."""
    return USAGE_DIR / session_id / f"{month_key}.json"


def _current_month_key() -> str:
    now = time.gmtime()
    return f"{now.tm_year}-{now.tm_mon:02d}"


def load(session_id: str) -> Dict[str, Any]:
    p = _path(session_id)
    if not p.exists():
        return {
            "id": session_id,
            "created_at": time.time(),
            "steps": [],
            "log": [],
            "history": [],
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {
            "id": session_id,
            "created_at": time.time(),
            "steps": [],
            "log": [],
            "history": [],
        }


def save(session: Dict[str, Any]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _path(session["id"]).write_text(
        json.dumps(session, indent=2), encoding="utf-8"
    )


def reset(session_id: str, scope: str = "all") -> Dict[str, Any]:
    """Drop session state. scope: 'all' | 'history'."""
    p = _path(session_id)
    if not p.exists():
        return {"status": "already_empty", "session_id": session_id, "scope": scope}
    if scope == "history":
        data = json.loads(p.read_text(encoding="utf-8"))
        data["history"] = []
        data["steps"] = []
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"status": "reset_history", "session_id": session_id, "scope": scope}
    # scope == "all"
    try:
        p.unlink()
    except OSError:
        pass
    return {"status": "reset_all", "session_id": session_id, "scope": scope}


# ── Monthly usage tracking ────────────────────────────────────────────────

def monthly_usage(session_id: str) -> Dict[str, Any]:
    """Return the current month's usage counters for a session.

    Keys: runs (int), in_tokens (int), out_tokens (int), est_cost (float).
    """
    month_key = _current_month_key()
    p = _usage_path(session_id, month_key)
    if not p.exists():
        return {"runs": 0, "in_tokens": 0, "out_tokens": 0, "est_cost": 0.0, "month": month_key}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data["month"] = month_key
        return data
    except Exception:
        return {"runs": 0, "in_tokens": 0, "out_tokens": 0, "est_cost": 0.0, "month": month_key}


def increment_usage(
    session_id: str,
    in_tokens: int = 0,
    out_tokens: int = 0,
    runs: int = 1,
    est_cost: float = 0.0,
) -> Dict[str, Any]:
    """Atomically increment monthly usage counters and persist."""
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    month_key = _current_month_key()
    p = _usage_path(session_id, month_key)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {}

    data["runs"] = data.get("runs", 0) + runs
    data["in_tokens"] = data.get("in_tokens", 0) + in_tokens
    data["out_tokens"] = data.get("out_tokens", 0) + out_tokens
    data["est_cost"] = round(data.get("est_cost", 0.0) + est_cost, 6)
    data["month"] = month_key
    data["updated_at"] = time.time()

    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data
