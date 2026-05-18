# app/api/license_api.py
"""License API — 硬體指紋收集 + 狀態查詢 + License 上傳"""
from __future__ import annotations

from fastapi import APIRouter, UploadFile, File, HTTPException
from app.config import settings
from app.services.license import HardwareFingerprint, LicenseManager, LicenseStatus

router = APIRouter(prefix="/license", tags=["license"])


@router.get("/fingerprint")
def get_hardware_fingerprint():
    """
    收集並回傳此機器的硬體指紋
    此 endpoint 在白名單中，不需要 license 即可訪問
    客戶把回傳的 JSON 傳給開發端用於簽發 license
    """
    info = HardwareFingerprint.collect()
    return info


@router.get("/status")
def get_license_status():
    """
    取得當前 license 授權狀態
    此 endpoint 在白名單中
    """
    # 開發模式：直接回傳 active
    if not settings.LICENSE_CHECK_ENABLED:
        return {
            "status": "active",
            "is_active": True,
            "is_history_only": False,
            "is_expired": False,
            "license_info": {"note": "LICENSE_CHECK_ENABLED=false, dev mode"},
        }

    manager = LicenseManager.get_instance()
    status = manager.check_status(skip_ntp=True)
    info = manager.get_license_info()

    return {
        "status": status.value,
        "is_active": status == LicenseStatus.ACTIVE,
        "is_history_only": status == LicenseStatus.HISTORY_ONLY,
        "is_expired": status in (LicenseStatus.EXPIRED, LicenseStatus.INVALID, LicenseStatus.TAMPERED),
        "license_info": info,
    }


@router.post("/upload")
async def upload_license(file: UploadFile = File(...)):
    """
    接收客戶上傳的 license.lic 並寫入磁碟
    此 endpoint 在白名單中，不需要 license 即可訪問
    """
    if not file.filename.endswith(".lic"):
        raise HTTPException(status_code=400, detail="請上傳 .lic 檔案")

    content = await file.read()
    if len(content) > 10240:  # 10KB 上限
        raise HTTPException(status_code=400, detail="檔案過大")

    # 寫入磁碟
    license_path = settings.LICENSE_FILE_PATH
    try:
        with open(license_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"寫入失敗: {e}")

    # 清除快取，強制重新載入
    LicenseManager._instance = None
    from app.middleware.license_middleware import _clear_cache
    _clear_cache()

    # 回傳新狀態
    manager = LicenseManager.get_instance()
    status = manager.check_status(skip_ntp=True)
    info = manager.get_license_info()

    return {
        "ok": True,
        "message": "License 已上傳",
        "status": status.value,
        "is_active": status == LicenseStatus.ACTIVE,
        "license_info": info,
    }
