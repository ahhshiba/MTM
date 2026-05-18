# app/db/models.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    Boolean,
    Enum,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=True)
    file_path = Column(String, nullable=False)
    page_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=True)


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no = Column("version_no", Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True)


class OCRRun(Base):
    __tablename__ = "ocr_runs"

    id = Column(Integer, primary_key=True, index=True)

    # === 關聯欄位 ===
    document_id = Column(String, nullable=False, index=True)
    document_version_id = Column(Integer, nullable=False, index=True)

    # === 狀態欄位 ===
    status = Column(String, nullable=False)
    engine = Column(String, nullable=False)
    options_json = Column(JSON, nullable=True)

    # === 輸出 / 錯誤 ===
    job_id = Column(String, nullable=True, index=True)
    output_dir_path = Column(String, nullable=False)
    output_dir_legacy = Column("output_dir", String, nullable=True)

    error_code = Column(String, nullable=True)
    error_message = Column(String, nullable=True)

    # === 時間 ===
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String(64), index=True, nullable=False)

    page_no = Column(Integer, nullable=False)  # DB uses page_no
    render_image_path = Column(Text, nullable=True)
    is_reviewed = Column(Boolean, nullable=False, server_default="false")
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("pages_document_id_page_no_key", "document_id", "page_no", unique=True),
    )


class PageOCRArtifact(Base):
    """
    對應每頁產物路徑（res.json / md / 視覺化 png）
    """
    __tablename__ = "page_ocr_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    ocr_run_id = Column(Integer, ForeignKey("ocr_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(Integer, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)

    result_json_path = Column(Text, nullable=True)
    result_md_path = Column(Text, nullable=True)
    vis_image_path = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("page_ocr_artifacts_ocr_run_id_page_id_key", "ocr_run_id", "page_id", unique=True),
    )


class Image(Base):
    """
    從 image/table/chart block 映射出的裁圖檔
    image_path: 實驗室本機檔案路徑
    """
    __tablename__ = "images"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ocr_run_id = Column(BigInteger, ForeignKey("ocr_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id = Column(BigInteger, ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True)

    image_path = Column(Text, nullable=False)
    bbox_json = Column(JSON, nullable=True)
    sort_order = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class VlmSession(Base):
    __tablename__ = "vlm_sessions"

    id = Column(String, primary_key=True)
    image_id = Column(String, nullable=False, index=True)
    aux_image_path = Column(Text, nullable=True)
    model = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=True)
    finalized = Column(Boolean, nullable=False, server_default="false")
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class VlmMessage(Base):
    __tablename__ = "vlm_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("vlm_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(Enum("user", "assistant", "system", name="chat_role", create_type=False), nullable=False)
    content = Column(Text, nullable=False)
    response_json = Column(JSON, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    candidate_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExtractionRun(Base):
    """結構化萃取執行記錄"""
    __tablename__ = "extraction_runs"

    id = Column(Integer, primary_key=True, index=True)
    ocr_run_id = Column(Integer, ForeignKey("ocr_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String, nullable=False, index=True)

    # 狀態
    status = Column(String, nullable=False, server_default="pending")  # pending, running, completed, failed

    # LLM 配置
    model = Column(String, nullable=True, server_default="gemini-2.5-flash")
    mode = Column(String, nullable=True, server_default="auto")  # auto, developer

    # Token 統計
    total_prompt_tokens = Column(Integer, nullable=True, server_default="0")
    total_candidate_tokens = Column(Integer, nullable=True, server_default="0")
    total_tokens = Column(Integer, nullable=True, server_default="0")

    # 輸出路徑
    raw_result_path = Column(Text, nullable=True)
    structured_result_path = Column(Text, nullable=True)
    bbox_result_path = Column(Text, nullable=True)

    # 錯誤
    error_message = Column(Text, nullable=True)

    # 時間
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ExtractionLLMCall(Base):
    """萃取時的 LLM 對話記錄"""
    __tablename__ = "extraction_llm_calls"

    id = Column(Integer, primary_key=True, index=True)
    extraction_run_id = Column(Integer, ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    # 呼叫類型
    call_type = Column(String, nullable=False)  # block_detection, bom_extraction, etc.

    # 內容
    prompt = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    image_path = Column(Text, nullable=True)

    # Token
    prompt_tokens = Column(Integer, nullable=True)
    candidate_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    # 時間
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

