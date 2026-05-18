"""
Tech Pack Extraction Configuration Module
支援不同客戶/品牌的 Tech Pack 格式配置

使用方式:
    from extraction_config import get_config, ExtractionConfig
    
    # 使用預設 GAP 配置
    config = get_config("gap")
    
    # 或用自動偵測
    config = get_config("auto")  # 根據文件內容自動選擇
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import re


@dataclass
class ExtractionConfig:
    """提取配置類"""
    
    # 配置名稱/ID
    name: str = "default"
    description: str = "預設配置"
    
    # === 基本欄位映射 ===
    # key: 標準欄位名, value: 可能出現的原始欄位名列表
    field_mapping: Dict[str, List[str]] = field(default_factory=dict)
    
    # === 區塊偵測關鍵字 ===
    # key: 區塊類型, value: regex 模式列表
    section_patterns: Dict[str, List[str]] = field(default_factory=dict)
    
    # === BOM 提取配置 ===
    bom_detection_patterns: List[str] = field(default_factory=list)
    bom_column_mapping: Dict[str, List[str]] = field(default_factory=dict)
    
    # === Measurement 提取配置 ===
    measurement_detection_patterns: List[str] = field(default_factory=list)
    measurement_column_mapping: Dict[str, List[str]] = field(default_factory=dict)
    
    # === 特殊處理 ===
    # 需要特殊處理的欄位類型
    str_fields: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        if not self.str_fields:
            self.str_fields = {"created", "modified", "date", "version"}


# ==============================================================================
# GAP 品牌配置
# ==============================================================================

GAP_CONFIG = ExtractionConfig(
    name="gap",
    description="GAP 品牌 Tech Pack 格式 (Centric PLM)",
    
    field_mapping={
        # Style/Design 相關
        "style_no": ["Design Number", "Style No", "Style Number", "Style", "款號", "款式編號"],
        "style_name": ["Description", "Style Name", "Design Name", "品名", "款式名稱"],
        "bom_number": ["BOM Number", "BOM No", "BOM", "物料編號"],
        
        # Season 相關
        "season": ["Design Season", "Season", "Planning Season", "季節"],
        
        # Brand 相關
        "brand": ["Brand", "Brand/Division", "Division", "品牌"],
        "department": ["Department", "Design Department", "部門"],
        "collection": ["Collection", "Design Collection", "系列"],
        
        # Category 相關
        "category": ["Category", "類別"],
        "sub_category": ["Sub-Category", "SubCategory", "子類別"],
        "design_type": ["Design Type", "Item Type", "Type", "產品類型"],
        
        # Vendor 相關
        "vendor": ["Vendor", "Tech Pack BOM Vendor", "供應商", "廠商"],
        "supplier": ["Supplier", "Supplier [Allocate]", "Allocated Supplier"],
        
        # Status 相關
        "status": ["Status", "BOM Status", "狀態"],
        
        # Date 相關
        "created": ["Created", "Created Date", "建立日期"],
        "modified": ["Modified", "Modified Date", "Revision Modified", "修改日期"],
        
        # Size 相關
        "size_range": ["Size Range", "Selected Sizes", "尺碼範圍"],
        "base_size": ["Base Size", "Sample Size", "基本尺碼", "樣品尺碼"],
    },
    
    section_patterns={
        "BOM": [
            r"BOM\s*Details",
            r"(?:^|\n|>)\s*(?:#+\s*)?(?:BOM|Bill\s+of\s+Materials?|材料清單|物料清單)",
            r"BOM\s*Details",
            r"(?:^|\n|>)\s*(?:#+\s*)?(?:BOM|Bill\s+of\s+Materials?|材料清單|物料清單)",
            r"Product.*Material\s*Name.*Supplier",
            r"Placement.*Description.*Item\s*Type.*Content",  # Gap Fabric table
            r"Fabric.*Details",
            r"(?:^|\n|>)\s*Fabric\s*$",
        ],
        "Measurement": [
            r"Measurement\s*Chart",
            r"POM\s*Name.*Description.*Tol",
            r"(?:^|\n|>)\s*(?:#+\s*)?(?:Measurement|尺寸|Size\s+Spec|規格表)",
        ],
        "Components": [
            r"(?:^|\n|>)\s*(?:#+\s*)?(?:Components?|組件|部件)",
        ],
        "Construction": [
            r"(?:^|\n|>)\s*(?:#+\s*)?(?:Construction|工藝|製程|Sewing|車縫)",
        ],
        "Colorway": [
            r"(?:^|\n|>)\s*(?:#+\s*)?(?:Colorway|配色|Color\s+Combo|顏色)",
        ],
    },
    
    bom_detection_patterns=[
        r"BOM\s*Details",
        r"Product.*Material\s*Name",
        r"Packaging\s+and\s+Labels",
    ],
    
    bom_column_mapping={
        "product_code": ["Product", "Material Code", "Code", "編碼"],
        "material_name": ["Material Name", "Description", "名稱"],
        "supplier": ["Supplier", "Vendor", "供應商"],
        "composition": ["Composition", "Content", "成分"],
        "color": ["Color", "Colorway", "顏色"],
        "usage": ["Usage", "Placement", "用途", "部位"],
    },
    
    measurement_detection_patterns=[
        r"Measurement\s*Chart",
        r"POM\s*Name",
        r"Tol\s*Fraction",
    ],
    
    measurement_column_mapping={
        "pom_code": ["POM", "Code", "編碼"],
        "point_name": ["POM Name", "Description", "測量點"],
        "tolerance": ["Tol", "Tolerance", "公差"],
    },
)


# ==============================================================================
# 通用配置 (適用於大多數格式)
# ==============================================================================

GENERIC_CONFIG = ExtractionConfig(
    name="generic",
    description="通用 Tech Pack 格式",
    
    field_mapping={
        "style_no": [
            "Style No", "Style Number", "Style", "Design Number", "Article No",
            "款號", "款式編號", "貨號"
        ],
        "style_name": [
            "Style Name", "Description", "Product Name", "Item Description",
            "品名", "款式名稱", "產品名稱"
        ],
        "season": [
            "Season", "Delivery Season", "季節"
        ],
        "brand": [
            "Brand", "Customer", "品牌", "客戶"
        ],
        "category": [
            "Category", "Product Type", "類別", "產品類型"
        ],
        "vendor": [
            "Vendor", "Factory", "Manufacturer", "供應商", "工廠", "製造商"
        ],
        "status": [
            "Status", "Stage", "狀態", "階段"
        ],
    },
    
    section_patterns={
        "BOM": [
            r"(?:BOM|Bill\s+of\s+Materials?|材料清單|物料清單)",
            r"(?:Fabric|Material|Trim).*(?:List|Details)",
            r"布料|輔料|材料",
        ],
        "Measurement": [
            r"(?:Measurement|尺寸|Size\s+Spec|規格表)",
            r"(?:Grading|跳檔|尺碼表)",
            r"POM",
        ],
        "Components": [
            r"(?:Components?|Parts?|組件|部件)",
        ],
        "Construction": [
            r"(?:Construction|Sewing|工藝|車縫)",
        ],
    },
    
    bom_detection_patterns=[
        r"Material",
        r"Fabric",
        r"Trim",
        r"Supplier",
    ],
    
    measurement_detection_patterns=[
        r"Measurement",
        r"Size",
        r"POM",
        r"Tolerance",
    ],
)


# ==============================================================================
# H&M 品牌配置 (範例)
# ==============================================================================

HM_CONFIG = ExtractionConfig(
    name="hm",
    description="H&M 品牌 Tech Pack 格式",
    
    field_mapping={
        "style_no": ["Article Number", "Art No", "Article", "貨號"],
        "style_name": ["Article Name", "Description", "品名"],
        "season": ["Season", "Delivery", "季節"],
        "brand": ["Brand", "Concept", "品牌"],
        "category": ["Division", "Product Group", "類別"],
        "vendor": ["Supplier", "Factory", "供應商"],
    },
    
    section_patterns={
        "BOM": [
            r"Material\s+Specification",
            r"Fabric\s+Details",
            r"Trim\s+Details",
        ],
        "Measurement": [
            r"Size\s+Specification",
            r"Measurement\s+Spec",
            r"Grade\s+Rule",
        ],
    },
    
    bom_detection_patterns=[
        r"Material\s+Spec",
        r"Fabric\s+Details",
    ],
    
    measurement_detection_patterns=[
        r"Size\s+Spec",
        r"Grade\s+Rule",
    ],
)


# ==============================================================================
# 配置管理
# ==============================================================================

# 所有已註冊的配置
REGISTERED_CONFIGS: Dict[str, ExtractionConfig] = {
    "gap": GAP_CONFIG,
    "generic": GENERIC_CONFIG,
    "hm": HM_CONFIG,
    "default": GAP_CONFIG,  # 預設使用 GAP 配置
}


def get_config(name: str = "default") -> ExtractionConfig:
    """
    取得指定名稱的配置
    
    Args:
        name: 配置名稱 ("gap", "hm", "generic", "auto", "default")
        
    Returns:
        ExtractionConfig 實例
    """
    if name.lower() == "auto":
        # TODO: 根據文件內容自動偵測
        return REGISTERED_CONFIGS["generic"]
    
    return REGISTERED_CONFIGS.get(name.lower(), REGISTERED_CONFIGS["default"])


def detect_config_from_content(text: str) -> ExtractionConfig:
    """
    根據文件內容自動偵測應使用的配置
    
    Args:
        text: 文件內容
        
    Returns:
        最匹配的 ExtractionConfig
    """
    scores = {}
    
    for config_name, config in REGISTERED_CONFIGS.items():
        if config_name in ("default", "auto"):
            continue
            
        score = 0
        
        # 檢查欄位名稱出現次數
        for field, aliases in config.field_mapping.items():
            for alias in aliases:
                if re.search(alias, text, re.IGNORECASE):
                    score += 1
                    break
        
        # 檢查區塊關鍵字
        for section, patterns in config.section_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    score += 2
                    break
        
        scores[config_name] = score
    
    if not scores:
        return REGISTERED_CONFIGS["generic"]
    
    best_config = max(scores, key=scores.get)
    return REGISTERED_CONFIGS[best_config]


def list_configs() -> List[str]:
    """列出所有可用的配置名稱"""
    return [name for name in REGISTERED_CONFIGS.keys() if name not in ("default",)]


def register_config(config: ExtractionConfig) -> None:
    """
    註冊新的配置
    
    Args:
        config: ExtractionConfig 實例
    """
    REGISTERED_CONFIGS[config.name.lower()] = config


# ==============================================================================
# 配置載入 (從 YAML 或 JSON)
# ==============================================================================

def load_config_from_file(path: str) -> ExtractionConfig:
    """
    從檔案載入配置
    支援 JSON 和 YAML 格式
    
    Args:
        path: 配置檔案路徑
        
    Returns:
        ExtractionConfig 實例
    """
    import json
    from pathlib import Path
    
    file_path = Path(path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        if file_path.suffix in ('.yaml', '.yml'):
            try:
                import yaml
                data = yaml.safe_load(f)
            except ImportError:
                raise ImportError("PyYAML is required to load YAML config files")
        else:
            data = json.load(f)
    
    return ExtractionConfig(
        name=data.get('name', 'custom'),
        description=data.get('description', ''),
        field_mapping=data.get('field_mapping', {}),
        section_patterns=data.get('section_patterns', {}),
        bom_detection_patterns=data.get('bom_detection_patterns', []),
        bom_column_mapping=data.get('bom_column_mapping', {}),
        measurement_detection_patterns=data.get('measurement_detection_patterns', []),
        measurement_column_mapping=data.get('measurement_column_mapping', {}),
        str_fields=set(data.get('str_fields', [])),
    )


# Export
__all__ = [
    'ExtractionConfig',
    'get_config',
    'detect_config_from_content',
    'list_configs',
    'register_config',
    'load_config_from_file',
    'GAP_CONFIG',
    'GENERIC_CONFIG',
    'HM_CONFIG',
]
