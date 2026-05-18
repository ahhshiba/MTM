from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from typing import Any, Dict, Generator, Optional, Tuple

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class LabApiError(Exception):
    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class LabApiTimeout(LabApiError):
    pass


class LabApiNotFound(LabApiError):
    pass


# 模組層級共用連線池，避免每次 API 呼叫都建立新 TCP 連線
_shared_client: httpx.Client | None = None


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _payload_trace_id(payload: Dict[str, Any]) -> str:
    return str(payload.get("trace_id") or "-")


def _client() -> httpx.Client:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.Client(
            base_url=settings.lab_api_base_url,
            timeout=settings.lab_http_timeout_seconds,
        )
    return _shared_client


@contextmanager
def _get_client() -> Generator[httpx.Client, None, None]:
    """Context manager that yields the shared client without closing it."""
    yield _client()


def _parse_response(resp: httpx.Response) -> Dict[str, Any]:
    if resp.status_code == 404:
        raise LabApiNotFound(
            f"lab job not found: {resp.text}",
            status_code=resp.status_code,
        )
    if resp.status_code >= 500:
        raise LabApiError(
            f"lab server error: {resp.text}",
            status_code=resp.status_code,
        )
    if resp.status_code >= 400:
        raise LabApiError(
            f"lab request rejected: {resp.text}",
            status_code=resp.status_code,
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise LabApiError(
            f"lab response is not valid json: {resp.text}",
            status_code=resp.status_code,
        ) from exc


def _raw_response(resp: httpx.Response) -> httpx.Response:
    if resp.status_code == 404:
        raise LabApiNotFound(
            f"lab resource not found: {resp.text}",
            status_code=resp.status_code,
        )
    if resp.status_code >= 500:
        raise LabApiError(
            f"lab server error: {resp.text}",
            status_code=resp.status_code,
        )
    if resp.status_code >= 400:
        raise LabApiError(
            f"lab request rejected: {resp.text}",
            status_code=resp.status_code,
        )
    return resp

def create_ocr_job(
    *,
    file_bytes: bytes,
    filename: str,
    document_id: str,
    document_version_id: int,
    output_folder_name: Optional[str],
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    data = {
        "document_id": document_id,
        "document_version_id": str(document_version_id),
    }
    if output_folder_name:
        data["output_folder_name"] = output_folder_name

    files = {
        "file": (filename or "document.pdf", file_bytes, "application/pdf"),
    }

    try:
        with _get_client() as client:
            logger.info(f"Sending OCR job to lab service: document_id={document_id}, version={document_version_id}")
            resp = client.post("/jobs/ocr", data=data, files=files)
            logger.info(
                "Lab service OCR create response: status=%s elapsed_ms=%d",
                resp.status_code,
                _duration_ms(t0),
            )
            if resp.status_code >= 400:
                logger.error(f"Lab service error response: {resp.text}")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        logger.error("Lab service OCR create timeout elapsed_ms=%d error=%s", _duration_ms(t0), exc)
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        logger.error("Lab service OCR create request error elapsed_ms=%d error=%s", _duration_ms(t0), exc)
        raise LabApiError(f"lab request failed: {exc}") from exc


def get_ocr_job(*, lab_job_id: str) -> Dict[str, Any]:
    try:
        with _get_client() as client:
            resp = client.get(f"/jobs/ocr/{lab_job_id}")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def cancel_ocr_job(*, lab_job_id: str) -> Dict[str, Any]:
    try:
        with _get_client() as client:
            resp = client.post(f"/jobs/ocr/{lab_job_id}/cancel")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_ocr_results(*, ocr_run_id: int) -> Dict[str, Any]:
    try:
        with _get_client() as client:
            resp = client.get(f"/results/ocr/{ocr_run_id}")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_binary(path: str) -> Tuple[bytes, str]:
    try:
        with _get_client() as client:
            resp = client.get(path)
            resp = _raw_response(resp)
            content_type = resp.headers.get("content-type") or "application/octet-stream"
            return resp.content, content_type
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def create_vlm_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    trace_id = _payload_trace_id(payload)
    try:
        with _get_client() as client:
            logger.info(
                "[VLM][%s] local->lab POST /vlm/sessions start image_id=%s timeout_s=%s",
                trace_id,
                payload.get("image_id"),
                settings.lab_http_timeout_seconds,
            )
            resp = client.post("/vlm/sessions", json=payload)
            logger.info(
                "[VLM][%s] local->lab POST /vlm/sessions done status=%s elapsed_ms=%d",
                trace_id,
                resp.status_code,
                _duration_ms(t0),
            )
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        logger.error(
            "[VLM][%s] local->lab POST /vlm/sessions timeout elapsed_ms=%d",
            trace_id,
            _duration_ms(t0),
        )
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        logger.error(
            "[VLM][%s] local->lab POST /vlm/sessions failed elapsed_ms=%d error=%s",
            trace_id,
            _duration_ms(t0),
            exc,
        )
        raise LabApiError("lab request failed") from exc


def get_vlm_session(session_id: str) -> Dict[str, Any]:
    try:
        with _get_client() as client:
            resp = client.get(f"/vlm/sessions/{session_id}")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def post_vlm_message(session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    trace_id = _payload_trace_id(payload)
    try:
        with _get_client() as client:
            logger.info(
                "[VLM][%s] local->lab POST /vlm/sessions/%s/messages start timeout_s=%s",
                trace_id,
                session_id,
                settings.lab_http_timeout_seconds,
            )
            resp = client.post(f"/vlm/sessions/{session_id}/messages", json=payload)
            logger.info(
                "[VLM][%s] local->lab POST /vlm/sessions/%s/messages done status=%s elapsed_ms=%d",
                trace_id,
                session_id,
                resp.status_code,
                _duration_ms(t0),
            )
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        logger.error(
            "[VLM][%s] local->lab POST /vlm/sessions/%s/messages timeout elapsed_ms=%d",
            trace_id,
            session_id,
            _duration_ms(t0),
        )
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        logger.error(
            "[VLM][%s] local->lab POST /vlm/sessions/%s/messages failed elapsed_ms=%d error=%s",
            trace_id,
            session_id,
            _duration_ms(t0),
            exc,
        )
        raise LabApiError("lab request failed") from exc


def create_vlm_sessions_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create VLM sessions for multiple images concurrently via lab_service."""
    t0 = time.perf_counter()
    trace_id = _payload_trace_id(payload)
    timeout_s = settings.lab_vlm_batch_timeout_seconds
    try:
        client = _client()
        logger.info(
            "[VLM][%s] local->lab POST /vlm/sessions/batch start total=%d timeout_s=%s",
            trace_id,
            len(payload.get("image_ids") or []),
            timeout_s,
        )
        resp = client.post(
            "/vlm/sessions/batch",
            json=payload,
            timeout=timeout_s,
        )
        logger.info(
            "[VLM][%s] local->lab POST /vlm/sessions/batch done status=%s elapsed_ms=%d",
            trace_id,
            resp.status_code,
            _duration_ms(t0),
        )
        return _parse_response(resp)
    except httpx.TimeoutException as exc:
        logger.error(
            "[VLM][%s] local->lab POST /vlm/sessions/batch timeout elapsed_ms=%d",
            trace_id,
            _duration_ms(t0),
        )
        raise LabApiTimeout("lab batch request timed out") from exc
    except httpx.RequestError as exc:
        logger.error(
            "[VLM][%s] local->lab POST /vlm/sessions/batch failed elapsed_ms=%d error=%s",
            trace_id,
            _duration_ms(t0),
            exc,
        )
        raise LabApiError("lab batch request failed") from exc


# ========== 結構化萃取 API ==========

def start_extraction(payload: Dict[str, Any]) -> Dict[str, Any]:
    """開始結構化萃取"""
    try:
        with _get_client() as client:
            resp = client.post("/extraction/start", json=payload)
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_extraction_status(extraction_id: int) -> Dict[str, Any]:
    """取得萃取狀態"""
    try:
        with _get_client() as client:
            resp = client.get(f"/extraction/{extraction_id}")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_extraction_result(extraction_id: int) -> Dict[str, Any]:
    """取得萃取結果 JSON"""
    try:
        client = _client()
        resp = client.get(
            f"/extraction/{extraction_id}/result",
            timeout=settings.lab_http_timeout_seconds * 2,
        )
        return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_extraction_llm_calls(extraction_id: int) -> Dict[str, Any]:
    """取得萃取 LLM 呼叫記錄"""
    try:
        with _get_client() as client:
            resp = client.get(f"/extraction/{extraction_id}/llm-calls")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_extraction_by_ocr_run(ocr_run_id: int) -> Dict[str, Any]:
    """根據 OCR Run ID 取得最新萃取記錄"""
    try:
        with _get_client() as client:
            resp = client.get(f"/extraction/by-ocr/{ocr_run_id}")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def update_image_selection(extraction_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """更新圖片選擇狀態"""
    try:
        with _get_client() as client:
            resp = client.post(f"/extraction/{extraction_id}/update-selection", json=payload)
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


# ========== 歷史紀錄 API ==========

def get_run_history(limit: int = 30, offset: int = 0) -> Dict[str, Any]:
    """取得 OCR 執行歷史紀錄"""
    try:
        with _get_client() as client:
            resp = client.get("/jobs/history", params={"limit": limit, "offset": offset})
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_run_history_detail(ocr_run_id: int) -> Dict[str, Any]:
    """取得單筆 OCR Run 的完整還原資訊"""
    try:
        with _get_client() as client:
            resp = client.get(f"/jobs/history/{ocr_run_id}/detail")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def delete_run_history(ocr_run_id: int) -> Dict[str, Any]:
    """刪除指定 OCR Run 及所有相關資料"""
    try:
        with _get_client() as client:
            resp = client.delete(f"/jobs/history/{ocr_run_id}")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_license_status() -> Dict[str, Any]:
    """取得 license 授權狀態"""
    try:
        with _get_client() as client:
            resp = client.get("/license/status")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def get_fingerprint() -> Dict[str, Any]:
    """取得硬體指紋"""
    try:
        with _get_client() as client:
            resp = client.get("/license/fingerprint")
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc


def upload_license(file_content: bytes, filename: str) -> Dict[str, Any]:
    """上傳 license 檔案"""
    try:
        with _get_client() as client:
            resp = client.post(
                "/license/upload",
                files={"file": (filename, file_content, "application/octet-stream")},
            )
            return _parse_response(resp)
    except httpx.TimeoutException as exc:
        raise LabApiTimeout("lab request timed out") from exc
    except httpx.RequestError as exc:
        raise LabApiError("lab request failed") from exc
