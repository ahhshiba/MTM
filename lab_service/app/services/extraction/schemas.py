"""
Tech Pack Structured Data Schemas
定義所有結構化輸出的 Pydantic Schema

特點:
- 雙語輸出: original_text (原始語言) + value (中文翻譯/標準化)
- 泛化設計: 支援各種衣物類型 (衣服、褲子、配件等)
- 前端友善: 欄位設計考慮前端跳轉和顯示需求
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# 基礎雙語欄位
# ==============================================================================

class BilingualField(BaseModel):
    """雙語欄位: 原始文字 + 中文標準化"""
    original: str = Field(description="原始文字 (英文/日文等)")
    zh: str = Field(description="中文翻譯/標準化")


class BilingualOptional(BaseModel):
    """可選的雙語欄位"""
    original: Optional[str] = Field(default=None, description="原始文字")
    zh: Optional[str] = Field(default=None, description="中文翻譯")


# ==============================================================================
# 基本資訊 (Tech Fields - 可硬比對)
# ==============================================================================

class BasicInfo(BaseModel):
    """基本款式資訊 - 大多可用 regex 或 HTML 表格解析"""
    # 核心欄位
    style_no: Optional[BilingualField] = Field(default=None, description="款式編號")
    style_name: Optional[BilingualField] = Field(default=None, description="款式名稱")
    bom_number: Optional[BilingualField] = Field(default=None, description="BOM 編號")
    season: Optional[BilingualField] = Field(default=None, description="季節 (如 SS24, Summer 2026)")
    
    # 品牌/組織欄位
    brand: Optional[BilingualField] = Field(default=None, description="品牌")
    department: Optional[BilingualField] = Field(default=None, description="部門")
    collection: Optional[BilingualField] = Field(default=None, description="系列")
    
    # 類別欄位
    category: Optional[BilingualField] = Field(default=None, description="類別 (KNITS/WOVENS)")
    sub_category: Optional[BilingualField] = Field(default=None, description="子類別")
    design_type: Optional[BilingualField] = Field(default=None, description="設計類型 (Top/Bottom/Dress)")
    
    # 供應商
    vendor: Optional[BilingualField] = Field(default=None, description="廠商/製造商")
    supplier: Optional[BilingualField] = Field(default=None, description="材料供應商")
    
    # 性別/尺碼
    gender: Optional[BilingualField] = Field(default=None, description="性別 (男/女/中性)")
    size_range: Optional[BilingualField] = Field(default=None, description="尺碼範圍")
    base_size: Optional[BilingualField] = Field(default=None, description="基本/樣品尺碼")
    
    # 狀態/日期
    status: Optional[BilingualField] = Field(default=None, description="狀態 (Concept/In-Work)")
    created: Optional[str] = Field(default=None, description="建立日期")
    modified: Optional[str] = Field(default=None, description="修改日期")
    
    # 訂單資訊
    order_no: Optional[BilingualField] = Field(default=None, description="訂單編號")
    date: Optional[str] = Field(default=None, description="日期")
    version: Optional[str] = Field(default=None, description="版本")
    
    # 額外捕獲的欄位 (動態)
    extra_fields: Optional[Dict[str, BilingualField]] = Field(
        default=None, 
        description="其他硬比對出的欄位"
    )


# ==============================================================================
# BOM 材料清單
# ==============================================================================

class BOMItem(BaseModel):
    """材料清單項目"""
    part: BilingualField = Field(description="部位 (如 Shell Fabric, Lining)")
    usage: Optional[BilingualField] = Field(default=None, description="用途/部位 (原欄位)")
    quantity: Optional[str] = Field(default=None, description="用量/數量")
    common_qty: Optional[str] = Field(default=None, description="Common Qty")
    gauge: Optional[str] = Field(default=None, description="Gauge")
    ends: Optional[str] = Field(default=None, description="Ends")
    stitch_size: Optional[str] = Field(default=None, description="Stitch size")
    allocated_supplier: Optional[BilingualField] = Field(default=None, description="Allocated supplier")
    comments: Optional[BilingualField] = Field(default=None, description="備註/Comments")
    supplier_article_number: Optional[str] = Field(default=None, description="Supplier Article Number")
    product_code: Optional[str] = Field(default=None, description="材料編碼")
    material_name: Optional[BilingualField] = Field(default=None, description="材料名稱")
    composition: Optional[BilingualField] = Field(default=None, description="成分 (如 100% Cotton)")
    color: Optional[BilingualField] = Field(default=None, description="顏色")
    color_code: Optional[str] = Field(default=None, description="色號")
    supplier: Optional[BilingualField] = Field(default=None, description="供應商")
    consumption: Optional[str] = Field(default=None, description="用量 (如 1.5 yd)")
    width: Optional[str] = Field(default=None, description="幅寬 (如 150cm)")
    weight: Optional[str] = Field(default=None, description="克重 (如 200gsm)")
    remarks: Optional[BilingualField] = Field(default=None, description="備註")


class BOMSection(BaseModel):
    """BOM 材料清單區塊"""
    section_type: Literal["BOM"] = "BOM"
    items: List[BOMItem] = Field(default_factory=list)
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    header_info: Optional[str] = Field(default=None, description="頁眉資訊 (Version/Date/Status)")
    raw_text: Optional[str] = Field(default=None, description="原始文字用於前端跳轉")


# ==============================================================================
# 尺寸規格表
# ==============================================================================

class MeasurementPoint(BaseModel):
    """尺寸測量點"""
    pom_code: Optional[str] = Field(default=None, description="POM 編碼 (如 B25.13)")
    point_name: BilingualField = Field(description="測量點名稱")
    variation: Optional[str] = Field(
        default=None,
        description="測量變體 (如 relaxed, flattened)，用於區分相同 POM Code 但不同測量條件"
    )
    unit: str = Field(default="cm", description="單位")
    tolerance: Optional[str] = Field(default=None, description="公差 (如 ±0.5)")
    tolerance_minus: Optional[str] = Field(default=None, description="負公差")
    tolerance_plus: Optional[str] = Field(default=None, description="正公差")
    values: Dict[str, Any] = Field(
        default_factory=dict, 
        description="各尺碼數值 {size: value}，支援分數格式如 '8 1/4'"
    )
    how_to_measure: Optional[BilingualField] = Field(
        default=None, 
        description="測量方式說明"
    )

    @field_validator("point_name", "how_to_measure", mode="before")
    @classmethod
    def _normalize_bilingual_fields(cls, value: Any) -> Optional[BilingualField]:
        if value is None:
            return None
        if isinstance(value, BilingualField):
            return value
        if isinstance(value, dict):
            original = value.get("original") or value.get("value") or value.get("text")
            zh = value.get("zh") or original
            if original is None and zh is None:
                return None
            original = original or zh or ""
            zh = zh or original or ""
            return BilingualField(original=original, zh=zh)
        if isinstance(value, str):
            return BilingualField(original=value, zh=value)
        return value


class MeasurementSection(BaseModel):
    """尺寸規格表區塊"""
    section_type: Literal["Measurement"] = "Measurement"
    chart_type: Optional[Literal["Increment", "Absolute"]] = Field(
        default=None,
        description="圖表類型: Increment(增量/差量) 或 Absolute(實際尺寸)"
    )
    value_format: Optional[str] = Field(
        default=None,
        description="數值格式說明，例如 'base_at_sample_size_increments_elsewhere' 表示 M 欄是實尺寸，其他尺碼是相對於 Base 的增量"
    )
    size_range: Optional[List[str]] = Field(
        default=None, 
        description="尺碼範圍 ['XS', 'S', 'M', 'L', 'XL']"
    )
    sample_size: Optional[str] = Field(default=None, description="樣品尺碼/基準尺碼")
    points: List[MeasurementPoint] = Field(default_factory=list)
    grading_rules: Optional[str] = Field(default=None, description="跳檔規則名稱")
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    header_info: Optional[str] = Field(default=None, description="頁眉資訊 (Version/Date/Status)")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


# ==============================================================================
# 組件/Components
# ==============================================================================

class Component(BaseModel):
    """成衣組件"""
    component_name: BilingualField = Field(description="組件名稱")
    component_type: Optional[BilingualField] = Field(
        default=None, 
        description="組件類型 (主布/配料/輔料)"
    )
    quantity: Optional[str] = Field(default=None, description="數量")
    position: Optional[BilingualField] = Field(default=None, description="位置")
    specifications: Optional[BilingualField] = Field(default=None, description="規格說明")
    remarks: Optional[BilingualField] = Field(default=None, description="備註")


class ComponentsSection(BaseModel):
    """組件區塊"""
    section_type: Literal["Components"] = "Components"
    items: List[Component] = Field(default_factory=list)
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


# ==============================================================================
# Item 品項資訊
# ==============================================================================

class ItemSection(BaseModel):
    """品項基本資訊區塊"""
    section_type: Literal["Item"] = "Item"
    description: Optional[BilingualField] = Field(default=None, description="品項描述")
    garment_type: Optional[BilingualField] = Field(default=None, description="服裝類型")
    fit: Optional[BilingualField] = Field(default=None, description="版型 (修身/寬鬆等)")
    silhouette: Optional[BilingualField] = Field(default=None, description="輪廓")
    construction_details: Optional[List[BilingualField]] = Field(
        default=None, 
        description="製作細節"
    )
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


# ==============================================================================
# Evaluation 評估
# ==============================================================================

class EvaluationItem(BaseModel):
    """評估項目"""
    item_name: BilingualField = Field(description="評估項目名稱")
    standard: Optional[BilingualField] = Field(default=None, description="標準")
    result: Optional[BilingualField] = Field(default=None, description="結果")
    remarks: Optional[BilingualField] = Field(default=None, description="備註")


class EvaluationSection(BaseModel):
    """評估區塊"""
    section_type: Literal["Evaluation"] = "Evaluation"
    items: List[EvaluationItem] = Field(default_factory=list)
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


# ==============================================================================
# 工藝/製程
# ==============================================================================

class ConstructionDetail(BaseModel):
    """工藝細節"""
    area: BilingualField = Field(description="區域 (如 領口/袖口/下擺)")
    process: BilingualField = Field(description="工藝 (如 雙針壓線/包邊)")
    stitch_type: Optional[BilingualField] = Field(default=None, description="車縫類型")
    seam_allowance: Optional[str] = Field(default=None, description="縫份")
    remarks: Optional[BilingualField] = Field(default=None, description="備註")


class ConstructionSection(BaseModel):
    """工藝區塊"""
    section_type: Literal["Construction"] = "Construction"
    details: List[ConstructionDetail] = Field(default_factory=list)
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


# ==============================================================================
# 配色
# ==============================================================================

class ColorwayItem(BaseModel):
    """配色項目"""
    color_name: BilingualField = Field(description="顏色名稱")
    color_code: Optional[str] = Field(default=None, description="色號")
    pantone: Optional[str] = Field(default=None, description="Pantone 色號")
    rgb: Optional[str] = Field(default=None, description="RGB 值")
    part_application: Optional[List[BilingualField]] = Field(
        default=None, 
        description="應用部位"
    )


class ColorwaySection(BaseModel):
    """配色區塊"""
    section_type: Literal["Colorway"] = "Colorway"
    colorways: List[ColorwayItem] = Field(default_factory=list)
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


# ==============================================================================
# 圖片資訊
# ==============================================================================

class ImageInfo(BaseModel):
    """圖片資訊"""
    image_id: Optional[str] = Field(default=None, description="圖片ID")
    image_path: str = Field(description="圖片路徑")
    image_type: Literal[
        "成衣實體圖", 
        "平面線段設計圖", 
        "色塊表", 
        "尺寸圖", 
        "細節圖",
        "Logo/標籤",
        "Email截圖",
        "其他",
        "Unknown"
    ] = Field(description="圖片類型")
    description: BilingualField = Field(description="圖片描述")
    feature_tags: List[str] = Field(default_factory=list, description="特徵標籤")
    related_section: Optional[str] = Field(
        default=None, 
        description="相關區塊 (BOM/Measurement/etc)"
    )
    is_primary: bool = Field(default=False, description="是否為該類別的主要展示圖片")
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    importance_score: Optional[float] = Field(default=None, description="重要性分數")
    image_role: Optional[str] = Field(
        default=None,
        description="圖片用途 (actual_spec/reference/inspiration/unknown)"
    )
    # 新增詳細資訊
    colorway_spec: Optional[str] = Field(
        default=None,
        description="配色方案詳情 (Combo A/B 等)",
    )
    artwork_details: Optional[str] = Field(
        default=None,
        description="圖案細節 (位置/尺寸等)",
    )


# ==============================================================================
# Email 往來記錄
# ==============================================================================

class EmailNote(BaseModel):
    """Email 截圖中的往來記錄"""
    date: Optional[str] = Field(default=None, description="日期")
    sender: Optional[str] = Field(default=None, description="寄件者")
    recipient: Optional[str] = Field(default=None, description="收件者")
    subject: Optional[BilingualField] = Field(default=None, description="主旨")
    content_summary: Optional[BilingualField] = Field(default=None, description="內容摘要")
    action_items: Optional[List[BilingualField]] = Field(
        default=None, 
        description="待辦事項/確認事項"
    )
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    image_path: Optional[str] = Field(default=None, description="對應 Email 截圖路徑")

    @staticmethod
    def _coerce_bilingual(value: Any) -> Optional[BilingualField]:
        if value is None:
            return None
        if isinstance(value, BilingualField):
            return value
        if isinstance(value, dict):
            original = value.get("original") or value.get("value") or value.get("text")
            zh = value.get("zh") or original
            if original is None and zh is None:
                return None
            original = original or zh or ""
            zh = zh or original or ""
            return BilingualField(original=original, zh=zh)
        if isinstance(value, str):
            return BilingualField(original=value, zh=value)
        return value

    @field_validator("subject", "content_summary", mode="before")
    @classmethod
    def _normalize_bilingual_fields(cls, value: Any) -> Optional[BilingualField]:
        return cls._coerce_bilingual(value)

    @field_validator("action_items", mode="before")
    @classmethod
    def _normalize_action_items(cls, value: Any) -> Optional[List[BilingualField]]:
        if value is None:
            return None
        if isinstance(value, list):
            items = [cls._coerce_bilingual(item) for item in value]
            items = [item for item in items if item is not None]
            return items or None
        item = cls._coerce_bilingual(value)
        return [item] if item is not None else None


# ==============================================================================
# Construction options / notes
# ==============================================================================

class ConstructionOptionAttribute(BaseModel):
    """作工選項的屬性"""
    name: BilingualField = Field(description="屬性名稱")
    value: Optional[BilingualField] = Field(default=None, description="屬性值")
    notes: Optional[BilingualField] = Field(default=None, description="補充說明")

    @staticmethod
    def _coerce_bilingual(value: Any) -> Optional[BilingualField]:
        if value is None:
            return None
        if isinstance(value, BilingualField):
            return value
        if isinstance(value, dict):
            original = value.get("original") or value.get("value") or value.get("text")
            zh = value.get("zh") or original
            if original is None and zh is None:
                return None
            original = original or zh or ""
            zh = zh or original or ""
            return BilingualField(original=original, zh=zh)
        if isinstance(value, str):
            return BilingualField(original=value, zh=value)
        return value

    @field_validator("name", "value", "notes", mode="before")
    @classmethod
    def _normalize_bilingual_fields(cls, value: Any) -> Optional[BilingualField]:
        return cls._coerce_bilingual(value)


class ConstructionOption(BaseModel):
    """作工選項 (如 OPT1/OPT2)"""
    option_id: Optional[str] = Field(default=None, description="選項代號")
    title: Optional[BilingualField] = Field(default=None, description="選項名稱")
    summary: Optional[BilingualField] = Field(default=None, description="選項摘要")
    status: Optional[str] = Field(default=None, description="狀態 (active/superseded/revised)")
    decision: Optional[BilingualField] = Field(default=None, description="決策說明")
    latest_update: Optional[str] = Field(default=None, description="最新更新日期 (YYYY-MM-DD)")
    attributes: Optional[List[ConstructionOptionAttribute]] = Field(default=None, description="屬性清單")
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")

    @field_validator("title", "summary", "decision", mode="before")
    @classmethod
    def _normalize_bilingual_fields(cls, value: Any) -> Optional[BilingualField]:
        return ConstructionOptionAttribute._coerce_bilingual(value)

    @field_validator("attributes", mode="before")
    @classmethod
    def _normalize_attributes(cls, value: Any) -> Optional[List[ConstructionOptionAttribute]]:
        if value is None:
            return None
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        return value


class ConstructionNote(BaseModel):
    """作工/TD/會議備註"""
    date: Optional[str] = Field(default=None, description="日期")
    date_original: Optional[str] = Field(default=None, description="原始日期")
    source: Optional[BilingualField] = Field(default=None, description="來源 (TD/RECAP/Meeting)")
    content: Optional[BilingualField] = Field(default=None, description="備註內容")
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")

    @staticmethod
    def _coerce_bilingual(value: Any) -> Optional[BilingualField]:
        if value is None:
            return None
        if isinstance(value, BilingualField):
            return value
        if isinstance(value, dict):
            original = value.get("original") or value.get("value") or value.get("text")
            zh = value.get("zh") or original
            if original is None and zh is None:
                return None
            original = original or zh or ""
            zh = zh or original or ""
            return BilingualField(original=original, zh=zh)
        if isinstance(value, str):
            return BilingualField(original=value, zh=value)
        return value

    @field_validator("source", "content", mode="before")
    @classmethod
    def _normalize_bilingual_fields(cls, value: Any) -> Optional[BilingualField]:
        return cls._coerce_bilingual(value)


class ConstructionExtractionResult(BaseModel):
    """LLM 作工選項/備註抽取結果"""
    options: List[ConstructionOption] = Field(default_factory=list)
    notes: List[ConstructionNote] = Field(default_factory=list)


# ==============================================================================
# Documents / Inspiration sections
# ==============================================================================

class SimpleSectionItem(BaseModel):
    """簡單文字清單項目"""
    text: BilingualField = Field(description="文字內容")
    notes: Optional[BilingualField] = Field(default=None, description="備註")


class DocumentsSection(BaseModel):
    """文件清單區塊"""
    section_type: Literal["Documents"] = "Documents"
    title: Optional[BilingualField] = Field(default=None, description="區塊標題")
    items: List[SimpleSectionItem] = Field(default_factory=list)
    image_paths: Optional[List[str]] = Field(default=None, description="圖片路徑清單")
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


class InspirationSection(BaseModel):
    """靈感/參考區塊"""
    section_type: Literal["Inspiration"] = "Inspiration"
    title: Optional[BilingualField] = Field(default=None, description="區塊標題")
    items: List[SimpleSectionItem] = Field(default_factory=list)
    image_paths: Optional[List[str]] = Field(default=None, description="圖片路徑清單")
    source_page: Optional[int] = Field(default=None, description="來源頁碼")
    raw_text: Optional[str] = Field(default=None, description="原始文字")


# ==============================================================================
# 文件元資料
# ==============================================================================

class DocumentMetadata(BaseModel):
    """文件元資料"""
    document_id: Optional[str] = Field(default=None)
    filename: Optional[str] = Field(default=None)
    total_pages: Optional[int] = Field(default=None)
    ocr_run_id: Optional[str] = Field(default=None)
    processed_at: Optional[str] = Field(default=None)
    extraction_version: str = Field(default="1.0.0")


# ==============================================================================
# 完整結構化輸出
# ==============================================================================

# 所有可能的 Section 類型 Union
SectionType = (
    BOMSection | 
    MeasurementSection | 
    ComponentsSection | 
    ItemSection | 
    EvaluationSection |
    ConstructionSection |
    ColorwaySection |
    DocumentsSection |
    InspirationSection
)


class TechPackStructured(BaseModel):
    """完整的 Tech Pack 結構化輸出"""
    
    # 基本資訊 (硬比對)
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    
    # 各區塊 (LLM 結構化)
    sections: List[SectionType] = Field(default_factory=list)
    
    # 圖片資訊
    images: List[ImageInfo] = Field(default_factory=list)
    
    # Email 記錄
    email_notes: List[EmailNote] = Field(default_factory=list)

    # 作工備註/選項
    construction_notes: List[ConstructionNote] = Field(default_factory=list)
    construction_options: List[ConstructionOption] = Field(default_factory=list)
    
    # 元資料
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    
    # 處理摘要
    extraction_summary: Optional[Dict[str, Any]] = Field(
        default=None,
        description="提取摘要 (區塊數、圖片數、LLM token 使用等)"
    )


# ==============================================================================
# LLM 專用 Schema (用於 structured output)
# ==============================================================================

class LLMSectionExtraction(BaseModel):
    """LLM 區塊提取結果"""
    section_type: str = Field(description="區塊類型")
    confidence: float = Field(description="信心度 0-1")
    extracted_data: Dict[str, Any] = Field(description="提取的資料")
    validation_notes: Optional[str] = Field(
        default=None, 
        description="驗證說明 (如與硬比對結果不符)"
    )


class LLMImageClassification(BaseModel):
    """LLM 圖片分類結果"""
    image_type: Literal[
        "成衣實體圖", 
        "平面線段設計圖", 
        "色塊表", 
        "尺寸圖", 
        "細節圖",
        "Logo/標籤",
        "Email截圖",
        "其他",
        "Unknown"
    ]
    description_original: str = Field(description="原始語言描述")
    description_zh: str = Field(description="中文描述")
    feature_tags: List[str] = Field(description="特徵標籤 (中文)")
    related_section: Optional[str] = Field(
        default=None,
        description="相關區塊類型"
    )
    image_role: Optional[str] = Field(
        default=None,
        description="圖片用途 (actual_spec/reference/inspiration/unknown)"
    )
    # 新增詳細資訊
    colorway_spec: Optional[str] = Field(
        default=None,
        description="配色方案詳情 (Combo A/B 等)",
    )
    artwork_details: Optional[str] = Field(
        default=None,
        description="圖案細節 (位置/尺寸等)",
    )


# Export all schemas
__all__ = [
    "BilingualField",
    "BilingualOptional",
    "BasicInfo",
    "BOMItem",
    "BOMSection",
    "MeasurementPoint",
    "MeasurementSection",
    "Component",
    "ComponentsSection",
    "ItemSection",
    "EvaluationItem",
    "EvaluationSection",
    "ConstructionDetail",
    "ConstructionSection",
    "ColorwayItem",
    "ColorwaySection",
    "ImageInfo",
    "EmailNote",
    "ConstructionOptionAttribute",
    "ConstructionOption",
    "ConstructionNote",
    "ConstructionExtractionResult",
    "SimpleSectionItem",
    "DocumentsSection",
    "InspirationSection",
    "DocumentMetadata",
    "TechPackStructured",
    "LLMSectionExtraction",
    "LLMImageClassification",
]
