# app/api/jobs.py
from __future__ import annotations

import logging
import threading
import uuid
import shutil
import time
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.config import settings
from app.redis.state import set_job_state, get_job_state, mark_canceled
from app.services.ocr_worker import submit_ocr_job

# DB
from app.db.session import SessionLocal
from app.db.models import OCRRun, Document, DocumentVersion, ExtractionRun, Page

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/jobs", tags=["jobs"])
UPLOAD_ROOT = Path(__file__).resolve().parents[1] / "upload_file"


# ==========
# Schemas
# ==========

class OCRJobCreateResponse(BaseModel):
    job_id: str
    ocr_run_id: int
    status: str
    output_dir: str


# ==========
# Routes
# ==========

@router.post("/ocr", response_model=OCRJobCreateResponse)
def create_job(
    document_id: str = Form(..., description="文件 ID"),
    document_version_id: int = Form(..., description="文件版本 ID"),
    output_folder_name: str = Form(..., description="OCR 輸出資料夾名稱"),
    file: UploadFile = File(..., description="PDF 檔案（multipart/form-data）"),
):
    """
    建立 OCR 任務（正式流程）
    1. 建立 OCRRun（DB，補齊所有 NOT NULL 欄位）
    2. 建立輸出資料夾
    3. Redis 寫入 job state
    4. 非同步送出 OCR worker
    """

    route_t0 = time.perf_counter()
    job_id = str(uuid.uuid4())
    logger.info(
        "[OCR][%s] lab /jobs/ocr received document_id=%s version_id=%s filename=%s",
        job_id[:8],
        document_id,
        document_version_id,
        file.filename,
    )

    # ---------- 資料夾名稱處理 ----------
    folder = output_folder_name.strip()
    if not folder:
        raise HTTPException(status_code=400, detail="output_folder_name is empty")

    # 防止路徑穿越
    folder = folder.replace("/", "_").replace("\\", "_").replace("..", "_")

    output_dir = Path(settings.OCR_DATA_ROOT) / folder
    output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 上傳檔案儲存 ----------
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    original_name = (file.filename or "uploaded.pdf").replace("/", "_").replace("\\", "_")
    if not original_name:
        original_name = "uploaded.pdf"
    suffix = Path(original_name).suffix or ".pdf"
    saved_path = UPLOAD_ROOT / f"{job_id}{suffix}"
    try:
        save_t0 = time.perf_counter()
        with saved_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(
            "[OCR][%s] lab upload saved path=%s elapsed_ms=%d",
            job_id[:8],
            saved_path,
            int((time.perf_counter() - save_t0) * 1000),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to save uploaded file: {e}")

    pdf_path = str(saved_path)

    # ---------- 1️ 建立 DB OCRRun ----------
    db = SessionLocal()
    try:
        db_t0 = time.perf_counter()
        doc = db.query(Document).filter(Document.id == document_id).one_or_none()
        if doc is None:
            # 自動建立文件主檔
            doc = Document(
                id=document_id,
                title=original_name,
                file_path=pdf_path,
                page_count=0,
                created_at=datetime.utcnow(),
            )
            db.add(doc)
        else:
            # 既有文件仍需更新為最新上傳路徑
            doc.file_path = pdf_path
            if not doc.title:
                doc.title = original_name
            if doc.page_count is None:
                doc.page_count = 0

        doc_version = db.query(DocumentVersion).filter(DocumentVersion.id == document_version_id).one_or_none()
        if doc_version is None:
            # 嘗試用 document_id + version_no=1 找既有版本，避免唯一鍵衝突
            existing_ver = (
                db.query(DocumentVersion)
                .filter(DocumentVersion.document_id == document_id, DocumentVersion.version_no == 1)
                .one_or_none()
            )
            if existing_ver:
                doc_version = existing_ver
                document_version_id = doc_version.id  # 後續沿用既有 id
            else:
                doc_version = DocumentVersion(
                    id=document_version_id,
                    document_id=document_id,
                    version_no=1,
                    created_at=datetime.utcnow(),
                )
                db.add(doc_version)
        elif doc_version.document_id != document_id:
            # ID 已存在但不屬於這份文件
            raise HTTPException(
                status_code=400,
                detail=f"document_version {document_version_id} not for document {document_id}",
            )

        ocr_run = OCRRun(
            document_id=document_id,
            document_version_id=document_version_id,
            status="queued",
            engine="paddleocr-vl",
            options_json={},
            output_dir_path=str(output_dir),
            created_at=datetime.utcnow(),
        )
        db.add(ocr_run)
        db.commit()
        db.refresh(ocr_run)
        ocr_run_id = ocr_run.id
        logger.info(
            "[OCR][%s] lab OCRRun created ocr_run_id=%s elapsed_ms=%d",
            job_id[:8],
            ocr_run_id,
            int((time.perf_counter() - db_t0) * 1000),
        )
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"DB create OCRRun failed: {e}",
        )
    finally:
        db.close()

    # ---------- 2️ Redis 初始化 job state ----------
    set_job_state(
        job_id,
        {
            "status": "queued",
            "step": "queued",
            "document_id": document_id,
            "document_version_id": document_version_id,
            "ocr_run_id": ocr_run_id,
            "output_dir": str(output_dir),
            "progress": 0.0,
        },
    )

    # ---------- 3️ 立即啟動 OCR worker thread ----------
    worker = threading.Thread(
        target=submit_ocr_job,
        kwargs=dict(
            job_id=job_id,
            document_id=document_id,
            document_version_id=document_version_id,
            pdf_path=pdf_path,
            ocr_run_id=ocr_run_id,
            output_dir=str(output_dir),
        ),
        daemon=True,
        name=f"ocr-worker-{job_id[:8]}",
    )
    worker.start()
    logger.info(
        "[OCR][%s] Worker thread started route_ms=%d",
        job_id[:8],
        int((time.perf_counter() - route_t0) * 1000),
    )

    # ---------- 4️ 立刻回傳 ----------
    return OCRJobCreateResponse(
        job_id=job_id,
        ocr_run_id=ocr_run_id,
        status="queued",
        output_dir=str(output_dir),
    )


