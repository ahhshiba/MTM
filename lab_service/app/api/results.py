from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.config import settings
from app.db.models import Image, OCRRun, Page, PageOCRArtifact
from app.db.session import SessionLocal


router = APIRouter(prefix="/results", tags=["results"])
UPLOAD_ROOT = Path(__file__).resolve().parents[1] / "upload_file"


def _is_under(path: Path, root: Path) -> bool:
    try:
        return Path(os.path.commonpath([path.resolve(), root.resolve()])) == root.resolve()
    except ValueError:
        return False


def _ensure_file(path_str: str) -> Path:
    if not path_str:
        raise HTTPException(status_code=404, detail="file path missing")
    path = Path(path_str)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    ocr_root = Path(settings.OCR_DATA_ROOT)
    if not (_is_under(path, ocr_root) or _is_under(path, UPLOAD_ROOT)):
        raise HTTPException(status_code=403, detail="file out of allowed roots")
    return path


def _guess_media_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


@router.get("/ocr/{ocr_run_id}")
def get_ocr_results(ocr_run_id: int) -> Dict[str, object]:
    db = SessionLocal()
    try:
        run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="ocr_run not found")

        pages = (
            db.query(Page)
            .filter(Page.document_id == run.document_id)
            .order_by(Page.page_no)
            .all()
        )
        artifacts = (
            db.query(PageOCRArtifact)
            .filter(PageOCRArtifact.ocr_run_id == ocr_run_id)
            .all()
        )
        images = (
            db.query(Image)
            .filter(Image.ocr_run_id == ocr_run_id)
            .order_by(Image.page_id, Image.sort_order)
            .all()
        )

        artifact_by_page = {row.page_id: row for row in artifacts}
        images_by_page: Dict[int, List[Image]] = {}
        for img in images:
            images_by_page.setdefault(int(img.page_id), []).append(img)

        payload_pages = []
        for page in pages:
            artifact = artifact_by_page.get(page.id)
            artifact_payload = None
            if artifact:
                artifact_payload = {
                    "artifact_id": artifact.id,
                    "result_json_url": f"/results/ocr/artifacts/{artifact.id}/result_json",
                    "result_md_url": f"/results/ocr/artifacts/{artifact.id}/result_md",
                    "vis_image_url": f"/results/ocr/artifacts/{artifact.id}/vis_image",
                }

            page_images = []
            for img in images_by_page.get(int(page.id), []):
                page_images.append(
                    {
                        "image_id": img.id,
                        "image_url": f"/results/ocr/images/{img.id}",
                        "bbox": img.bbox_json,
                        "sort_order": img.sort_order,
                    }
                )

            render_url = None
            if page.render_image_path:
                render_url = f"/results/ocr/pages/{page.id}/render_image"

            payload_pages.append(
                {
                    "page_id": page.id,
                    "page_no": page.page_no,
                    "render_image_url": render_url,
                    "artifact": artifact_payload,
                    "images": page_images,
                }
            )

        return {
            "ocr_run_id": run.id,
            "document_id": run.document_id,
            "document_version_id": run.document_version_id,
            "status": run.status,
            "output_dir": run.output_dir_path,
            "pages": payload_pages,
        }
    finally:
        db.close()


@router.get("/ocr/artifacts/{artifact_id}/result_json")
def get_artifact_json(artifact_id: int):
    db = SessionLocal()
    try:
        artifact = db.query(PageOCRArtifact).filter(PageOCRArtifact.id == artifact_id).one_or_none()
        if artifact is None or not artifact.result_json_path:
            raise HTTPException(status_code=404, detail="artifact json not found")
        path = _ensure_file(artifact.result_json_path)
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    finally:
        db.close()


@router.get("/ocr/artifacts/{artifact_id}/result_md")
def get_artifact_md(artifact_id: int):
    db = SessionLocal()
    try:
        artifact = db.query(PageOCRArtifact).filter(PageOCRArtifact.id == artifact_id).one_or_none()
        if artifact is None or not artifact.result_md_path:
            raise HTTPException(status_code=404, detail="artifact md not found")
        path = _ensure_file(artifact.result_md_path)
        content = path.read_text(encoding="utf-8", errors="ignore")
        return Response(content=content, media_type="text/markdown; charset=utf-8")
    finally:
        db.close()


@router.get("/ocr/artifacts/{artifact_id}/vis_image")
def get_artifact_vis(artifact_id: int):
    db = SessionLocal()
    try:
        artifact = db.query(PageOCRArtifact).filter(PageOCRArtifact.id == artifact_id).one_or_none()
        if artifact is None or not artifact.vis_image_path:
            raise HTTPException(status_code=404, detail="artifact image not found")
        path = _ensure_file(artifact.vis_image_path)
        return FileResponse(path, media_type=_guess_media_type(path))
    finally:
        db.close()


@router.get("/ocr/images/{image_id}")
def get_image(image_id: str):
    db = SessionLocal()
    try:
        image = db.query(Image).filter(Image.id == image_id).one_or_none()
        if image is None:
            # Removed fallback integer query as it causes DB error when column is VARCHAR
            pass
        if image is None or not image.image_path:
            raise HTTPException(status_code=404, detail="image not found")
        path = _ensure_file(image.image_path)
        return FileResponse(path, media_type=_guess_media_type(path))
    finally:
        db.close()


@router.get("/ocr/pages/{page_id}/render_image")
def get_page_render_image(page_id: int):
    db = SessionLocal()
    try:
        page = db.query(Page).filter(Page.id == page_id).one_or_none()
        if page is None:
            raise HTTPException(status_code=404, detail="page not found")
        
        # 優先使用資料庫中的路徑
        if page.render_image_path:
            path = _ensure_file(page.render_image_path)
            return FileResponse(path, media_type=_guess_media_type(path))
        
        # 如果 render_image_path 為空，嘗試使用 PageOCRArtifact 的 vis_image_path
        artifact = db.query(PageOCRArtifact).filter(PageOCRArtifact.page_id == page_id).first()
        if artifact and artifact.vis_image_path:
            path = _ensure_file(artifact.vis_image_path)
            return FileResponse(path, media_type=_guess_media_type(path))
        
        raise HTTPException(status_code=404, detail="render image not found")
    finally:
        db.close()
