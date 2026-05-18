from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, List, Sequence

import psycopg2
from psycopg2.extras import DictCursor

from app.core.config import settings


class TokenStoreError(RuntimeError):
    pass


@contextmanager
def _conn():
    conn = psycopg2.connect(settings.database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_session_token_totals(session_id: str) -> Dict[str, int]:
    query = """
    SELECT
        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
        COALESCE(SUM(candidate_tokens), 0) AS candidate_tokens,
        COALESCE(SUM(total_tokens), 0) AS total_tokens
    FROM vlm_messages
    WHERE session_id = %s
    """
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, (session_id,))
                row = cur.fetchone() or {}
                return {
                    "session_id": session_id,
                    "prompt_tokens": int(row.get("prompt_tokens") or 0),
                    "candidate_tokens": int(row.get("candidate_tokens") or 0),
                    "total_tokens": int(row.get("total_tokens") or 0),
                }
    except psycopg2.Error as exc:
        raise TokenStoreError("failed to read session tokens") from exc


def get_tokens_for_sessions(session_ids: Sequence[str]) -> Dict[str, object]:
    session_ids = [str(session_id) for session_id in session_ids if session_id]
    if not session_ids:
        return {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "sessions": [],
        }

    query = """
    SELECT
        session_id,
        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
        COALESCE(SUM(candidate_tokens), 0) AS candidate_tokens,
        COALESCE(SUM(total_tokens), 0) AS total_tokens
    FROM vlm_messages
    WHERE session_id = ANY(%s)
    GROUP BY session_id
    """
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, (session_ids,))
                rows = cur.fetchall() or []
    except psycopg2.Error as exc:
        raise TokenStoreError("failed to read session tokens") from exc

    by_session: Dict[str, Dict[str, int]] = {}
    for row in rows:
        sid = str(row.get("session_id"))
        by_session[sid] = {
            "session_id": sid,
            "prompt_tokens": int(row.get("prompt_tokens") or 0),
            "candidate_tokens": int(row.get("candidate_tokens") or 0),
            "total_tokens": int(row.get("total_tokens") or 0),
        }

    sessions: List[Dict[str, int]] = []
    total_prompt = 0
    total_candidate = 0
    total_tokens = 0
    for sid in session_ids:
        payload = by_session.get(
            sid,
            {
                "session_id": sid,
                "prompt_tokens": 0,
                "candidate_tokens": 0,
                "total_tokens": 0,
            },
        )
        sessions.append(payload)
        total_prompt += payload["prompt_tokens"]
        total_candidate += payload["candidate_tokens"]
        total_tokens += payload["total_tokens"]

    return {
        "total_tokens": total_tokens,
        "prompt_tokens": total_prompt,
        "candidate_tokens": total_candidate,
        "sessions": sessions,
    }
