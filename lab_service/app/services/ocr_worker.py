# app/services/ocr_worker.py
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import OCRRun, Page, PageOCRArtifact, Image
from app.redis.state import set_job_state, is_cancel_requested
from app.services.ocr_runner import run_paddleocr_doc_parser, OCRSubprocessError
from app.services.ocr_parser import (
    iter_res_json_files,
    load_res_json,
    extract_page_meta,
    extract_blocks,
    norm_bbox,
    pick_page_prefix,
    page_artifact_paths,
    OCRParseError,
)
from app.services.image_mapper import match_image_by_bbox


logger = logging.getLogger(__name__)


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class JobError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# =====================
# DB helpers
# =====================

def _upsert_page(db: Session, document_id: str, page_no: int) -> Page:
    page = (
        db.query(Page)
        .filter(Page.document_id == document_id, Page.page_no == page_no)
        .one_or_none()
    )
    if page is None:
        page = Page(
            document_id=document_id,
            page_no=page_no,
        )
        db.add(page)
        db.flush()
    return page


def _upsert_artifact(db: Session, ocr_run_id: int, page_id: int, paths: dict) -> None:
    row = (
        db.query(PageOCRArtifact)
        .filter(
            PageOCRArtifact.ocr_run_id == ocr_run_id,
            PageOCRArtifact.page_id == page_id,
        )
        .one_or_none()
    )
    if row is None:
        row = PageOCRArtifact(
            ocr_run_id=ocr_run_id,
            page_id=page_id,
            result_json_path=paths.get("result_json_path"),
            result_md_path=paths.get("result_md_path"),
            vis_image_path=paths.get("vis_image_path"),
        )
        db.add(row)
    else:
        for k in ("result_json_path", "result_md_path", "vis_image_path"):
            v = paths.get(k)
            if v:
                setattr(row, k, v)


def _upsert_ocr_run_running(db: Session, ocr_run_id: int, job_id: str, output_dir: str) -> OCRRun:
    run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).one_or_none()
    if run is None:
        raise JobError("DB_FAILED", f"OCRRun not found: {ocr_run_id}")

    run.status = "running"
    run.job_id = job_id
    run.output_dir_path = output_dir
    run.started_at = run.started_at or datetime.utcnow()
    run.updated_at = datetime.utcnow()
    run.error_code = None
    run.error_message = None
    return run


def _finish_ocr_run(db: Session, ocr_run_id: int, status: str, error_code: str | None, error_message: str | None) -> None:
    run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).one_or_none()
    if run is None:
        return
    run.status = status
    run.finished_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    run.error_code = error_code
    run.error_message = error_message


# =====================
# Worker entry
# =====================

