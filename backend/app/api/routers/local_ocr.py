from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Body, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.core.config import settings
from app.services.lab_client import (
    LabApiError,
    LabApiNotFound,
    LabApiTimeout,
    cancel_ocr_job,
    create_ocr_job,
    create_vlm_session,
    create_vlm_sessions_batch,
    get_binary,
    get_ocr_job,
    get_ocr_results,
    get_vlm_session,
    post_vlm_message,
    # Extraction APIs
    start_extraction,
    get_extraction_status,
    get_extraction_result,
    get_extraction_llm_calls,
    get_extraction_by_ocr_run,
    update_image_selection,
    # History APIs
    get_run_history,
    get_run_history_detail,
    delete_run_history,
    # License API
    get_license_status,
    get_fingerprint,
    upload_license,
)
from app.services.local_db import DocumentStoreError, DocumentVersionConflict, ensure_document_exists, get_latest_version, insert_document_version
from app.services.local_ocr_state import (
    get_latest_doc_version,
    get_local_job_state,
    set_latest_doc_version,
    set_local_job_state,
    update_local_job_state,
)
from app.services.local_vlm_tokens import TokenStoreError, get_session_token_totals, get_tokens_for_sessions


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/local/ocr", tags=["Local OCR"])

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


def _is_pdf_upload(file: UploadFile) -> bool:
    if file.content_type == "application/pdf":
        return True
    filename = (file.filename or "").lower()
    return filename.endswith(".pdf")


def _build_response(state: Dict[str, Any], *, source: str, warning: Optional[str] = None) -> Dict[str, Any]:
    response = {
        "local_job_id": state.get("local_job_id"),
        "lab_job_id": state.get("lab_job_id"),
        "status": state.get("status"),
        "step": state.get("step"),
        "document_id": state.get("document_id"),
        "document_version_id": state.get("document_version_id"),
        "document_version_no": state.get("document_version_no"),
        "ocr_run_id": state.get("ocr_run_id"),
        "progress": state.get("progress"),
        "output_dir": state.get("output_dir"),
        "error_code": state.get("error_code"),
        "error_message": state.get("error_message"),
        "updated_at": state.get("updated_at"),
        "source": source,
    }
    if warning:
        response["warning"] = warning
    return response


def _proxy_lab_binary(path: str) -> Response:
    try:
        content, content_type = get_binary(path)
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return Response(content=content, media_type=content_type)


def _hash_document_id(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _reserve_document_version(document_id: str, original_filename: str) -> Tuple[int, int]:
    cached_version = get_latest_doc_version(document_id)
    if cached_version is None:
        try:
            cached_version = get_latest_version(document_id)
        except DocumentStoreError:
            cached_version = None

    next_version = (cached_version or 0) + 1
    filename = original_filename or "document.pdf"
    ext = ".pdf" if not filename.lower().endswith(".pdf") else ""
    file_path = f"{settings.local_upload_root.rstrip('/')}/{document_id}{ext}"
    page_count = 0
    status = "uploaded"
    attempts = 0
    while attempts < 2:
        try:
            ensure_document_exists(document_id, filename, file_path, page_count, status)
            version_id = insert_document_version(document_id, next_version, original_filename)
            set_latest_doc_version(document_id, next_version)
            return version_id, next_version
        except DocumentVersionConflict:
            attempts += 1
            latest = get_latest_version(document_id)
            next_version = (latest or 0) + 1
        except DocumentStoreError as exc:
            logger.exception("DB error while reserving document version")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="failed to reserve document version")


