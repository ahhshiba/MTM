# backend/app/workers/ocr_worker.py

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.redis_state import set_doc_state, is_canceled, clear_state
from app.services.ocr_service import run_paddleocr_doc_parser

from app.db.models.document import Document
from app.db.models.page import Page
from app.db.models.ocr_run import OCRRun
from app.db.models.ocr_artifact import PageOCRArtifact
from app.db.models.image import Image

from app.utils.ids import new_id


class OCRCancelledError(Exception):
    pass


RES_JSON_RE = re.compile(r"_(\d+)_res\.json$", re.IGNORECASE)


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _page_idx_from_filename(res_json_path: Path) -> Optional[int]:
    m = RES_JSON_RE.search(res_json_path.name)
    if not m:
        return None
    return int(m.group(1))


def _stem_prefix_from_filename(res_json_path: Path) -> str:
    # D42260_0_res.json -> D42260
    parts = res_json_path.name.split("_")
    return parts[0] if parts else "doc"


def _safe_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


def _norm_bbox(bbox: Any) -> Optional[List[int]]:
    """
    你的 res.json 目前是 [x1,y1,x2,y2]（int）
    但也補一點容錯（float / polygon）
    """
    if bbox is None:
        return None

    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
        return [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]

    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in bbox):
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

    return None


def _collect_page_artifact_paths(run_dir: Path, prefix: str, page_idx: int) -> Dict[str, Optional[str]]:
    """
    依你目前輸出檔名：
      D42260_0_res.json
      D42260_0.md
      D42260_0_layout_det_res.png
      D42260_0_layout_order_res.png
    """
    base = f"{prefix}_{page_idx}"

    res_json = run_dir / f"{base}_res.json"
    md = run_dir / f"{base}.md"
    det = run_dir / f"{base}_layout_det_res.png"
    order = run_dir / f"{base}_layout_order_res.png"

    return {
        "result_json_path": str(res_json) if res_json.exists() else None,
        "result_md_path": str(md) if md.exists() else None,
        "vis_image_path": str(det) if det.exists() else None,
        "layout_order_path": str(order) if order.exists() else None,  # DB 不一定存，但先保留你可用
    }


def _resolve_img_by_bbox(imgs_dir: Path, label: str, bbox: List[int]) -> Optional[Path]:
    """
    imgs 檔名沒有 page_no，只能用 bbox 反查
    常見格式（你截圖）：
      img_in_image_box_0_1_1073_804.jpg
      img_in_chart_box_502_56_992_214.jpg

    你的 parsing_res_list block_label 會是：
      image / table / chart / ...
    我們用 label 去猜 prefix：
      image -> img_in_image_box_
      chart -> img_in_chart_box_
      table -> img_in_table_box_ （若有）
    並且再用 bbox 去配對尾巴 _x1_y1_x2_y2
    """
    if not imgs_dir.exists():
        return None

    x1, y1, x2, y2 = bbox
    suffix = f"_{x1}_{y1}_{x2}_{y2}"

    label = (label or "").lower().strip()

    prefix_candidates = []
    if label == "image":
        prefix_candidates = ["img_in_image_box", "img_in_img_box", "img_in_image"]
    elif label == "chart":
        prefix_candidates = ["img_in_chart_box", "img_in_chart"]
    elif label == "table":
        prefix_candidates = ["img_in_table_box", "img_in_table"]
    else:
        prefix_candidates = ["img_in_image_box", "img_in_chart_box", "img_in_table_box", "img_in_image", "img_in_chart", "img_in_table"]

    # 允許 jpg/png/jpeg
    exts = ["*.jpg", "*.jpeg", "*.png", "*.webp"]

    for pre in prefix_candidates:
        for ext in exts:
            # 例：img_in_chart_box_*_502_56_992_214.jpg
            pattern = f"{pre}*{suffix}{ext[1:]}" if ext.startswith("*") else f"{pre}*{suffix}{ext}"
            # pathlib glob 不吃中間的 "*{suffix}{ext}" 這種組合太複雜，改用遍歷過濾更穩
            # 這裡先用 contains 篩一次
            for p in imgs_dir.glob(ext):
                name = p.name
                if name.startswith(pre) and suffix in name:
                    return p

    # 最後兜底：只用 suffix 找（不管 prefix）
    for ext in exts:
        for p in imgs_dir.glob(ext):
            if suffix in p.name:
                return p

    return None