def submit_ocr_job(
    *,
    job_id: str,
    document_id: str,
    document_version_id: int,
    pdf_path: str,
    ocr_run_id: int,
    output_dir: str,
) -> None:
    """
    背景任務：
    OCR → parse → image mapping → DB
    """
    total_t0 = time.perf_counter()
    ocr_elapsed_ms = 0
    parse_elapsed_ms = 0
    db: Session = SessionLocal()
    out_dir = Path(output_dir)

    try:
        logger.info(
            "[OCR][%s] worker start document_id=%s version_id=%s ocr_run_id=%s",
            job_id[:8],
            document_id,
            document_version_id,
            ocr_run_id,
        )
        # ---------- 1️ DB: running ----------
        _upsert_ocr_run_running(db, ocr_run_id, job_id, str(out_dir))
        db.commit()

        set_job_state(job_id, {
            "status": "running",
            "step": "ocr",
            "document_id": document_id,
            "document_version_id": document_version_id,
            "ocr_run_id": ocr_run_id,
            "output_dir": str(out_dir),
            "progress": 0.01,
            "timing": {
                "backend_worker_start_ms": _duration_ms(total_t0),
            },
        })

        if is_cancel_requested(job_id):
            raise JobError("CANCELED", "Canceled before OCR")

        # ---------- 2️ Run PaddleOCR ----------
        try:
            ocr_t0 = time.perf_counter()
            run_paddleocr_doc_parser(
                pdf_path=pdf_path,
                output_dir=str(out_dir),
            )
            ocr_elapsed_ms = _duration_ms(ocr_t0)
            logger.info(
                "[OCR][%s] pure OCR complete ocr_run_id=%s elapsed_ms=%d",
                job_id[:8],
                ocr_run_id,
                ocr_elapsed_ms,
            )
        except OCRSubprocessError as e:
            raise JobError("OCR_FAILED", str(e)) from e

        if is_cancel_requested(job_id):
            raise JobError("CANCELED", "Canceled after OCR")

        set_job_state(job_id, {
            "status": "running",
            "step": "parse_and_mapping",
            "document_id": document_id,
            "document_version_id": document_version_id,
            "ocr_run_id": ocr_run_id,
            "output_dir": str(out_dir),
            "progress": 0.20,
            "timing": {
                "ocr_ms": ocr_elapsed_ms,
                "total_ms": _duration_ms(total_t0),
            },
        })

        # ---------- 3️ Parse ----------
        parse_t0 = time.perf_counter()
        res_files = iter_res_json_files(out_dir)
        if not res_files:
            raise JobError("PARSE_FAILED", "No *_res.json found after OCR")

        prefix = pick_page_prefix(res_files[0].name)
        imgs_dir = out_dir / "imgs"

        total = len(res_files)
        done = 0

        for res_json_path in res_files:
            if is_cancel_requested(job_id):
                raise JobError("CANCELED", "Canceled during parsing")

            res = load_res_json(res_json_path)
            meta = extract_page_meta(res)

            page_no = meta.get("page_index")
            if page_no is None:
                raise JobError("PARSE_FAILED", f"page_index missing in {res_json_path.name}")

            page = _upsert_page(
                db,
                document_id=document_id,
                page_no=int(page_no),
            )

            paths = page_artifact_paths(out_dir, prefix, int(page_no))
            _upsert_artifact(db, ocr_run_id, page.id, paths)

            blocks = extract_blocks(res)

            db.query(Image).filter(
                Image.ocr_run_id == ocr_run_id,
                Image.page_id == page.id,
            ).delete()

            images_to_insert = []

            for i, b in enumerate(blocks):
                block_type = (b.get("block_label") or "").strip()
                bbox = norm_bbox(b.get("block_bbox"))

                if block_type in {"image", "table", "chart"} and bbox:
                    img_path = match_image_by_bbox(imgs_dir, bbox)
                    if img_path:
                        images_to_insert.append((img_path, bbox))

            for idx, (img_path, bbox) in enumerate(images_to_insert):
                db.add(Image(
                    ocr_run_id=ocr_run_id,
                    page_id=page.id,
                    image_path=str(img_path),
                    bbox_json=bbox,
                    sort_order=idx,
                ))

            db.commit()

            done += 1
            set_job_state(job_id, {
                "status": "running",
                "step": "parse_and_mapping",
                "progress": round(0.20 + (done / total) * 0.75, 4),
                "current_page": int(page_no),
                "total_pages": total,
                "timing": {
                    "ocr_ms": ocr_elapsed_ms,
                    "parse_mapping_ms": _duration_ms(parse_t0),
                    "total_ms": _duration_ms(total_t0),
                },
            })

        # ---------- 4️ Finish ----------
        parse_elapsed_ms = _duration_ms(parse_t0)
        total_elapsed_ms = _duration_ms(total_t0)
        logger.info(
            "[OCR][%s] parse/mapping complete pages=%d elapsed_ms=%d",
            job_id[:8],
            total,
            parse_elapsed_ms,
        )
        _finish_ocr_run(db, ocr_run_id, "succeeded", None, None)
        db.commit()

        set_job_state(job_id, {
            "status": "done",
            "step": "finished",
            "progress": 1.0,
            "timing": {
                "ocr_ms": ocr_elapsed_ms,
                "parse_mapping_ms": parse_elapsed_ms,
                "total_ms": total_elapsed_ms,
            },
        })
        logger.info(
            "[OCR][%s] worker complete ocr_run_id=%s total_ms=%d ocr_ms=%d parse_mapping_ms=%d",
            job_id[:8],
            ocr_run_id,
            total_elapsed_ms,
            ocr_elapsed_ms,
            parse_elapsed_ms,
        )

    except JobError as e:
        _finish_ocr_run(
            db,
            ocr_run_id,
            "canceled" if e.code == "CANCELED" else "failed",
            e.code,
            e.message,
        )
        db.commit()

        set_job_state(job_id, {
            "status": "canceled" if e.code == "CANCELED" else "failed",
            "step": "error",
            "error_code": e.code,
            "error_message": e.message,
            "progress": 0.0,
            "timing": {
                "ocr_ms": ocr_elapsed_ms,
                "parse_mapping_ms": parse_elapsed_ms,
                "total_ms": _duration_ms(total_t0),
            },
        })
        logger.warning(
            "[OCR][%s] worker stopped status=%s code=%s total_ms=%d",
            job_id[:8],
            "canceled" if e.code == "CANCELED" else "failed",
            e.code,
            _duration_ms(total_t0),
        )

    except Exception as e:
        db.rollback()
        _finish_ocr_run(db, ocr_run_id, "failed", "UNKNOWN_ERROR", str(e))
        db.commit()

        set_job_state(job_id, {
            "status": "failed",
            "step": "error",
            "error_code": "UNKNOWN_ERROR",
            "error_message": str(e),
            "progress": 0.0,
            "timing": {
                "ocr_ms": ocr_elapsed_ms,
                "parse_mapping_ms": parse_elapsed_ms,
                "total_ms": _duration_ms(total_t0),
            },
        })
        logger.exception("[OCR][%s] worker failed total_ms=%d", job_id[:8], _duration_ms(total_t0))

    finally:
        db.close()