@router.post("/jobs")
async def create_local_ocr_job(
    file: Optional[UploadFile] = File(None),
) -> Dict[str, Any]:
    request_t0 = time.perf_counter()
    if file is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is required")

    if not _is_pdf_upload(file):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="only pdf is supported")

    read_t0 = time.perf_counter()
    file_bytes = await file.read()
    await file.close()
    logger.info(
        "[OCR] local backend received upload filename=%s bytes=%d read_ms=%d",
        file.filename,
        len(file_bytes),
        int((time.perf_counter() - read_t0) * 1000),
    )
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is empty")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file is too large")

    document_id = _hash_document_id(file_bytes)
    document_version_id, document_version_no = _reserve_document_version(document_id, file.filename or "document.pdf")
    output_folder_name = f"{document_id}_v{document_version_no}"

    local_job_id = str(uuid.uuid4())
    created_at = int(time.time())
    base_state = {
        "local_job_id": local_job_id,
        "lab_job_id": None,
        "document_id": document_id,
        "document_version_id": document_version_id,
        "document_version_no": document_version_no,
        "ocr_run_id": None,
        "status": "creating",
        "step": "creating",
        "progress": 0.0,
        "output_dir": None,
        "cancel_requested": False,
        "error_code": None,
        "error_message": None,
        "created_at": created_at,
    }
    set_local_job_state(local_job_id, base_state)

    try:
        lab_t0 = time.perf_counter()
        lab_response = create_ocr_job(
            file_bytes=file_bytes,
            filename=file.filename or "document.pdf",
            document_id=document_id,
            document_version_id=document_version_id,
            output_folder_name=output_folder_name,
        )
        logger.info(
            "[OCR] local backend lab create returned local_job_id=%s lab_job_id=%s elapsed_ms=%d",
            local_job_id,
            lab_response.get("job_id") or lab_response.get("lab_job_id"),
            int((time.perf_counter() - lab_t0) * 1000),
        )
    except LabApiTimeout as exc:
        logger.exception("Lab API timeout on create")
        update_local_job_state(
            local_job_id,
            {
                "status": "error",
                "step": "error",
                "error_code": "lab_timeout",
                "error_message": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"message": "lab api timeout", "local_job_id": local_job_id},
        ) from exc
    except LabApiError as exc:
        logger.exception("Lab API error on create")
        update_local_job_state(
            local_job_id,
            {
                "status": "error",
                "step": "error",
                "error_code": "lab_bad_gateway",
                "error_message": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "lab api error", "local_job_id": local_job_id},
        ) from exc

    lab_job_id = lab_response.get("job_id") or lab_response.get("lab_job_id")
    if not lab_job_id:
        update_local_job_state(
            local_job_id,
            {
                "status": "error",
                "step": "error",
                "error_code": "lab_invalid_response",
                "error_message": "missing job_id from lab response",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "lab api returned invalid response", "local_job_id": local_job_id},
        )

    ocr_run_id = lab_response.get("ocr_run_id")
    status_value = lab_response.get("status") or "queued"
    step_value = lab_response.get("step") or status_value
    output_dir = lab_response.get("output_dir")
    progress_value = lab_response.get("progress", 0.0)

    update_local_job_state(
        local_job_id,
        {
            "lab_job_id": lab_job_id,
            "ocr_run_id": ocr_run_id,
            "status": status_value,
            "step": step_value,
            "progress": progress_value,
            "output_dir": output_dir,
            "error_code": None,
            "error_message": None,
            "document_version_id": document_version_id,
            "document_version_no": document_version_no,
        },
    )

    total_ms = int((time.perf_counter() - request_t0) * 1000)
    logger.info(
        "[OCR] local backend create complete local_job_id=%s lab_job_id=%s total_ms=%d",
        local_job_id,
        lab_job_id,
        total_ms,
    )
    return {
        "local_job_id": local_job_id,
        "lab_job_id": lab_job_id,
        "ocr_run_id": ocr_run_id,
        "status": status_value,
        "output_dir": output_dir,
        "document_id": document_id,
        "document_version_id": document_version_id,
        "document_version_no": document_version_no,
        "created_at": created_at,
        "timing": {"route_ms": total_ms},
    }


_TERMINAL_STATUSES = {"succeeded", "done", "completed", "failed", "error", "canceled"}


