# app/api/extraction.py
"""結構化萃取 API"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from app.config import settings
from app.db.models import ExtractionRun, ExtractionLLMCall, OCRRun, Image
from app.db.session import SessionLocal
from app.redis.state import set_job_state, get_job_state
from app.services.extraction.extractor import run_extraction_task, TechPackExtractor


router = APIRouter(prefix="/extraction", tags=["extraction"])


class ExtractionStartRequest(BaseModel):
    ocr_run_id: int
    document_id: str
    mode: str = "auto"  # auto, developer
    model: str = "gemini-2.5-flash"


class ImageSelectionRequest(BaseModel):
    image_ids: List[int]
    selected: bool


def _extraction_key(extraction_id: int) -> str:
    return f"extraction:{extraction_id}"


def _run_extraction_background(
    extraction_run_id: int,
    ocr_run_id: int,
    document_id: str,
    mode: str,
    model: str,
):
    """背景執行萃取任務"""
    import traceback
    try:
        # 更新 Redis 狀態
        set_job_state(_extraction_key(extraction_run_id), {
            "status": "running",
            "extraction_run_id": extraction_run_id,
            "ocr_run_id": ocr_run_id,
            "progress": 0,
        })
        
        # 建立 extractor
        extractor = TechPackExtractor(
            ocr_run_id=ocr_run_id,
            document_id=document_id,
            mode=mode,
            model=model,
        )
        extractor.extraction_run_id = extraction_run_id
        
        # 執行萃取
        result = extractor.run_extraction()
        
        # 更新 Redis 狀態
        if result.get("success"):
            summary = result.get("summary") or {}
            set_job_state(_extraction_key(extraction_run_id), {
                "status": "completed",
                "extraction_run_id": extraction_run_id,
                "ocr_run_id": ocr_run_id,
                "progress": 1.0,
                "bbox_result_path": result.get("bbox_result_path"),
                "summary": summary,
                # 前端直接讀取這些欄位
                "total_tokens": summary.get("llm_tokens_used", 0),
                "total_prompt_tokens": summary.get("llm_input_tokens", 0),
                "total_candidate_tokens": summary.get("llm_output_tokens", 0),
            })
        else:
            error_msg = result.get("error", "Unknown extraction error")
            set_job_state(_extraction_key(extraction_run_id), {
                "status": "failed",
                "extraction_run_id": extraction_run_id,
                "ocr_run_id": ocr_run_id,
                "error": error_msg,
                "error_message": error_msg,  # Frontend reads this field
            })
            
    except Exception as e:
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(f"[Extraction Error] {error_msg}")  # Log to console
        set_job_state(_extraction_key(extraction_run_id), {
            "status": "failed",
            "extraction_run_id": extraction_run_id,
            "error": error_msg,
            "error_message": str(e),  # Frontend reads this field
        })


@router.post("/start")
def start_extraction(payload: ExtractionStartRequest):
    """
    開始結構化萃取
    
    非同步執行，透過 Redis 追蹤狀態
    """
    db = SessionLocal()
    try:
        # 驗證 OCR Run 存在
        ocr_run = db.query(OCRRun).filter(OCRRun.id == payload.ocr_run_id).first()
        if not ocr_run:
            raise HTTPException(status_code=404, detail="OCR Run not found")
        
        # 接受多種完成狀態
        completed_statuses = ["done", "completed", "succeeded", "finished"]
        db_status = (ocr_run.status or "").lower()
        
        # 如果資料庫狀態不是完成，也檢查 Redis
        is_completed = db_status in completed_statuses
        if not is_completed:
            # 嘗試從 Redis 檢查狀態
            redis_state = get_job_state(f"ocr:job:{payload.ocr_run_id}")
            if redis_state:
                redis_status = (redis_state.get("status") or "").lower()
                is_completed = redis_status in completed_statuses
        
        if not is_completed:
            raise HTTPException(
                status_code=400, 
                detail=f"OCR Run is not completed (current status: {ocr_run.status})"
            )
        
        # 檢查是否已有進行中的萃取
        existing = db.query(ExtractionRun).filter(
            ExtractionRun.ocr_run_id == payload.ocr_run_id,
            ExtractionRun.status.in_(["pending", "running"])
        ).first()
        
        if existing:
            return {
                "extraction_run_id": existing.id,
                "status": existing.status,
                "message": "Extraction already in progress",
            }
        
        # 建立萃取記錄
        run = ExtractionRun(
            ocr_run_id=payload.ocr_run_id,
            document_id=payload.document_id,
            status="pending",
            model=payload.model,
            mode=payload.mode,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        
        extraction_run_id = run.id
        
        # 初始化 Redis 狀態
        set_job_state(_extraction_key(extraction_run_id), {
            "status": "pending",
            "extraction_run_id": extraction_run_id,
            "ocr_run_id": payload.ocr_run_id,
            "progress": 0,
        })
        
        # 啟動背景任務
        thread = threading.Thread(
            target=_run_extraction_background,
            args=(
                extraction_run_id,
                payload.ocr_run_id,
                payload.document_id,
                payload.mode,
                payload.model,
            ),
            daemon=True,
        )
        thread.start()
        
        return {
            "extraction_run_id": extraction_run_id,
            "status": "pending",
            "message": "Extraction started",
        }
        
    finally:
        db.close()


@router.get("/{extraction_id}")
def get_extraction_status(extraction_id: int):
    """取得萃取狀態"""
    # 先查 Redis
    redis_state = get_job_state(_extraction_key(extraction_id))
    if redis_state:
        return redis_state
    
    # 查資料庫
    db = SessionLocal()
    try:
        run = db.query(ExtractionRun).filter(ExtractionRun.id == extraction_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Extraction run not found")
        
        return {
            "extraction_run_id": run.id,
            "ocr_run_id": run.ocr_run_id,
            "document_id": run.document_id,
            "status": run.status,
            "model": run.model,
            "mode": run.mode,
            "total_tokens": run.total_tokens,
            "total_prompt_tokens": run.total_prompt_tokens,
            "total_candidate_tokens": run.total_candidate_tokens,
            "raw_result_path": run.raw_result_path,
            "bbox_result_path": run.bbox_result_path,
            "error_message": run.error_message,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
    finally:
        db.close()


@router.get("/{extraction_id}/result")
def get_extraction_result(extraction_id: int):
    """取得結構化萃取結果 JSON"""
    db = SessionLocal()
    try:
        run = db.query(ExtractionRun).filter(ExtractionRun.id == extraction_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Extraction run not found")
        
        if run.status != "completed":
            raise HTTPException(
                status_code=400, 
                detail=f"Extraction not completed, current status: {run.status}"
            )
        
        result_path = run.bbox_result_path or run.structured_result_path
        if not result_path or not Path(result_path).exists():
            raise HTTPException(status_code=404, detail="Result file not found")
        
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return {
            "extraction_run_id": extraction_id,
            "result": data,
            "result_path": result_path,
            "token_usage": {
                "total_tokens": run.total_tokens,
                "prompt_tokens": run.total_prompt_tokens,
                "candidate_tokens": run.total_candidate_tokens,
            }
        }
    finally:
        db.close()


@router.get("/{extraction_id}/llm-calls")
def get_extraction_llm_calls(extraction_id: int):
    """取得萃取過程中的 LLM 呼叫記錄"""
    db = SessionLocal()
    try:
        calls = db.query(ExtractionLLMCall).filter(
            ExtractionLLMCall.extraction_run_id == extraction_id
        ).order_by(ExtractionLLMCall.id).all()
        
        return {
            "extraction_run_id": extraction_id,
            "calls": [
                {
                    "id": c.id,
                    "call_type": c.call_type,
                    "prompt_tokens": c.prompt_tokens,
                    "candidate_tokens": c.candidate_tokens,
                    "total_tokens": c.total_tokens,
                    "duration_ms": c.duration_ms,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in calls
            ]
        }
    finally:
        db.close()


@router.post("/{extraction_id}/update-selection")
def update_image_selection(extraction_id: int, payload: ImageSelectionRequest):
    """
    更新圖片選擇狀態 (開發者模式)
    """
    db = SessionLocal()
    try:
        # 驗證萃取記錄
        run = db.query(ExtractionRun).filter(ExtractionRun.id == extraction_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Extraction run not found")
        
        # 更新圖片選擇狀態
        updated_count = db.query(Image).filter(
            Image.id.in_(payload.image_ids)
        ).update(
            {"is_selected": payload.selected},
            synchronize_session=False
        )
        db.commit()
        
        return {
            "updated_count": updated_count,
            "image_ids": payload.image_ids,
            "selected": payload.selected,
        }
    finally:
        db.close()


@router.get("/by-ocr/{ocr_run_id}")
def get_extraction_by_ocr_run(ocr_run_id: int):
    """根據 OCR Run ID 取得最新萃取記錄"""
    db = SessionLocal()
    try:
        run = db.query(ExtractionRun).filter(
            ExtractionRun.ocr_run_id == ocr_run_id
        ).order_by(ExtractionRun.id.desc()).first()
        
        if not run:
            return {"extraction_run": None}
        
        return {
            "extraction_run": {
                "id": run.id,
                "extraction_run_id": run.id,
                "status": run.status,
                "total_tokens": run.total_tokens,
                "bbox_result_path": run.bbox_result_path,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
        }
    finally:
        db.close()
