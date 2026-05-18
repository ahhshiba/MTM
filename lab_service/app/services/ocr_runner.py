# app/services/ocr_runner.py
from __future__ import annotations

import logging
import time
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class OCRSubprocessError(RuntimeError):
    pass


# ==============================================================================
# Singleton: PaddleOCRVL 實例  (初始化一次，所有請求共用)
# ==============================================================================
_ocr_pipeline = None


def _get_pipeline():
    """
    Lazy-init singleton PaddleOCRVL pipeline.
    第一次呼叫時初始化 (包含 import + GPU init)，之後直接複用。
    """
    global _ocr_pipeline
    if _ocr_pipeline is not None:
        return _ocr_pipeline

    logger.info("[OCR] 首次初始化 PaddleOCRVL pipeline (含 import + GPU init)...")
    t0 = time.time()

    from paddleocr import PaddleOCRVL

    _ocr_pipeline = PaddleOCRVL(
        vl_rec_backend="vllm-server",
        vl_rec_server_url=settings.PADDLE_VLLM_URL,
        device="gpu",
    )

    elapsed = time.time() - t0
    logger.info(f"[OCR] PaddleOCRVL pipeline 初始化完成 ({elapsed:.1f}s)")
    return _ocr_pipeline


def run_paddleocr_doc_parser(
    pdf_path: str,
    output_dir: str,
    timeout_seconds: Optional[int] = None,
):
    """
    使用 PaddleOCRVL Python API 直接執行 doc_parser。
    Pipeline 為 singleton，僅首次呼叫時初始化（慢），之後複用（快）。
    """
    try:
        pipeline = _get_pipeline()
    except Exception as e:
        raise OCRSubprocessError(f"OCR pipeline init failed: {e}") from e

    try:
        t0 = time.perf_counter()
        last_page_t0 = t0
        logger.info(f"[OCR] 開始處理: {pdf_path}")

        results = pipeline.predict_iter(pdf_path)
        for i, res in enumerate(results):
            res.save_all(output_dir)
            now = time.perf_counter()
            logger.info(
                "[OCR] Page %s 完成 page_ms=%d total_ms=%d",
                i,
                int((now - last_page_t0) * 1000),
                int((now - t0) * 1000),
            )
            last_page_t0 = now

        logger.info("[OCR] 全部完成 total_ms=%d", int((time.perf_counter() - t0) * 1000))

    except Exception as e:
        raise OCRSubprocessError(f"OCR processing failed: {e}") from e
