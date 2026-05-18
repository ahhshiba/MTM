from __future__ import annotations

from contextlib import contextmanager
from typing import Optional

import psycopg2
from psycopg2.extras import DictCursor

from app.core.config import settings


class DocumentStoreError(RuntimeError):
    pass


class DocumentVersionConflict(DocumentStoreError):
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


def get_latest_version(document_id: str) -> Optional[int]:
    query = "SELECT MAX(version_no) AS max_version FROM document_versions WHERE document_id = %s"
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, (document_id,))
                row = cur.fetchone()
                if not row or row["max_version"] is None:
                    return None
                return int(row["max_version"])
    except psycopg2.Error as exc:
        raise DocumentStoreError("failed to read latest version") from exc


def ensure_document_exists(
    document_id: str,
    title: str,
    file_path: str,
    page_count: int,
    status: str,
) -> None:
    query = """
    INSERT INTO documents (id, title, file_path, page_count, status, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
    ON CONFLICT (id) DO NOTHING
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (document_id, title, file_path, page_count, status))
    except psycopg2.Error as exc:
        raise DocumentStoreError("failed to ensure document") from exc


def insert_document_version(document_id: str, version_no: int, label: Optional[str]) -> int:
    query = """
    INSERT INTO document_versions (document_id, version_no, label, created_at)
    VALUES (%s, %s, %s, NOW())
    RETURNING id
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (document_id, version_no, label))
                row = cur.fetchone()
                if not row:
                    raise DocumentStoreError("failed to insert document version")
                return int(row[0])
    except psycopg2.Error as exc:
        if exc.pgcode == "23505":
            raise DocumentVersionConflict("document version conflict") from exc
        raise DocumentStoreError("failed to insert document version") from exc
