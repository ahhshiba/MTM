# app/main.py
import logging
import threading

from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.api.results import router as results_router
from app.api.vlm import router as vlm_router
from app.api.extraction import router as extraction_router
from app.api.license_api import router as license_router
from app.middleware.license_middleware import LicenseMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(title="Lab OCR Worker API")

# License 中間件 (第一層防護)
app.add_middleware(LicenseMiddleware)

app.include_router(license_router)
app.include_router(jobs_router)
app.include_router(results_router)
app.include_router(vlm_router)
app.include_router(extraction_router)


def _warmup_ocr_pipeline():
    """在背景 thread 預熱 PaddleOCR pipeline，避免首次請求等待過久。"""
    try:
        from app.services.ocr_runner import _get_pipeline
        logger.info("[Startup] 開始預熱 PaddleOCR pipeline ...")
        _get_pipeline()
        logger.info("[Startup] PaddleOCR pipeline 預熱完成")
    except Exception as e:
        logger.warning(f"[Startup] PaddleOCR 預熱失敗（首次請求時會重試）: {e}")


@app.on_event("startup")
def startup_warmup():
    """服務啟動時在背景 thread 預載 PaddleOCR 模型"""
    thread = threading.Thread(target=_warmup_ocr_pipeline, daemon=True)
    thread.start()


@app.get("/health")
def health():
    return {"ok": True}
