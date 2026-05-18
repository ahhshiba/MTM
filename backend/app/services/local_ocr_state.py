import json
import time
from typing import Any, Dict, Optional

import redis

from app.core.config import settings


_redis = redis.Redis.from_url(settings.local_redis_url, decode_responses=True)
_STATE_PREFIX = "local:ocr:job:"
_DOC_VERSION_PREFIX = "local:ocr:doc:"


def _state_key(local_job_id: str) -> str:
    return f"{_STATE_PREFIX}{local_job_id}"


def _doc_version_key(document_id: str) -> str:
    return f"{_DOC_VERSION_PREFIX}{document_id}:latest_version"


def set_local_job_state(local_job_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    state = dict(state)
    current = get_local_job_state(local_job_id) or {}
    if "progress" in state and isinstance(state.get("progress"), (int, float)):
        previous = current.get("progress")
        if isinstance(previous, (int, float)) and state["progress"] < previous:
            state["progress"] = previous
    state["updated_at"] = int(time.time())
    _redis.set(_state_key(local_job_id), json.dumps(state), ex=settings.local_job_ttl_seconds)
    return state


def get_local_job_state(local_job_id: str) -> Optional[Dict[str, Any]]:
    raw = _redis.get(_state_key(local_job_id))
    return json.loads(raw) if raw else None


def update_local_job_state(local_job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    current = get_local_job_state(local_job_id)
    if current is None:
        return None
    current.update(updates)
    return set_local_job_state(local_job_id, current)


def get_latest_doc_version(document_id: str) -> Optional[int]:
    raw = _redis.get(_doc_version_key(document_id))
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def set_latest_doc_version(document_id: str, version_no: int) -> None:
    _redis.set(_doc_version_key(document_id), str(version_no), ex=settings.local_job_ttl_seconds)
