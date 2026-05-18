# app/redis/state.py
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import redis

from app.config import settings


_r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _key(job_id: str) -> str:
    return f"ocr:job:{job_id}"


def set_job_state(job_id: str, data: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
    payload = dict(data)
    current = get_job_state(job_id) or {}
    if "progress" in payload and isinstance(payload.get("progress"), (int, float)):
        previous = current.get("progress")
        if isinstance(previous, (int, float)) and payload["progress"] < previous:
            payload["progress"] = previous
    payload["updated_at"] = int(time.time())

    ttl = ttl_seconds if ttl_seconds is not None else settings.JOB_STATE_TTL_SECONDS
    _r.set(_key(job_id), json.dumps(payload, ensure_ascii=False), ex=ttl)


def get_job_state(job_id: str) -> Optional[Dict[str, Any]]:
    raw = _r.get(_key(job_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def mark_canceled(job_id: str) -> None:
    state = get_job_state(job_id) or {}
    state["cancel_requested"] = True
    set_job_state(job_id, state)


def is_cancel_requested(job_id: str) -> bool:
    state = get_job_state(job_id) or {}
    return bool(state.get("cancel_requested"))