@router.get("/ocr/{job_id}")
def get_ocr_job(job_id: str):
    """
    從 Redis 查詢 OCR 任務狀態
    """
    state = get_job_state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="job not found")
    return state


@router.post("/ocr/{job_id}/cancel")
def cancel_ocr_job(job_id: str):
    """
    標記 OCR 任務為取消（worker 會定期檢查）
    """
    state = get_job_state(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="job not found")

    mark_canceled(job_id)
    return {
        "job_id": job_id,
        "cancel_requested": True,
    }


@router.get("/history")
def get_ocr_history(limit: int = 30, offset: int = 0):
    """
    取得 OCR 執行歷史紀錄（從 DB 查詢）
    包含: document 標題、OCR 狀態、是否有 Extraction、token 統計
    """
    from sqlalchemy import func as sa_func, desc
    from sqlalchemy.orm import aliased

    db = SessionLocal()
    try:
        # Subquery: 每個 ocr_run 的最新 extraction
        latest_ext = (
            db.query(
                ExtractionRun.ocr_run_id,
                sa_func.max(ExtractionRun.id).label("latest_ext_id"),
            )
            .group_by(ExtractionRun.ocr_run_id)
            .subquery()
        )

        # Subquery: 每個 document 的 page count
        page_count_sub = (
            db.query(
                Page.document_id,
                sa_func.count(Page.id).label("page_count"),
            )
            .group_by(Page.document_id)
            .subquery()
        )

        rows = (
            db.query(
                OCRRun.id.label("ocr_run_id"),
                OCRRun.document_id,
                OCRRun.status.label("ocr_status"),
                OCRRun.started_at,
                OCRRun.finished_at,
                OCRRun.created_at,
                Document.title.label("document_title"),
                page_count_sub.c.page_count,
                latest_ext.c.latest_ext_id.label("extraction_run_id"),
                ExtractionRun.status.label("extraction_status"),
                ExtractionRun.total_tokens,
                ExtractionRun.model.label("extraction_model"),
            )
            .outerjoin(Document, OCRRun.document_id == Document.id)
            .outerjoin(page_count_sub, OCRRun.document_id == page_count_sub.c.document_id)
            .outerjoin(latest_ext, OCRRun.id == latest_ext.c.ocr_run_id)
            .outerjoin(ExtractionRun, ExtractionRun.id == latest_ext.c.latest_ext_id)
            .order_by(desc(OCRRun.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        total_count = db.query(sa_func.count(OCRRun.id)).scalar() or 0

        items = []
        for row in rows:
            items.append({
                "ocr_run_id": row.ocr_run_id,
                "document_id": row.document_id,
                "document_title": row.document_title or "Untitled",
                "ocr_status": row.ocr_status,
                "page_count": row.page_count or 0,
                "has_extraction": row.extraction_run_id is not None,
                "extraction_run_id": row.extraction_run_id,
                "extraction_status": row.extraction_status,
                "extraction_model": row.extraction_model,
                "total_tokens": row.total_tokens or 0,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })

        return {
            "items": items,
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }
    finally:
        db.close()


@router.get("/history/{ocr_run_id}/detail")
def get_ocr_history_detail(ocr_run_id: int):
    """
    取得單筆 OCR Run 的完整還原資訊
    用於前端還原歷史工作流
    """
    db = SessionLocal()
    try:
        ocr_run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).first()
        if not ocr_run:
            raise HTTPException(status_code=404, detail="OCR run not found")

        doc = db.query(Document).filter(Document.id == ocr_run.document_id).first()

        # 最新 extraction run
        ext_run = (
            db.query(ExtractionRun)
            .filter(ExtractionRun.ocr_run_id == ocr_run_id)
            .order_by(ExtractionRun.id.desc())
            .first()
        )

        # Page list
        pages = (
            db.query(Page)
            .filter(Page.document_id == ocr_run.document_id)
            .order_by(Page.page_no)
            .all()
        )

        return {
            "ocr_run": {
                "id": ocr_run.id,
                "document_id": ocr_run.document_id,
                "status": ocr_run.status,
                "output_dir_path": ocr_run.output_dir_path,
                "started_at": ocr_run.started_at.isoformat() if ocr_run.started_at else None,
                "finished_at": ocr_run.finished_at.isoformat() if ocr_run.finished_at else None,
            },
            "document": {
                "id": doc.id if doc else None,
                "title": doc.title if doc else "Untitled",
                "page_count": doc.page_count if doc else 0,
            },
            "extraction_run": {
                "id": ext_run.id,
                "status": ext_run.status,
                "model": ext_run.model,
                "total_tokens": ext_run.total_tokens or 0,
                "total_prompt_tokens": ext_run.total_prompt_tokens or 0,
                "total_candidate_tokens": ext_run.total_candidate_tokens or 0,
                "bbox_result_path": ext_run.bbox_result_path,
                "started_at": ext_run.started_at.isoformat() if ext_run.started_at else None,
                "finished_at": ext_run.finished_at.isoformat() if ext_run.finished_at else None,
            } if ext_run else None,
            "pages": [
                {
                    "id": p.id,
                    "page_no": p.page_no,
                }
                for p in pages
            ],
        }
    finally:
        db.close()


@router.delete("/history/{ocr_run_id}")
def delete_ocr_run(ocr_run_id: int):
    """
    刪除指定的 OCR 執行紀錄及所有相關資料
    包含: ExtractionRun (cascade), PageOCRArtifact (cascade),
          Image (cascade), Pages, Document (如果沒有其他 run 參考)
    以及磁碟上的 output 目錄
    """
    from app.db.models import PageOCRArtifact, Image, ExtractionRun, ExtractionLLMCall

    db = SessionLocal()
    try:
        ocr_run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).first()
        if not ocr_run:
            raise HTTPException(status_code=404, detail="OCR run not found")

        document_id = ocr_run.document_id
        output_dir = ocr_run.output_dir_path

        # 1. 刪除 ExtractionLLMCall + ExtractionRun (cascade 應自動處理，但明確刪除更安全)
        ext_runs = db.query(ExtractionRun).filter(ExtractionRun.ocr_run_id == ocr_run_id).all()
        for ext in ext_runs:
            db.query(ExtractionLLMCall).filter(ExtractionLLMCall.extraction_run_id == ext.id).delete()
            # 刪除 extraction 的輸出檔案
            for path_attr in [ext.raw_result_path, ext.structured_result_path, ext.bbox_result_path]:
                if path_attr:
                    p = Path(path_attr)
                    if p.exists():
                        p.unlink(missing_ok=True)
        db.query(ExtractionRun).filter(ExtractionRun.ocr_run_id == ocr_run_id).delete()

        # 2. 刪除 PageOCRArtifact
        db.query(PageOCRArtifact).filter(PageOCRArtifact.ocr_run_id == ocr_run_id).delete()

        # 3. 刪除 Image
        db.query(Image).filter(Image.ocr_run_id == ocr_run_id).delete()

        # 4. 刪除 OCRRun
        db.delete(ocr_run)

        # 5. 檢查是否要刪除 Pages 和 Document（只在沒有其他 OCR run 時刪除）
        other_runs = db.query(OCRRun).filter(
            OCRRun.document_id == document_id,
            OCRRun.id != ocr_run_id,
        ).count()

        deleted_pages = 0
        deleted_document = False
        if other_runs == 0:
            # 沒有其他 OCR run 了，刪除 pages
            deleted_pages = db.query(Page).filter(Page.document_id == document_id).delete()
            # 刪除 document
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                db.delete(doc)
                deleted_document = True

        db.commit()

        # 6. 刪除磁碟上的 output 目錄
        dir_deleted = False
        if output_dir:
            output_path = Path(output_dir)
            if output_path.exists() and output_path.is_dir():
                import shutil
                shutil.rmtree(output_path, ignore_errors=True)
                dir_deleted = True

        return {
            "deleted": True,
            "ocr_run_id": ocr_run_id,
            "document_id": document_id,
            "extraction_runs_deleted": len(ext_runs),
            "pages_deleted": deleted_pages,
            "document_deleted": deleted_document,
            "output_dir_deleted": dir_deleted,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")
    finally:
        db.close()