@router.get("/jobs/{local_job_id}")
def get_local_ocr_job(local_job_id: str) -> Dict[str, Any]:
    local_state = get_local_job_state(local_job_id)
    if local_state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="local_job_id not found")

    lab_job_id = local_state.get("lab_job_id")
    if not lab_job_id:
        return _build_response(local_state, source="local", warning="lab_job_id_missing")

    # 已結束的任務直接回傳本地快取，不再打 lab_service
    local_status = (local_state.get("status") or "").lower()
    if local_status in _TERMINAL_STATUSES:
        return _build_response(local_state, source="local_cached")

    try:
        lab_state = get_ocr_job(lab_job_id=lab_job_id)
    except LabApiNotFound:
        return _build_response(local_state, source="local", warning="lab_job_not_found")
    except LabApiTimeout as exc:
        logger.exception("Lab API timeout on get")
        update_local_job_state(
            local_job_id,
            {
                "status": "error",
                "step": "error",
                "error_code": "lab_timeout",
                "error_message": str(exc),
            },
        )
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="lab api timeout") from exc
    except LabApiError as exc:
        logger.exception("Lab API error on get")
        update_local_job_state(
            local_job_id,
            {
                "status": "error",
                "step": "error",
                "error_code": "lab_bad_gateway",
                "error_message": str(exc),
            },
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="lab api error") from exc

    merged_state = dict(local_state)
    for key in [
        "status",
        "step",
        "progress",
        "output_dir",
        "error_code",
        "error_message",
        "ocr_run_id",
        "document_id",
        "document_version_id",
        "document_version_no",
    ]:
        if key in lab_state:
            merged_state[key] = lab_state[key]

    local_progress = local_state.get("progress")
    lab_progress = lab_state.get("progress")
    if isinstance(local_progress, (int, float)) and isinstance(lab_progress, (int, float)):
        merged_state["progress"] = max(local_progress, lab_progress)

    update_local_job_state(local_job_id, merged_state)
    updated_state = get_local_job_state(local_job_id) or merged_state
    return _build_response(updated_state, source="lab")


@router.post("/jobs/{local_job_id}/cancel")
def cancel_local_ocr_job(local_job_id: str) -> Dict[str, Any]:
    local_state = get_local_job_state(local_job_id)
    if local_state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="local_job_id not found")

    lab_job_id = local_state.get("lab_job_id")
    if lab_job_id:
        try:
            cancel_ocr_job(lab_job_id=lab_job_id)
        except LabApiTimeout as exc:
            logger.exception("Lab API timeout on cancel")
            update_local_job_state(
                local_job_id,
                {
                    "error_code": "lab_timeout",
                    "error_message": str(exc),
                },
            )
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="lab api timeout") from exc
        except LabApiError as exc:
            logger.exception("Lab API error on cancel")
            update_local_job_state(
                local_job_id,
                {
                    "error_code": "lab_bad_gateway",
                    "error_message": str(exc),
                },
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="lab api error") from exc

    updated = update_local_job_state(local_job_id, {"cancel_requested": True})
    return {
        "local_job_id": local_job_id,
        "lab_job_id": lab_job_id,
        "cancel_requested": True,
        "updated_at": (updated or {}).get("updated_at"),
    }


@router.get("/jobs/{local_job_id}/results")
def get_local_ocr_results(local_job_id: str) -> Dict[str, Any]:
    local_state = get_local_job_state(local_job_id)
    if local_state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="local_job_id not found")

    ocr_run_id = local_state.get("ocr_run_id")
    if not ocr_run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ocr_run_id not ready")

    try:
        return get_ocr_results(ocr_run_id=int(ocr_run_id))
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/results/images/{image_id}")
def get_local_ocr_image(image_id: str) -> Response:
    return _proxy_lab_binary(f"/results/ocr/images/{image_id}")


@router.get("/results/pages/{page_id}/render_image")
def get_local_page_render_image(page_id: str) -> Response:
    return _proxy_lab_binary(f"/results/ocr/pages/{page_id}/render_image")


@router.get("/results/artifacts/{artifact_id}/vis_image")
def get_local_artifact_vis(artifact_id: str) -> Response:
    return _proxy_lab_binary(f"/results/ocr/artifacts/{artifact_id}/vis_image")


@router.get("/results/artifacts/{artifact_id}/result_json")
def get_local_artifact_json(artifact_id: str) -> Response:
    return _proxy_lab_binary(f"/results/ocr/artifacts/{artifact_id}/result_json")


