import os
from pathlib import Path
from pydantic import BaseModel


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

class Settings(BaseModel):
    # DB / Redis
    database_url: str = _env_str("DATABASE_URL", "postgresql://user:password@localhost:5432/yourdb")
    redis_url: str = _env_str("REDIS_URL", "redis://localhost:6379/0")
    local_redis_url: str = _env_str("LOCAL_REDIS_URL", _env_str("REDIS_URL", "redis://localhost:6379/0"))
    local_job_ttl_seconds: int = _env_int("LOCAL_JOB_TTL_SECONDS", 60 * 60 * 24)
    local_upload_root: str = _env_str("LOCAL_UPLOAD_ROOT", "./uploads")

    # OCR server (實驗室電腦)
    paddle_ocr_vllm_url: str = _env_str("PADDLE_OCR_VLLM_URL", "http://localhost:8000/v1")
    lab_api_base_url: str = _env_str("LAB_API_BASE_URL", "http://localhost:9000")
    lab_http_timeout_seconds: int = _env_int("LAB_HTTP_TIMEOUT_SECONDS", 30)
    lab_vlm_batch_timeout_seconds: int = _env_int("LAB_VLM_BATCH_TIMEOUT_SECONDS", lab_http_timeout_seconds * 2)

    # 本機看到的「實驗室檔案系統掛載路徑（邏輯）」 
    lab_data_root: str = _env_str("LAB_DATA_ROOT", "/lab_data/documents")

settings = Settings()
