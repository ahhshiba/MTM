# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # PaddleOCR vLLM server URL (實驗室機器本機 Docker 對外的 /v1)
    PADDLE_VLLM_URL: str = "http://127.0.0.1:8080/v1"

    # OCR 結果根目錄（實驗室機器本機路徑）
    OCR_DATA_ROOT: str = "/home/lab321/桌面/mtm_api/result"

    # 同時跑幾個 OCR 任務
    WORKER_MAX_CONCURRENCY: int = 1

    # Redis job state TTL（秒）
    JOB_STATE_TTL_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

    # PaddleOCR subprocess timeout（秒），0 表示不設 timeout
    OCR_SUBPROCESS_TIMEOUT_SECONDS: int = 0

    # Gemini VLM
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_BASE: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_TIMEOUT_SECONDS: int = 30
    GEMINI_MAX_CONCURRENCY: int = 4
    GEMINI_MAX_OUTPUT_TOKENS: int = 2048
    GEMINI_MAX_IMAGE_SIDE: int = 1600
    GEMINI_IMAGE_JPEG_QUALITY: int = 85
    GEMINI_THINKING_BUDGET: int = 0
    GEMINI_MAX_HISTORY_MESSAGES: int = 6
    GEMINI_TEMPERATURE: float = 0.2
    EXTRACTION_SECTION_CHUNK_PAGE_COUNT: int = 2
    EXTRACTION_SECTION_CHUNK_MAX_WORKERS: int = 2

    # Vertex AI
    USE_VERTEX_AI: bool = False
    VERTEX_API_KEY: str | None = None
    VERTEX_PROJECT: str | None = None      # GCP Project ID, e.g. mtmtest-483603
    VERTEX_LOCATION: str = "us-central1"

    # License
    LICENSE_FILE_PATH: str = "/app/license_dir/license.lic"
    LICENSE_CHECK_ENABLED: bool = True  # 設為 False 可跳過 license 檢查（開發用）


settings = Settings()
