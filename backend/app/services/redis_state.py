import redis
import json
import time
from typing import Optional, Dict, Any
from app.core.config import settings

r = redis.Redis.from_url(settings.redis_url, decode_responses=True)

STATE_TTL = 60 * 60 * 24  # 24h

def set_doc_state(doc_id: str, state: Dict[str, Any]):
    state["updated_at"] = int(time.time())
    r.set(f"doc:{doc_id}:state", json.dumps(state), ex=STATE_TTL)

def get_doc_state(doc_id: str) -> Optional[Dict[str, Any]]:
    raw = r.get(f"doc:{doc_id}:state")
    return json.loads(raw) if raw else None

def mark_cancel(doc_id: str):
    r.set(f"doc:{doc_id}:cancel", "1", ex=600)

def is_canceled(doc_id: str) -> bool:
    return r.exists(f"doc:{doc_id}:cancel") == 1

def clear_state(doc_id: str):
    r.delete(f"doc:{doc_id}:state")