@router.get("/results/artifacts/{artifact_id}/result_md")
def get_local_artifact_md(artifact_id: str) -> Response:
    return _proxy_lab_binary(f"/results/ocr/artifacts/{artifact_id}/result_md")


@router.post("/vlm/sessions")
def create_local_vlm_session(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    trace_id = str(payload.get("trace_id") or uuid.uuid4().hex[:12])
    payload = {**payload, "trace_id": trace_id}
    t0 = time.perf_counter()
    logger.info(
        "[VLM][%s] local backend /vlm/sessions received image_id=%s",
        trace_id,
        payload.get("image_id"),
    )
    try:
        result = create_vlm_session(payload)
        logger.info(
            "[VLM][%s] local backend /vlm/sessions complete elapsed_ms=%d",
            trace_id,
            int((time.perf_counter() - t0) * 1000),
        )
        return result
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/vlm/sessions/batch")
def create_local_vlm_sessions_batch(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Batch create VLM sessions for multiple images concurrently."""
    trace_id = str(payload.get("trace_id") or uuid.uuid4().hex[:12])
    payload = {**payload, "trace_id": trace_id}
    t0 = time.perf_counter()
    logger.info(
        "[VLM][%s] local backend /vlm/sessions/batch received total=%d",
        trace_id,
        len(payload.get("image_ids") or []),
    )
    try:
        result = create_vlm_sessions_batch(payload)
        logger.info(
            "[VLM][%s] local backend /vlm/sessions/batch complete elapsed_ms=%d",
            trace_id,
            int((time.perf_counter() - t0) * 1000),
        )
        return result
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/vlm/sessions/{session_id}")
def get_local_vlm_session(session_id: str) -> Dict[str, Any]:
    try:
        return get_vlm_session(session_id)
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/vlm/sessions/{session_id}/messages")
def post_local_vlm_message(session_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    trace_id = str(payload.get("trace_id") or uuid.uuid4().hex[:12])
    payload = {**payload, "trace_id": trace_id}
    t0 = time.perf_counter()
    logger.info(
        "[VLM][%s] local backend /vlm/sessions/%s/messages received role=%s",
        trace_id,
        session_id,
        payload.get("role"),
    )
    try:
        result = post_vlm_message(session_id, payload)
        logger.info(
            "[VLM][%s] local backend /vlm/sessions/%s/messages complete elapsed_ms=%d",
            trace_id,
            session_id,
            int((time.perf_counter() - t0) * 1000),
        )
        return result
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/vlm/sessions/{session_id}/tokens")
def get_local_vlm_session_tokens(session_id: str) -> Dict[str, Any]:
    try:
        return get_session_token_totals(session_id)
    except TokenStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/vlm/tokens")
def get_local_vlm_tokens(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    session_ids = payload.get("session_ids")
    if session_ids is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_ids is required")
    if not isinstance(session_ids, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_ids must be a list")
    session_ids = [str(item) for item in session_ids if item]
    try:
        return get_tokens_for_sessions(session_ids)
    except TokenStoreError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# ========== 結構化萃取 API ==========

@router.post("/extraction/start")
def start_local_extraction(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """開始結構化萃取"""
    try:
        return start_extraction(payload)
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/extraction/{extraction_id}")
def get_local_extraction_status(extraction_id: int) -> Dict[str, Any]:
    """取得萃取狀態"""
    try:
        return get_extraction_status(extraction_id)
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/extraction/{extraction_id}/result")
def get_local_extraction_result(extraction_id: int) -> Dict[str, Any]:
    """取得萃取結果 JSON"""
    try:
        return get_extraction_result(extraction_id)
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/extraction/{extraction_id}/llm-calls")
def get_local_extraction_llm_calls(extraction_id: int) -> Dict[str, Any]:
    """取得萃取 LLM 呼叫記錄"""
    try:
        return get_extraction_llm_calls(extraction_id)
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/extraction/by-ocr/{ocr_run_id}")
def get_local_extraction_by_ocr_run(ocr_run_id: int) -> Dict[str, Any]:
    """根據 OCR Run ID 取得最新萃取記錄"""
    try:
        return get_extraction_by_ocr_run(ocr_run_id)
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/extraction/{extraction_id}/update-selection")
def update_local_image_selection(extraction_id: int, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """更新圖片選擇狀態"""
    try:
        return update_image_selection(extraction_id, payload)
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ========== 歷史紀錄 API ==========

@router.get("/history")
def get_local_history(limit: int = 30, offset: int = 0) -> Dict[str, Any]:
    """取得合併的歷史紀錄（近期 Redis + 歷史 DB）"""
    try:
        # 從 lab_service DB 取得歷史
        db_history = get_run_history(limit=limit, offset=offset)

        # 標記近期項目（Redis 中還有 job state）
        items = db_history.get("items", [])
        for item in items:
            # 嘗試在 Redis 找到對應的 local job
            # (透過 document_id 匹配)
            item["is_recent"] = False  # 預設為歷史

        # 掃描 Redis 尋找近期 jobs
        try:
            from app.services.local_ocr_state import _redis, _STATE_PREFIX
            import json
            cursor = 0
            recent_doc_ids = {}
            while True:
                cursor, keys = _redis.scan(cursor, match=f"{_STATE_PREFIX}*", count=100)
                for key in keys:
                    raw = _redis.get(key)
                    if raw:
                        state = json.loads(raw)
                        doc_id = state.get("document_id")
                        if doc_id:
                            recent_doc_ids[doc_id] = state.get("local_job_id")
                if cursor == 0:
                    break

            # 標記近期項目
            for item in items:
                if item.get("document_id") in recent_doc_ids:
                    item["is_recent"] = True
                    item["local_job_id"] = recent_doc_ids[item["document_id"]]
        except Exception:
            pass  # Redis 不可用則全部視為歷史

        return db_history
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/history/{ocr_run_id}/restore")
def restore_history_run(ocr_run_id: int) -> Dict[str, Any]:
    """還原歷史工作流 — 取得完整的 OCR + Extraction 資料供前端還原"""
    try:
        detail = get_run_history_detail(ocr_run_id)

        # 如果有 extraction run，也取得 extraction result
        extraction_result = None
        ext = detail.get("extraction_run")
        if ext and ext.get("id") and ext.get("status") == "completed":
            try:
                from app.services.lab_client import get_extraction_result
                extraction_result = get_extraction_result(ext["id"])
            except Exception:
                pass  # Extraction result 可能不存在

        return {
            **detail,
            "extraction_result": extraction_result,
        }
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.delete("/history/{ocr_run_id}")
def delete_local_history_run(ocr_run_id: int) -> Dict[str, Any]:
    """刪除指定的 OCR 執行紀錄及所有相關資料"""
    try:
        result = delete_run_history(ocr_run_id)

        # 清理 Redis 中對應的 local job state
        try:
            from app.services.local_ocr_state import _redis, _STATE_PREFIX
            import json
            cursor = 0
            while True:
                cursor, keys = _redis.scan(cursor, match=f"{_STATE_PREFIX}*", count=100)
                for key in keys:
                    raw = _redis.get(key)
                    if raw:
                        state = json.loads(raw)
                        if state.get("document_id") == result.get("document_id"):
                            _redis.delete(key)
                if cursor == 0:
                    break
        except Exception:
            pass  # Redis cleanup is best-effort

        return result
    except LabApiNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


# ========== License API ==========

@router.get("/license/status")
def get_local_license_status() -> Dict[str, Any]:
    """取得 license 授權狀態"""
    try:
        return get_license_status()
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/license/fingerprint")
def get_local_fingerprint() -> Dict[str, Any]:
    """取得硬體指紋"""
    try:
        return get_fingerprint()
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/license/upload")
async def upload_local_license(file: UploadFile) -> Dict[str, Any]:
    """上傳 license 檔案"""
    content = await file.read()
    try:
        return upload_license(content, file.filename)
    except LabApiTimeout as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except LabApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