def _upsert_page_artifact(
    db: Session,
    *,
    ocr_run_id: int,
    page_id: int,
    result_json_path: Optional[str],
    result_md_path: Optional[str],
    vis_image_path: Optional[str],
) -> None:
    artifact = (
        db.query(PageOCRArtifact)
        .filter(PageOCRArtifact.ocr_run_id == ocr_run_id, PageOCRArtifact.page_id == page_id)
        .one_or_none()
    )

    if artifact is None:
        artifact = PageOCRArtifact(
            ocr_run_id=ocr_run_id,
            page_id=page_id,
            result_json_path=result_json_path,
            result_md_path=result_md_path,
            vis_image_path=vis_image_path,
        )
        db.add(artifact)
    else:
        if result_json_path:
            artifact.result_json_path = result_json_path
        if result_md_path:
            artifact.result_md_path = result_md_path
        if vis_image_path:
            artifact.vis_image_path = vis_image_path


def _image_exists(db: Session, *, ocr_run_id: int, page_id: int, image_path: str) -> bool:
    row = (
        db.query(Image)
        .filter(Image.ocr_run_id == ocr_run_id, Image.page_id == page_id, Image.image_path == image_path)
        .first()
    )
    return row is not None


def ocr_worker(
    *,
    document_id: str,
    document_version_id: int,
    ocr_run_id: int,
    pdf_path_on_lab: str,
    run_dir_on_lab: str,
) -> None:
    """
    完整 OCR worker：
    1) 呼叫 paddleocr doc_parser（透過 vllm server）
    2) 掃描 run_dir 解析每頁 *_res.json
    3) 寫入 page_ocr_artifacts / images
    4) 更新 DB + Redis
    5) 支援取消

    重要：如果你的本機無法直接讀到 run_dir_on_lab 的檔案，
    你要用 NFS/SMB/sshfs 等方式把實驗室路徑掛載到本機，否則無法解析寫 DB。
    """
    db: Session = SessionLocal()
    started_at = time.time()

    try:
        doc = db.query(Document).filter(Document.id == document_id).one_or_none()
        if doc is None:
            raise RuntimeError(f"Document not found: {document_id}")

        ocr_run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).one_or_none()
        if ocr_run is None:
            raise RuntimeError(f"OCRRun not found: {ocr_run_id}")

        # 標記狀態：running
        doc.status = "ocr_processing"
        ocr_run.status = "running"
        ocr_run.started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        db.commit()

        set_doc_state(document_id, {
            "status": "processing",
            "step": "ocr_processing",
            "progress": 0.0,
            "current_page": 0,
        })

        if is_canceled(document_id):
            raise OCRCancelledError()

        # 1) 執行 PaddleOCR doc_parser（實驗室電腦會產檔）
        run_paddleocr_doc_parser(
            pdf_path=pdf_path_on_lab,
            output_dir=run_dir_on_lab,
        )

        if is_canceled(document_id):
            raise OCRCancelledError()

        # 2) 解析輸出
        run_dir = Path(run_dir_on_lab)
        if not run_dir.exists():
            raise RuntimeError(f"run_dir not accessible: {run_dir_on_lab}")

        imgs_dir = run_dir / "imgs"

        res_json_files = sorted(run_dir.glob("*_res.json"))
        if not res_json_files:
            raise RuntimeError("No *_res.json found in run_dir")

        prefix = _stem_prefix_from_filename(res_json_files[0])

        total = doc.page_count or len(res_json_files)
        processed = 0

        for res_json_path in res_json_files:
            if is_canceled(document_id):
                raise OCRCancelledError()

            res = _load_json(res_json_path)

            # 優先用檔案內容的 page_index（你提供的 json 有）
            page_idx = _safe_int(res.get("page_index"))
            if page_idx is None:
                page_idx = _page_idx_from_filename(res_json_path)

            if page_idx is None:
                # 真的遇到不符合命名規則就跳過
                continue

            page_no = page_idx + 1  # DB 1-based

            page = (
                db.query(Page)
                .filter(Page.document_id == document_id, Page.page_no == page_no)
                .one_or_none()
            )
            if page is None:
                # 容錯：若 pages 未建齊，補建
                page = Page(
                    document_id=document_id,
                    page_no=page_no,
                    render_image_path=None,
                    is_reviewed=False,
                    reviewed_at=None,
                )
                db.add(page)
                db.flush()

            # 寫入 page_ocr_artifacts 路徑
            artifacts = _collect_page_artifact_paths(run_dir, prefix, page_idx)
            _upsert_page_artifact(
                db,
                ocr_run_id=ocr_run_id,
                page_id=page.id,
                result_json_path=artifacts["result_json_path"],
                result_md_path=artifacts["result_md_path"],
                vis_image_path=artifacts["vis_image_path"],
            )

            # 解析 parsing_res_list
            blocks = res.get("parsing_res_list", [])
            if not isinstance(blocks, list):
                blocks = []

            # image 的排序（依 block_order 或出現順序）
            def _block_sort_key(b: Dict[str, Any], fallback: int) -> Tuple[int, int]:
                bo = b.get("block_order")
                bo_i = _safe_int(bo)
                # block_order 有可能是 null
                if bo_i is None:
                    return (10_000_000, fallback)
                return (bo_i, fallback)

            image_like_labels = {"image", "chart", "table"}

            candidates: List[Tuple[int, Dict[str, Any]]] = []
            for i, b in enumerate(blocks):
                if not isinstance(b, dict):
                    continue
                label = (b.get("block_label") or "").lower().strip()
                if label in image_like_labels:
                    candidates.append((i, b))

            candidates.sort(key=lambda x: _block_sort_key(x[1], x[0]))

            sort_order = 0
            for _, b in candidates:
                label = (b.get("block_label") or "").lower().strip()
                bbox = _norm_bbox(b.get("block_bbox"))
                if bbox is None:
                    continue

                img_path = _resolve_img_by_bbox(imgs_dir, label, bbox)
                if img_path is None:
                    # 這代表 Paddle 沒有輸出對應的裁圖；跳過即可
                    continue

                img_path_str = str(img_path)

                if _image_exists(db, ocr_run_id=ocr_run_id, page_id=page.id, image_path=img_path_str):
                    continue

                db.add(Image(
                    id=new_id("img"),
                    ocr_run_id=ocr_run_id,
                    page_id=page.id,
                    bbox_json=bbox,
                    image_path=img_path_str,
                    sort_order=sort_order,
                ))
                sort_order += 1

            db.commit()

            processed += 1
            progress = min(1.0, processed / max(1, total))
            set_doc_state(document_id, {
                "status": "processing",
                "step": "ocr_processing",
                "progress": progress,
                "current_page": page_no,
            })

        # 3) 成功結束
        doc.status = "ocr_done"
        ocr_run.status = "succeeded"
        ocr_run.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        db.commit()

        set_doc_state(document_id, {
            "status": "ocr_done",
            "step": "ocr_done",
            "progress": 1.0,
            "current_page": doc.page_count or processed,
        })

    except OCRCancelledError:
        # canceled：不刪 DB，不刪檔案，僅狀態更新
        try:
            doc = db.query(Document).filter(Document.id == document_id).one_or_none()
            if doc:
                doc.status = "canceled"

            ocr_run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).one_or_none()
            if ocr_run:
                ocr_run.status = "canceled"
                ocr_run.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                ocr_run.error_reason = "Canceled by user"

            db.commit()
        finally:
            clear_state(document_id)

    except Exception as e:
        # failed
        try:
            doc = db.query(Document).filter(Document.id == document_id).one_or_none()
            if doc:
                doc.status = "error"
                doc.error_reason = str(e)[:2000]

            ocr_run = db.query(OCRRun).filter(OCRRun.id == ocr_run_id).one_or_none()
            if ocr_run:
                ocr_run.status = "failed"
                ocr_run.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                ocr_run.error_reason = str(e)[:2000]

            db.commit()
        finally:
            set_doc_state(document_id, {
                "status": "error",
                "step": "ocr_failed",
                "progress": 0.0,
                "error": str(e),
            })
    finally:
        db.close()
