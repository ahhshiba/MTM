# app/middleware/license_middleware.py
"""
FastAPI 中間件 — 在每個 request 檢查 license 狀態
"""
from __future__ import annotations

import logging
import time
from typing import Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.services.license import LicenseManager, LicenseStatus

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 白名單路徑設定
# ═══════════════════════════════════════════════════════════════

# 完全不檢查 license 的路徑 (始終放行)
ALWAYS_ALLOWED_PATHS: Set[str] = {
    "/health",
    "/license/fingerprint",
    "/license/status",
    "/license/upload",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# HISTORY_ONLY 模式下允許的路徑前綴 (GET only)
HISTORY_ALLOWED_PREFIXES = (
    "/jobs/history",
    "/extraction/",
    "/results/",
    "/license/",
    "/health",
)

# 快取 license 狀態的秒數，避免每個 request 都做完整檢查
_CACHE_TTL_SECONDS = 60
_cached_status: LicenseStatus | None = None
_cached_at: float = 0


def _get_cached_status(manager: LicenseManager) -> LicenseStatus:
    """取得 license 狀態 (有快取)"""
    global _cached_status, _cached_at

    now = time.time()
    if _cached_status is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return _cached_status

    status = manager.check_status(skip_ntp=True)  # NTP 太慢，只在啟動時檢查
    _cached_status = status
    _cached_at = now
    return status


def _clear_cache():
    """清除快取 (供 license upload 後呼叫)"""
    global _cached_status, _cached_at
    _cached_status = None
    _cached_at = 0


class LicenseMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, license_path: str = "/app/license_dir/license.lic"):
        super().__init__(app)
        self.manager = LicenseManager.get_instance(license_path)
        # 啟動時做一次完整檢查 (含 NTP)
        try:
            startup_status = self.manager.check_status(skip_ntp=False)
            logger.info(f"[License] Startup check: {startup_status.value}")
        except Exception as e:
            logger.error(f"[License] Startup check failed: {e}")

    async def dispatch(self, request: Request, call_next):
        from app.config import settings

        # 0. 開發模式：跳過 license 檢查
        if not settings.LICENSE_CHECK_ENABLED:
            response = await call_next(request)
            response.headers["X-License-Status"] = "active"
            return response

        path = request.url.path
        method = request.method.upper()

        # 1. 白名單路徑 — 始終放行
        if path in ALWAYS_ALLOWED_PATHS:
            response = await call_next(request)
            return response

        # 2. 取得 license 狀態
        status = _get_cached_status(self.manager)

        # 3. 根據狀態決定
        if status == LicenseStatus.ACTIVE:
            # 全功能放行
            response = await call_next(request)
            response.headers["X-License-Status"] = status.value
            return response

        elif status == LicenseStatus.HISTORY_ONLY:
            # 只允許 GET + 白名單路徑
            if method == "GET" and any(path.startswith(p) for p in HISTORY_ALLOWED_PREFIXES):
                response = await call_next(request)
                response.headers["X-License-Status"] = status.value
                return response
            else:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "license_history_only",
                        "status": status.value,
                        "message": "授權已到期，僅可調閱歷史紀錄。請聯繫供應商續約。",
                    },
                    headers={"X-License-Status": status.value},
                )

        elif status in (LicenseStatus.EXPIRED, LicenseStatus.INVALID, LicenseStatus.TAMPERED):
            # 完全鎖定
            msg_map = {
                LicenseStatus.EXPIRED: "授權已完全到期，請聯繫供應商續約。",
                LicenseStatus.INVALID: "授權無效，請確認 license 檔案是否正確。",
                LicenseStatus.TAMPERED: "偵測到系統時間異常，服務已鎖定。請聯繫供應商。",
            }
            return JSONResponse(
                status_code=403,
                content={
                    "error": f"license_{status.value}",
                    "status": status.value,
                    "message": msg_map.get(status, "授權異常"),
                },
                headers={"X-License-Status": status.value},
            )

        # fallback: 放行 (理論上不會到這)
        response = await call_next(request)
        return response
