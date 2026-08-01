from __future__ import annotations

import hashlib
from datetime import datetime


def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> datetime:
    return datetime.utcnow()
