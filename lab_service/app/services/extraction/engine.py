# app/services/extraction/engine.py
"""
Extraction Engine
核心萃取邏輯 — asyncio 全並行版
"""
import asyncio
import json
import re
import time
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pydantic import BaseModel

# Local Imports
from .schemas import (
    TechPackStructured, BasicInfo, BilingualField, BOMSection, BOMItem,
    MeasurementSection, MeasurementPoint, ComponentsSection, Component,
    ItemSection, EvaluationSection, EvaluationItem, ColorwaySection, ColorwayItem,
    ConstructionSection, ConstructionDetail, ImageInfo, EmailNote, DocumentMetadata,
    LLMImageClassification, ConstructionOptionAttribute, ConstructionOption,
    ConstructionNote, ConstructionExtractionResult, DocumentsSection, InspirationSection,
    SimpleSectionItem
)
from .config import ExtractionConfig
from .llm import GeminiClient, AsyncGeminiClient, load_image_data
from .patterns import HARD_MATCH_PATTERNS, SECTION_PATTERNS
from .prompts import (
    SECTION_EXTRACTION_PROMPTS, IMAGE_CLASSIFICATION_PROMPT, 
    EMAIL_EXTRACTION_PROMPT, CONSTRUCTION_EXTRACTION_PROMPT,
    FINAL_REVIEW_PROMPT, BASIC_INFO_TRANSLATION_PROMPT
)
from app.config import settings

# ==============================================================================
# 輔助函數
# ==============================================================================
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _contains_cjk(text: Optional[str]) -> bool:
    return bool(text and _CJK_RE.search(str(text)))


def _contains_latin(text: Optional[str]) -> bool:
    return bool(text and _LATIN_RE.search(str(text)))


def _translation_key(text: str) -> str:
    text = re.sub(r"[_/]+", " ", text.strip().lower())
    text = re.sub(r"\s*-\s*", " - ", text)
    return re.sub(r"\s+", " ", text).strip()


EXACT_ZH_TRANSLATIONS = {
    "waistband height": "腰頭高度",
    "contour waist at top edge - tape flat": "腰頭上緣圍 - 平量",
    "contour waist at bottom of band - tape flat": "腰頭下緣圍 - 平量",
    "minimum waist stretched": "最小腰圍拉伸",
    "front rise": "前襠",
    "back rise": "後襠",
    "hip position - 3 point": "臀位 - 三點",
    "low hip 3 point measurement": "低臀圍三點量測",
    "low hip 3-point measurement": "低臀圍三點量測",
    "gusset length": "襠片長",
    "gusset width": "襠片寬",
    "thigh": "大腿圍",
    "neck width": "領寬",
    "front neck drop": "前領深",
    "back neck drop": "後領深",
    "chest": "胸圍",
    "bust": "胸圍",
    "waist": "腰圍",
    "hip": "臀圍",
    "seat": "臀圍",
    "sleeve length": "袖長",
    "across shoulder": "肩寬",
    "shoulder width": "肩寬",
    "body length": "衣長",
    "bottom opening": "下擺寬",
    "cuff opening": "袖口寬",
    "trim height": "邊飾高度",
    "armhole": "袖攏",
    "inseam": "褲內長",
    "outseam": "褲長",
    "leg opening": "褲口寬",
    "sweep": "下擺寬",
    "hem": "下擺",
    "main body - cross grain": "大身 - 橫紋",
    "gusset": "襠片",
    "1 ply mesh in wb": "腰頭內單層網布",
    "contrast inner waistband": "撞色內腰頭",
    "dtm stitching": "同色車線",
    "contrast stitching": "撞色車線",
    "logo - see sketch": "Logo - 見設計圖",
    "customer review": "客戶審閱",
    "td notes": "TD 備註",
    "recap": "回顧摘要",
}


PHRASE_ZH_TRANSLATIONS = [
    ("no seam at the sideseam", "側縫無縫"),
    ("straight waist seam", "直腰縫"),
    ("block reference", "版型參考"),
    ("actual waistband", "實際腰頭"),
    ("double layer", "雙層"),
    ("self fabric", "本布"),
    ("folded along top edge", "沿上緣折疊"),
    ("extra high rise", "超高腰"),
    ("contour waist at bottom of band", "腰頭下緣圍"),
    ("contour waist at top edge", "腰頭上緣圍"),
    ("minimum waist stretched", "最小腰圍拉伸"),
    ("low hip 3-point measurement", "低臀圍三點量測"),
    ("low hip 3 point measurement", "低臀圍三點量測"),
    ("hip position - 3 point", "臀位 - 三點"),
    ("waistband height", "腰頭高度"),
    ("gusset length", "襠片長"),
    ("gusset width", "襠片寬"),
    ("front rise", "前襠"),
    ("back rise", "後襠"),
    ("tape flat", "平量"),
    ("side seam", "側縫"),
    ("main body", "大身"),
    ("cross grain", "橫紋"),
    ("inner waistband", "內腰頭"),
    ("waistband", "腰頭"),
    ("contrast stitching", "撞色車線"),
    ("dtm stitching", "同色車線"),
    ("see sketch", "見設計圖"),
    ("cotton jersey", "棉質平紋針織"),
    ("spun polyester", "紡績聚酯"),
    ("polyester", "聚酯"),
    ("heat transfer", "熱轉印"),
    ("exterior label", "外標"),
    ("design to specify", "由設計指定"),
    ("rpet interlock", "RPET 雙面針織"),
    ("interlock", "雙面針織"),
    ("piece dye", "匹染"),
    ("breathable", "透氣"),
    ("quick dry", "快乾"),
    ("go dry", "速乾"),
    ("weft knit", "緯編"),
    ("solid", "素色"),
    ("mesh", "網布"),
    ("lining", "裡布"),
    ("shell", "表布"),
    ("body", "大身"),
    ("neck", "領口"),
    ("sleeve", "袖子"),
    ("hem", "下擺"),
    ("cuff", "袖口"),
    ("label", "標籤"),
    ("packaging", "包裝"),
    ("color", "顏色"),
    ("comments", "備註"),
]


def _translate_text_fallback(text: Optional[str]) -> str:
    """本地術語補強：LLM 未翻譯時，盡量補可辨識的服裝中文。"""
    if not text:
        return ""

    original = str(text).strip()
    if not original or not _contains_latin(original) or _contains_cjk(original):
        return original

    exact = EXACT_ZH_TRANSLATIONS.get(_translation_key(original))
    if exact:
        return exact

    translated = original
    for phrase, zh in sorted(PHRASE_ZH_TRANSLATIONS, key=lambda item: len(item[0]), reverse=True):
        translated = re.sub(re.escape(phrase), zh, translated, flags=re.IGNORECASE)

    translated = re.sub(r"\s+", " ", translated).strip()
    translated = re.sub(r"\s+([,.;:)])", r"\1", translated)
    translated = re.sub(r"([(])\s+", r"\1", translated)
    return translated if translated != original and _contains_cjk(translated) else original


def _should_replace_zh(original: str, current_zh: Optional[str], fallback_zh: str) -> bool:
    if not fallback_zh or fallback_zh == original:
        return False
    if not current_zh or current_zh == original or current_zh == "-":
        return True
    if not _contains_cjk(current_zh):
        return True

    exact = EXACT_ZH_TRANSLATIONS.get(_translation_key(original))
    generic_terms = {"腰圍", "臀圍", "下擺", "袖口", "領口"}
    return bool(exact and current_zh.strip() in generic_terms and exact != current_zh.strip())


def _ensure_bilingual_translations(value: Any) -> None:
    """遞迴補齊非中文 original 的 zh，避免預覽只剩原文。"""
    if isinstance(value, BilingualField):
        original = (value.original or "").strip()
        fallback_zh = _translate_text_fallback(original)
        if _should_replace_zh(original, value.zh, fallback_zh):
            value.zh = fallback_zh
        return

    if isinstance(value, BaseModel):
        if hasattr(value, "original") and hasattr(value, "zh"):
            original = str(getattr(value, "original") or "").strip()
            current_zh = getattr(value, "zh", None)
            fallback_zh = _translate_text_fallback(original)
            if _should_replace_zh(original, current_zh, fallback_zh):
                setattr(value, "zh", fallback_zh)
        for field_name in value.__class__.model_fields:
            _ensure_bilingual_translations(getattr(value, field_name, None))
        return

    if isinstance(value, dict):
        for child in value.values():
            _ensure_bilingual_translations(child)
        return

    if isinstance(value, (list, tuple, set)):
        for child in value:
            _ensure_bilingual_translations(child)


def load_markdown_file(path: str) -> str:
    """載入 Markdown 檔案"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[Warning] Failed to load {path}: {e}")
        return ""


def load_json_file(path: str) -> Dict[str, Any]:
    """載入 JSON 檔案"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Warning] Failed to load {path}: {e}")
        return {}


def extract_tables_from_json(json_files: List[Path]) -> Dict[str, List[str]]:
    """
    從 JSON 檔案的 parsing_res_list 提取表格內容
    作為 markdown 解析失敗時的 fallback
    
    Returns:
        Dict with keys: 'tables', 'headers', 'all_blocks'
    """
    result = {
        "tables": [],  # HTML table content
        "headers": [],  # Header text
        "all_blocks": []  # All text blocks for context
    }
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            page_idx = data.get('page_index', 0)
            
            for block in data.get('parsing_res_list', []):
                label = block.get('block_label', '')
                content = block.get('block_content', '')
                
                if not content:
                    continue
                
                if label == 'table':
                    result['tables'].append({
                        'page': page_idx,
                        'content': content
                    })
                elif label == 'header':
                    result['headers'].append({
                        'page': page_idx,
                        'content': content
                    })
                
                result['all_blocks'].append({
                    'page': page_idx,
                    'label': label,
                    'content': str(content)[:500]  # Truncate for memory
                })
                    
        except Exception as e:
            print(f"[Warning] Failed to parse {json_file.name}: {e}")
    
    return result


# ==============================================================================
# 硬比對提取
# ==============================================================================

def extract_basic_info_regex(text: str) -> BasicInfo:
    """使用 regex 硬比對提取基本資訊 (含字典翻譯)"""
    basic_info = BasicInfo()
    
    # 簡易中英對照字典
    TERM_MAPPING = {
        "in-work": "製作中", "in work": "製作中",
        "adopted": "已採用", "dropped": "已取消", "cancelled": "已取消",
        "alpha": "字母尺碼", "numeric": "數字尺碼",
        "women": "女裝", "men": "男裝", "girls": "女童", "boys": "男童",
        "toddler": "幼童", "infant": "嬰兒", "baby": "嬰兒",
        "spring": "春季", "summer": "夏季", "fall": "秋季", "winter": "冬季",
        "holiday": "假日", "resort": "渡假", "pre-fall": "早秋"
    }

    # 這些欄位是 str 型別，不是 BilingualField
    str_fields = {"date", "version"}
    
    for field_name, patterns in HARD_MATCH_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                
                if hasattr(basic_info, field_name):
                    if field_name in str_fields:
                        setattr(basic_info, field_name, value)
                    else:
                        # 嘗試翻譯
                        val_lower = value.lower()
                        zh_value = value
                        
                        # 1. 直接對應
                        if val_lower in TERM_MAPPING:
                            zh_value = TERM_MAPPING[val_lower]
                        # 2. 季節模糊比對 (例如 "Summer 2026" -> "2026 夏季")
                        elif field_name == "season":
                            for en_term in ["spring", "summer", "fall", "winter", "holiday", "resort"]:
                                if en_term in val_lower:
                                    zh_term = TERM_MAPPING.get(en_term, en_term)
                                    # 簡單替換英文單字
                                    zh_value = val_lower.replace(en_term, zh_term).replace("  ", " ").strip().title()
                                    # 如果包含數字，調整順序? 暫時不處理太複雜的 regex
                                    break
                                    
                        bilingual = BilingualField(original=value, zh=zh_value)
                        setattr(basic_info, field_name, bilingual)
                break
    
    return basic_info


def detect_sections(text: str, config: Optional[Any] = None) -> Dict[str, List[Tuple[int, int]]]:
    """偵測文字中的各區塊位置"""
    sections_found: Dict[str, List[Tuple[int, int]]] = {}
    
    # 使用配置或預設 patterns
    patterns_to_use = config.section_patterns if config and config.section_patterns else SECTION_PATTERNS
    
    for section_type, patterns in patterns_to_use.items():
        for pattern in patterns:
            try:
                for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                    if section_type not in sections_found:
                        sections_found[section_type] = []
                    sections_found[section_type].append((match.start(), match.end()))
            except re.error as e:
                print(f"[Warning] Invalid regex pattern '{pattern}': {e}")
    
    return sections_found


def extract_section_text(
    full_text: str, 
    section_start: int, 
    next_section_start: Optional[int] = None,
    max_length: int = 5000
) -> str:
    """提取區塊文字"""
    if next_section_start:
        end = min(next_section_start, section_start + max_length)
    else:
        end = min(len(full_text), section_start + max_length)
    
    return full_text[section_start:end]


# ==============================================================================
# JSON 解析輔助函數
# ==============================================================================

def parse_llm_json_response(response: str) -> Optional[Dict[str, Any]]:
    """
    健壯地解析 LLM 的 JSON 回應
    處理 markdown code blocks、前後文字等問題
    """
    if not response or not response.strip():
        return None
    
    text = response.strip()
    
    # 1. 移除 markdown code blocks
    if "```" in text:
        # 找出 ```json 或 ``` 包裹的內容
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    
    # 2. 找出 JSON 開始位置 { 或 [
    json_start = -1
    for i, char in enumerate(text):
        if char in '{[':
            json_start = i
            break
    
    if json_start == -1:
        return None
    
    # 3. 找出對應的結束位置
    text = text[json_start:]
    
    # 4. 嘗試解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # 5. 嘗試修復常見問題並重試
    # 移除尾部多餘內容 (找到最後一個 } 或 ])
    for i in range(len(text) - 1, -1, -1):
        if text[i] in '}]':
            try:
                return json.loads(text[:i+1])
            except json.JSONDecodeError:
                continue
    
    return None


# ==============================================================================
# 表格解析 (支援 HTML 表格)
# ==============================================================================

def parse_html_tables(text: str) -> List[List[List[str]]]:
    """
    解析 HTML 表格，返回 [table1, table2, ...]
    每個 table 是 [[row1_cells], [row2_cells], ...]
    """
    import re
    tables = []
    
    # 找出所有 <table>...</table>
    table_pattern = r'<table[^>]*>(.*?)</table>'
    table_matches = re.findall(table_pattern, text, re.DOTALL | re.IGNORECASE)
    
    for table_content in table_matches:
        rows = []
        # 找出所有 <tr>...</tr>
        row_pattern = r'<tr[^>]*>(.*?)</tr>'
        row_matches = re.findall(row_pattern, table_content, re.DOTALL | re.IGNORECASE)
        
        for row_content in row_matches:
            cells = []
            # 找出所有 <td>...</td> 或 <th>...</th>
            cell_pattern = r'<t[dh][^>]*>(.*?)</t[dh]>'
            cell_matches = re.findall(cell_pattern, row_content, re.DOTALL | re.IGNORECASE)
            
            for cell in cell_matches:
                # 清理 HTML 標籤和實體
                clean_cell = re.sub(r'<[^>]+>', '', cell)
                clean_cell = clean_cell.replace('&amp;', '&')
                clean_cell = clean_cell.replace('&lt;', '<')
                clean_cell = clean_cell.replace('&gt;', '>')
                clean_cell = clean_cell.replace('&quot;', '"')
                clean_cell = clean_cell.strip()
                cells.append(clean_cell)
            
            if cells:
                rows.append(cells)
        
        if rows:
            tables.append(rows)
    
    return tables


def extract_key_value_pairs_from_tables(tables: List[List[List[str]]]) -> Dict[str, str]:
    """
    從兩欄表格中提取 key-value 對
    適用於表頭資訊區塊
    """
    kv_pairs = {}
    
    for table in tables:
        for row in table:
            if len(row) == 2:
                key = row[0].strip()
                value = row[1].strip()
                if key and value:
                    kv_pairs[key] = value
    
    return kv_pairs


def parse_markdown_table(text: str) -> List[Dict[str, str]]:
    """解析 Markdown 表格 (保留向後相容)"""
    lines = text.strip().split("\n")
    tables = []
    current_table = []
    
    for line in lines:
        if "|" in line:
            cells = [cell.strip() for cell in line.split("|")]
            cells = [c for c in cells if c]
            if cells and not all(c.replace("-", "").replace(":", "") == "" for c in cells):
                current_table.append(cells)
        else:
            if current_table and len(current_table) > 1:
                tables.append(current_table)
            current_table = []
    
    if current_table and len(current_table) > 1:
        tables.append(current_table)
    
    results = []
    for table in tables:
        headers = table[0]
        for row in table[1:]:
            if len(row) >= len(headers):
                row_dict = {headers[i]: row[i] for i in range(len(headers))}
                results.append(row_dict)
            elif row:
                row_dict = {f"col_{i}": val for i, val in enumerate(row)}
                results.append(row_dict)
    
    return results


def extract_basic_info_from_html(text: str, config: Optional[Any] = None) -> Dict[str, str]:
    """
    從 HTML 表格中提取基本資訊
    通用化設計，適用於各種 Tech Pack 格式
    """
    tables = parse_html_tables(text)
    kv_pairs = extract_key_value_pairs_from_tables(tables)
    
    # 使用配置或預設 mapping
    if config and config.field_mapping:
        field_mapping = config.field_mapping
    else:
        # 標準化欄位名稱映射 (通用)
        field_mapping = {
            # Style/Design 相關
            "style_no": ["Design Number", "Style No", "Style Number", "Style", "款號", "款式編號"],
            "style_name": ["Description", "Style Name", "Design Name", "品名", "款式名稱"],
            "bom_number": ["BOM Number", "BOM No", "BOM", "物料編號"],
            
            # Season 相關
            "season": ["Season", "Design Season", "Planning Season", "季節"],
            
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
        }
    
    result = {}
    for field, possible_keys in field_mapping.items():
        for key in possible_keys:
            if key in kv_pairs:
                result[field] = kv_pairs[key]
                break
    
    return result

EMAIL_KEYWORDS = [
    "From:", "Sent:", "To:", "Subject:",
    "Original Message", "Replies", "Outlook", "Gmail",
    "Hi All", "Dear", "Best Regards",
    "收件者", "寄件者", "主旨", "日期", "發件人", "收件人",
]

EMAIL_HEADER_PATTERNS = {
    "sender": [
        r"^(?:from|寄件者|發件人|寄件人)[:：]?\s*(.+)$",
    ],
    "recipient": [
        r"^(?:to|收件者|收件人)[:：]?\s*(.+)$",
    ],
    "subject": [
        r"^(?:subject|主旨|標題|标题)[:：]?\s*(.+)$",
    ],
    "date": [
        r"^(?:sent|date|日期|發送時間|发送时间)[:：]?\s*(.+)$",
    ],
}

EMAIL_ADDRESS_RE = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+", re.IGNORECASE)
DOCUMENT_FILENAME_RE = re.compile(
    r"\b[\w\-. ]+\.(?:pdf|docx?|xlsx?|pptx?|csv|txt|zip|rar|7z|jpg|jpeg|png|tif|tiff|psd)\b",
    re.IGNORECASE,
)

COMPOSITION_KEYWORD_RE = re.compile(r"(composition|content|fiber\s*content|成分|成份)", re.IGNORECASE)

CONSTRUCTION_KEYWORDS = [
    "construction", "sewing", "stitch", "seam", "workmanship", "spec",
    "option", "opt", "note", "recap", "meeting", "td",
    "作工", "做工", "車縫", "縫", "壓", "針", "規格", "備註", "會前會", "會議", "說明",
]

OPTION_MARKER_RE = re.compile(r"\b(?:OPT\s*\d+|Option\s*[A-Z0-9]+)\b", re.IGNORECASE)
BOM_MAIN_TEXT_LIMIT = 15000
BOM_CONTEXT_LIMIT = 8000
MEASUREMENT_MAIN_TEXT_LIMIT = 20000
MEASUREMENT_CONTEXT_LIMIT = 12000
BOM_CONTEXT_KEYWORDS = [
    "bom", "bill of materials", "fabric", "body", "shell", "trim", "label",
    "packaging", "wash", "graphic", "material", "composition", "supplier",
    "article", "color", "colour", "usage", "qty", "quantity", "gauge",
    "stitch", "comments", "remarks", "主布", "布料", "輔料", "標籤", "包裝",
    "成分", "供應商", "顏色", "用量", "備註",
]
MEASUREMENT_CONTEXT_KEYWORDS = [
    "measurement", "measure", "spec", "size", "pom", "tolerance", "tol",
    "grade", "grading", "increment", "absolute", "base size", "xs", "xxs",
    "xl", "xxl", "chest", "shoulder", "sleeve", "neck",
    "bottom", "cuff", "bicep", "sweep", "waist", "hip", "inseam",
    "尺寸", "量測", "公差", "尺碼", "胸", "肩", "袖", "領", "腰", "臀",
]
SECTION_CHUNK_PAGE_COUNT = max(1, int(settings.EXTRACTION_SECTION_CHUNK_PAGE_COUNT))
SECTION_CHUNK_MAX_WORKERS = max(1, int(settings.EXTRACTION_SECTION_CHUNK_MAX_WORKERS))

# ==============================================================================
# 主要提取器
# ==============================================================================

@dataclass
class ExtractionContext:
    """提取上下文 — 支援同步與非同步 client"""
    run_dir: Path
    api_key: Optional[str]
    gemini_client: Optional[GeminiClient] = None
    async_gemini_client: Optional[AsyncGeminiClient] = None
    use_llm: bool = False
    config: Optional[Any] = None  # ExtractionConfig
    token_tracker: Optional["TokenTracker"] = None
    log_writer: Optional["LogWriter"] = None
    progress_callback: Optional[Any] = None  # Callable[[float, str], None]


class TokenTracker:
    """Thread-safe AND async-safe token tracker"""
    def __init__(self) -> None:
        import threading
        self._thread_lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None
        self._totals: Dict[str, Dict[str, int]] = {}

    def _ensure_async_lock(self):
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return self._async_lock

    def add(self, step: str, usage: Dict[str, int]) -> None:
        """同步版 add"""
        if not usage:
            return
        with self._thread_lock:
            self._add_internal(step, usage)

    async def async_add(self, step: str, usage: Dict[str, int]) -> None:
        """非同步版 add"""
        if not usage:
            return
        async with self._ensure_async_lock():
            self._add_internal(step, usage)

    def _add_internal(self, step: str, usage: Dict[str, int]) -> None:
        totals = self._totals.setdefault(step, {
            "prompt_tokens": 0,
            "candidate_tokens": 0,
            "cached_tokens": 0,
            "total_tokens": 0,
        })
        totals["prompt_tokens"] += usage.get("prompt_tokens", 0)
        totals["candidate_tokens"] += usage.get("candidate_tokens", 0)
        totals["cached_tokens"] += usage.get("cached_tokens", 0)
        totals["total_tokens"] += usage.get("total_tokens", 0)

    def summary(self) -> Dict[str, Dict[str, int]]:
        return {k: dict(v) for k, v in self._totals.items()}


class LogWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = path.open("a", encoding="utf-8")

    def log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self._fh.write(f"[{timestamp}] {message}\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None


def _log(ctx: ExtractionContext, message: str) -> None:
    if ctx.log_writer:
        ctx.log_writer.log(message)


def _track_tokens(ctx: ExtractionContext, step: str, usage: Dict[str, int]) -> None:
    if ctx.token_tracker:
        ctx.token_tracker.add(step, usage)


async def _async_track_tokens(ctx: ExtractionContext, step: str, usage: Dict[str, int]) -> None:
    if ctx.token_tracker:
        await ctx.token_tracker.async_add(step, usage)


def _clip_middle(text: str, limit: int, marker: str) -> str:
    if len(text) <= limit:
        return text
    if limit <= len(marker) + 200:
        return text[:limit]
    head_len = (limit - len(marker)) // 2
    tail_len = limit - len(marker) - head_len
    return text[:head_len] + marker + text[-tail_len:]


def _keyword_context(text: str, keywords: List[str]) -> str:
    if not keywords:
        return ""
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    lines = text.splitlines()
    keep: set[int] = set()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("---") or pattern.search(line):
            for nearby in range(max(0, idx - 1), min(len(lines), idx + 2)):
                keep.add(nearby)
    return "\n".join(lines[idx] for idx in sorted(keep))


def _limit_prompt_text(
    text: str,
    limit: int,
    label: str,
    ctx: Optional[ExtractionContext] = None,
    keywords: Optional[List[str]] = None,
) -> str:
    if len(text) <= limit:
        return text

    marker = f"\n\n[... {label} compacted; middle non-key content omitted ...]\n\n"
    head_tail_budget = max(1000, int(limit * 0.45))
    keyword_budget = max(0, limit - head_tail_budget)
    compacted = _clip_middle(text, head_tail_budget, marker)

    keyword_text = _keyword_context(text, keywords or [])
    if keyword_text:
        keyword_marker = f"\n\n[... {label} keyword-context ...]\n\n"
        compacted += keyword_marker + _clip_middle(keyword_text, keyword_budget, marker)
        compacted = _clip_middle(compacted, limit, marker)

    message = f"{label} compacted chars={len(text)}->{len(compacted)} limit={limit}"
    print(f"  [PromptLimit] {message}")
    if ctx:
        _log(ctx, message)
    return compacted


def _source_page_from_name(source_name: Optional[str]) -> Optional[int]:
    if not source_name:
        return None
    matches = re.findall(r"\d+", source_name)
    if not matches:
        return None
    try:
        return int(matches[0])
    except ValueError:
        return None


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, BilingualField):
        return value.original or value.zh or ""
    if isinstance(value, dict):
        return str(value.get("original") or value.get("zh") or value.get("value") or "")
    return str(value)


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, BilingualField):
        return not (value.original or value.zh)
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _merge_pydantic_non_empty(base: BaseModel, incoming: BaseModel) -> None:
    for field_name in base.__class__.model_fields:
        if field_name == "section_type":
            continue
        base_value = getattr(base, field_name, None)
        incoming_value = getattr(incoming, field_name, None)
        if _is_empty_value(base_value) and not _is_empty_value(incoming_value):
            setattr(base, field_name, incoming_value)


def _bom_item_key(item: BOMItem, fallback_index: int) -> str:
    parts = [
        item.product_code,
        _text_value(item.material_name),
        _text_value(item.usage) or _text_value(item.part),
        _text_value(item.color),
        item.color_code,
        item.supplier_article_number,
    ]
    key = "|".join(re.sub(r"\s+", " ", p.strip().lower()) for p in parts if p and p.strip())
    return key or f"unknown:{fallback_index}"


def _measurement_point_key(section: MeasurementSection, point: MeasurementPoint, fallback_index: int) -> str:
    parts = [
        section.chart_type or "",
        point.pom_code or "",
        _text_value(point.point_name),
        point.variation or "",
    ]
    key = "|".join(re.sub(r"\s+", " ", p.strip().lower()) for p in parts if p and p.strip())
    return key or f"unknown:{fallback_index}"


def _merge_bom_sections(sections: List[BOMSection]) -> List[BOMSection]:
    merged_items: Dict[str, BOMItem] = {}
    headers: List[str] = []
    raw_parts: List[str] = []
    source_pages: List[int] = []

    for section in sections:
        if section.header_info and section.header_info not in headers:
            headers.append(section.header_info)
        if section.raw_text:
            raw_parts.append(section.raw_text)
        if section.source_page is not None:
            source_pages.append(section.source_page)
        for item in section.items or []:
            key = _bom_item_key(item, len(merged_items))
            existing = merged_items.get(key)
            if existing is None:
                merged_items[key] = item
            else:
                _merge_pydantic_non_empty(existing, item)

    if not merged_items:
        return []
    return [
        BOMSection(
            items=list(merged_items.values()),
            source_page=min(source_pages) if source_pages else None,
            header_info=" | ".join(headers[:5]) if headers else None,
            raw_text="\n\n".join(raw_parts)[:4000] if raw_parts else None,
        )
    ]


def _merge_measurement_sections(sections: List[MeasurementSection]) -> List[MeasurementSection]:
    section_map: Dict[str, MeasurementSection] = {}
    point_maps: Dict[str, Dict[str, MeasurementPoint]] = {}

    for section in sections:
        group_key = "|".join([
            section.chart_type or "Unknown",
            section.header_info or "",
            section.sample_size or "",
            section.grading_rules or "",
        ])
        if group_key not in section_map:
            section_map[group_key] = MeasurementSection(
                chart_type=section.chart_type,
                value_format=section.value_format,
                size_range=section.size_range,
                sample_size=section.sample_size,
                grading_rules=section.grading_rules,
                source_page=section.source_page,
                header_info=section.header_info,
                raw_text=section.raw_text,
                points=[],
            )
            point_maps[group_key] = {}
        else:
            _merge_pydantic_non_empty(section_map[group_key], section)

        for point in section.points or []:
            point_key = _measurement_point_key(section, point, len(point_maps[group_key]))
            existing = point_maps[group_key].get(point_key)
            if existing is None:
                point_maps[group_key][point_key] = point
            else:
                _merge_pydantic_non_empty(existing, point)
                existing.values.update({k: v for k, v in (point.values or {}).items() if k not in existing.values or not existing.values.get(k)})

    merged_sections: List[MeasurementSection] = []
    for group_key, section in section_map.items():
        section.points = list(point_maps[group_key].values())
        if section.points:
            merged_sections.append(section)
    return merged_sections


def _bom_section_from_llm_data(bom_data: Optional[Dict[str, Any]], source_name: str, raw_text: str) -> Optional[BOMSection]:
    if not bom_data or not bom_data.get("items"):
        return None

    bom_items: List[BOMItem] = []
    for item in bom_data.get("items", []):
        if not isinstance(item, dict):
            continue
        usage_value = item.get("usage") or item.get("usage_qty") or item.get("part")
        part_value = usage_value or item.get("part") or item.get("category") or ""
        composition_value = item.get("composition")
        if not composition_value:
            for candidate in (
                item.get("comments"),
                item.get("remarks"),
                item.get("material_name"),
                item.get("material_name_zh"),
                item.get("specifications"),
            ):
                composition_value = _extract_composition_from_text(candidate)
                if composition_value:
                    break
        if not any([
            item.get("product_code"),
            item.get("material_name"),
            usage_value,
            item.get("supplier_article_number"),
            item.get("supplier_article"),
            composition_value,
        ]):
            continue

        bom_items.append(BOMItem(
            part=BilingualField(original=part_value, zh=part_value),
            usage=BilingualField(original=usage_value, zh=usage_value) if usage_value else None,
            quantity=item.get("quantity") or item.get("qty"),
            common_qty=item.get("common_qty"),
            gauge=item.get("gauge"),
            ends=item.get("ends"),
            stitch_size=item.get("stitch_size"),
            allocated_supplier=BilingualField(
                original=item.get("allocated_supplier", ""),
                zh=item.get("allocated_supplier", ""),
            ) if item.get("allocated_supplier") else None,
            comments=BilingualField(
                original=item.get("comments", ""),
                zh=item.get("comments", ""),
            ) if item.get("comments") else None,
            supplier_article_number=item.get("supplier_article_number") or item.get("supplier_article"),
            product_code=item.get("product_code"),
            material_name=BilingualField(
                original=item.get("material_name", ""),
                zh=item.get("material_name_zh", item.get("material_name", "")),
            ) if item.get("material_name") else None,
            composition=BilingualField(original=composition_value, zh=composition_value) if composition_value else None,
            color=BilingualField(
                original=item.get("color_info", ""),
                zh=item.get("color_info", ""),
            ) if item.get("color_info") else None,
            color_code=item.get("color_code"),
            supplier=BilingualField(
                original=item.get("supplier", ""),
                zh=item.get("supplier", ""),
            ) if item.get("supplier") else None,
            consumption=item.get("consumption"),
            width=item.get("width"),
            weight=item.get("weight"),
            remarks=BilingualField(
                original=item.get("remarks", ""),
                zh=item.get("remarks", ""),
            ) if item.get("remarks") else None,
        ))

    if not bom_items:
        return None
    header_info = bom_data.get("header_info")
    if isinstance(header_info, (dict, list)):
        header_info = json.dumps(header_info, ensure_ascii=False)
    return BOMSection(
        items=bom_items,
        source_page=_source_page_from_name(source_name),
        header_info=header_info,
        raw_text=raw_text[:2000],
    )


def _measurement_sections_from_llm_data(
    measurement_data: Optional[Dict[str, Any]],
    source_name: str,
    raw_text: str,
) -> List[MeasurementSection]:
    if not measurement_data:
        return []
    charts = measurement_data.get("charts", [])
    if not charts and "points" in measurement_data:
        charts = [measurement_data]

    local_sections: List[MeasurementSection] = []
    for chart in charts:
        if not isinstance(chart, dict):
            continue
        chart_type = chart.get("chart_type")
        points_data = chart.get("points", [])
        if not points_data:
            continue

        measurement_points: List[MeasurementPoint] = []
        for pt in points_data:
            if not isinstance(pt, dict):
                continue
            variation = pt.get("variation")
            if variation:
                variation = variation.replace("(inferred)", "").strip()
                if not variation or variation == "null":
                    variation = None

            description = pt.get("description")
            point_name = pt.get("point_name") or ""
            if description:
                description = description.replace("(inferred)", "").strip()
                if description.lower().replace(" ", "") == point_name.lower().replace(" ", ""):
                    description = None
            if not point_name and not pt.get("pom_code") and not pt.get("values"):
                continue

            measurement_points.append(MeasurementPoint(
                pom_code=pt.get("pom_code"),
                point_name=BilingualField(original=point_name, zh=pt.get("point_name_zh") or point_name),
                variation=variation,
                unit=chart.get("unit", "inches"),
                tolerance=f"-{pt.get('tolerance_minus', '')} / +{pt.get('tolerance_plus', '')}" if pt.get("tolerance_minus") else None,
                tolerance_minus=pt.get("tolerance_minus"),
                tolerance_plus=pt.get("tolerance_plus"),
                values=pt.get("values") or {},
                how_to_measure=BilingualField(original=description, zh=description) if description else None,
            ))

        if not measurement_points:
            continue

        header_info = chart.get("header_info")
        if isinstance(header_info, (dict, list)):
            header_info = json.dumps(header_info, ensure_ascii=False)

        value_format = None
        base_size = chart.get("base_size")
        if chart_type == "Increment" and base_size:
            is_mixed = False
            for pt in measurement_points:
                base_val = str(pt.values.get(base_size, "")).strip()
                if base_val and re.match(r"^\d", base_val) and base_val != "0" and "+" not in base_val and "-" not in base_val:
                    for k, v in pt.values.items():
                        if k != base_size and ("+" in str(v) or "-" in str(v)):
                            is_mixed = True
                            break
                if is_mixed:
                    break
            value_format = f"base_at_{base_size}_increments_elsewhere" if is_mixed else "pure_increments"

        local_sections.append(MeasurementSection(
            chart_type=chart_type if chart_type in ("Increment", "Absolute") else None,
            value_format=value_format,
            size_range=chart.get("size_range"),
            sample_size=chart.get("base_size"),
            grading_rules=chart.get("grading_rule_name") or chart.get("grading_rule"),
            source_page=_source_page_from_name(source_name),
            header_info=header_info,
            raw_text=raw_text[:2000],
            points=measurement_points,
        ))
    return local_sections


def collect_ocr_files(run_dir: Path) -> Dict[str, Any]:
    """收集 OCR 輸出檔案"""
    files = {
        "json_files": sorted(run_dir.glob("*_res.json")),
        "md_files": sorted(run_dir.glob("*.md")),
        "imgs_dir": run_dir / "imgs",
    }
    
    print(f"找到 {len(files['json_files'])} 個 JSON 檔案")
    print(f"找到 {len(files['md_files'])} 個 Markdown 檔案")
    
    if files["imgs_dir"].exists():
        img_count = len(list(files["imgs_dir"].glob("*")))
        print(f"找到 {img_count} 張圖片")
    
    return files


def merge_all_markdown(md_files: List[Path]) -> str:
    """合併所有 Markdown 內容"""
    all_text = []
    for md_file in md_files:
        content = load_markdown_file(str(md_file))
        all_text.append(f"--- Page {md_file.stem} ---\n{content}")
    return "\n\n".join(all_text)


def extract_with_hard_matching(full_text: str, config: Optional[Any] = None) -> BasicInfo:
    """
    使用硬比對提取基本資訊
    結合 regex 和 HTML 表格解析
    """
    print("\n[1/5] 硬比對提取基本資訊...")
    
    # 1. 先用 regex 硬比對
    # TODO: 也將 regex 模式配置化
    basic_info = extract_basic_info_regex(full_text)
    
    # 2. 再用 HTML 表格解析補充
    html_info = extract_basic_info_from_html(full_text, config)
    
    # 3. 合併結果 (HTML 表格解析通常更準確，優先使用)
    # 這些欄位是 str 型別，不是 BilingualField
    str_fields = config.str_fields if config else {"created", "modified", "date", "version"}
    
    for field, value in html_info.items():
        if value and value.strip():
            if hasattr(basic_info, field):
                if field in str_fields:
                    # 直接設為字串
                    setattr(basic_info, field, value)
                else:
                    # 設為 BilingualField
                    bilingual = BilingualField(original=value, zh=value)
                    setattr(basic_info, field, bilingual)
    
    # 4. 打印找到的欄位
    found_count = 0
    # 優先顯示的欄位列表（包含 HTML 解析能抓到的欄位）
    priority_fields = [
        "style_no", "style_name", "bom_number", "season", "brand", 
        "department", "collection", "category", "design_type",
        "vendor", "supplier", "status", "size_range", "base_size",
        "created", "modified"
    ]
    for field_name in priority_fields:
        value = getattr(basic_info, field_name, None)
        if value:
            if hasattr(value, 'original') and value.original:
                print(f"  {field_name}: {value.original}")
                found_count += 1
            elif isinstance(value, str) and value.strip():
                print(f"  {field_name}: {value}")
                found_count += 1
    
    print(f"  總計找到 {found_count} 個欄位")
    
    return basic_info


def extract_sections_with_llm(
    full_text: str, 
    ctx: ExtractionContext,
    md_files: List[Path],
    json_files: Optional[List[Path]] = None
) -> List[Any]:
    """
    使用 LLM 提取各區塊
    策略: 
    1. 優先從 markdown 文件解析
    2. fallback 到 JSON 的 parsing_res_list
    """
    print("\n[2/5] 偵測並提取區塊...")
    
    extracted_sections = []
    sections_found = detect_sections(full_text, ctx.config)
    
    # 統計偵測到的區塊
    for section_type, positions in sections_found.items():
        if positions:
            print(f"  發現 {section_type} 區塊: {len(positions)} 處")
    
    # 如果沒有 LLM，只做基本解析
    if not ctx.use_llm or not ctx.gemini_client:
        print("  (無 LLM，跳過詳細提取)")
        return extracted_sections
    
    # 收集需要提取的頁面內容 (BOM 和 Measurement 是關鍵)
    bom_pages = []
    measurement_pages = []
    
    # 準備偵測模式
    bom_patterns = [r'BOM\s*Details', r'Product.*Material\s*Name', r'Packaging\s+and\s+Labels']
    measurement_patterns = [r'Measurement\s*Chart', r'POM\s*Name', r'Tol\s*Fraction']
    
    if ctx.config:
        if ctx.config.bom_detection_patterns:
            bom_patterns = ctx.config.bom_detection_patterns
        if ctx.config.measurement_detection_patterns:
            measurement_patterns = ctx.config.measurement_detection_patterns
    
    bom_regex = "|".join(bom_patterns)
    measurement_regex = "|".join(measurement_patterns)

    md_page_entries = []
    for md_file in md_files:
        with open(md_file, 'r', encoding='utf-8') as f:
            page_content = f.read()
        
        page_name = md_file.stem
        md_page_entries.append((page_name, page_content))
        
        # 檢查這頁是否包含 BOM 相關內容
        if re.search(bom_regex, page_content, re.IGNORECASE):
            bom_pages.append((page_name, page_content))
        
        # 檢查這頁是否包含 Measurement 相關內容
        if re.search(measurement_regex, page_content, re.IGNORECASE):
            measurement_pages.append((page_name, page_content))
    
    # === JSON Fallback ===
    # 如果 markdown 沒找到，嘗試從 JSON 表格中提取
    if (not bom_pages or not measurement_pages) and json_files:
        print("  (嘗試 JSON fallback...)")
        json_data = extract_tables_from_json(json_files)
        
        for table in json_data.get('tables', []):
            table_content = table.get('content', '')
            page_idx = table.get('page', 0)
            
            # 檢查表格內容是否包含 BOM 相關
            if not bom_pages and re.search(bom_regex, table_content, re.IGNORECASE):
                bom_pages.append((f"page_{page_idx}_json", table_content))
            
            # 檢查表格內容是否包含 Measurement 相關
            if not measurement_pages and re.search(measurement_regex, table_content, re.IGNORECASE):
                measurement_pages.append((f"page_{page_idx}_json", table_content))

    def _keyword_regex(keywords: List[str]) -> str:
        return "|".join(re.escape(k) for k in keywords if k)

    if not bom_pages and md_page_entries:
        bom_keyword_regex = _keyword_regex(BOM_CONTEXT_KEYWORDS)
        broad_bom_pages = [
            (name, content)
            for name, content in md_page_entries
            if re.search(bom_keyword_regex, content, re.IGNORECASE)
        ]
        if broad_bom_pages:
            print(f"  BOM regex 未命中，改用 keyword 候選頁: {len(broad_bom_pages)} 頁")
            bom_pages = broad_bom_pages[:8]
        else:
            print("  BOM regex/keyword 皆未命中，fallback 前 5 頁交給 LLM 判斷")
            bom_pages = md_page_entries[:5]

    if not measurement_pages and md_page_entries:
        measurement_keyword_regex = _keyword_regex(MEASUREMENT_CONTEXT_KEYWORDS)
        broad_measurement_pages = [
            (name, content)
            for name, content in md_page_entries
            if re.search(measurement_keyword_regex, content, re.IGNORECASE)
        ]
        if broad_measurement_pages:
            print(f"  Measurement regex 未命中，改用 keyword 候選頁: {len(broad_measurement_pages)} 頁")
            measurement_pages = broad_measurement_pages[:10]
        else:
            table_pages = [
                (name, content)
                for name, content in md_page_entries
                if "|" in content or "<table" in content.lower()
            ]
            if table_pages:
                print(f"  Measurement regex/keyword 皆未命中，fallback table 頁: {len(table_pages)} 頁")
                measurement_pages = table_pages[:10]

    def _dedupe_pages(pages: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        seen = set()
        result = []
        for name, content in pages:
            key = (name, content[:200])
            if key in seen:
                continue
            seen.add(key)
            result.append((name, content))
        return result

    bom_pages = _dedupe_pages(bom_pages)
    measurement_pages = _dedupe_pages(measurement_pages)

    def _page_chunks(pages: List[Tuple[str, str]]) -> List[List[Tuple[str, str]]]:
        pages = _dedupe_pages(pages)
        return [pages[i:i + SECTION_CHUNK_PAGE_COUNT] for i in range(0, len(pages), SECTION_CHUNK_PAGE_COUNT)]

    def _build_chunk_text(chunk_pages: List[Tuple[str, str]]) -> Tuple[str, str]:
        source_label = ", ".join(name for name, _ in chunk_pages)
        chunk_text = "\n\n".join([f"--- {name} ---\n{content}" for name, content in chunk_pages])
        return source_label, chunk_text

    def _build_bom_prompt(source_label: str, text: str) -> str:
        return """你是服裝 Tech Pack BOM 資料抽取專家。請只根據本 chunk 內容抽取材料清單，不要推測。

來源頁:
{source_label}

本 chunk 內容:
{text}

請抽取本 chunk 中所有 BOM / Fabric / Trim / Label / Packaging / Wash / Graphic 材料項目。
若此 chunk 沒有 BOM 材料，回傳 {{"header_info": null, "items": []}}。

輸出 JSON:
{{
  "header_info": "頁眉資訊，例如 Concept/Updated Date/Status/Version；沒有則 null",
  "items": [
    {{
      "product_code": "材料編碼；沒有則 null",
      "material_name": "材料名稱原文；沒有則 null",
      "material_name_zh": "繁體中文名稱；沒有則可同原文",
      "category": "Fabric/Trim/Label/Packaging/Wash/Graphic/其他；沒有則 null",
      "usage": "用途/部位，例如 Body/Hem/Neck/Shell/Lining；沒有則 null",
      "quantity": "數量/用量；沒有則 null",
      "common_qty": "Common Qty；沒有則 null",
      "gauge": "Gauge；沒有則 null",
      "ends": "Ends；沒有則 null",
      "stitch_size": "Stitch size；沒有則 null",
      "allocated_supplier": "Allocated Supplier；沒有則 null",
      "composition": "成分；沒有則 null，禁止推測",
      "supplier": "供應商；沒有則 null",
      "color_info": "顏色資訊；沒有則 null",
      "color_code": "色號；沒有則 null",
      "supplier_article_number": "Supplier Article Number / Supplier Code；沒有則 null",
      "specifications": "其他規格；沒有則 null",
      "width": "幅寬；沒有則 null",
      "weight": "克重；沒有則 null",
      "comments": "Comments 原文逐字抽取；沒有則 null",
      "remarks": "其他備註原文逐字抽取；沒有則 null"
    }}
  ]
}}

規則:
1. 忠於原文，禁止 inferred/likely/possibly。
2. 不要把不是顏色的供應商編號誤放到 color_info。
3. 空欄位使用 null，不要編造。""".format(
            source_label=source_label,
            text=text,
        )

    def _build_measurement_prompt(source_label: str, text: str) -> str:
        return """You are a Tech Pack Measurement Chart extraction expert. Extract every measurement row visible in this chunk only.

Source pages:
{source_label}

Chunk content:
{text}

If this chunk contains no Measurement Chart / POM / size spec data, return {{"charts": []}}.

Output JSON:
{{
  "charts": [
    {{
      "chart_type": "Increment OR Absolute",
      "header_info": "Only Date/Time/Status/Version/page header; null if absent",
      "size_range": ["XS", "S", "M", "L", "XL", "XXL"],
      "base_size": "Base/sample size, null if absent",
      "grading_rule_name": "Grading rule name, null if absent",
      "unit": "inches or cm",
      "points": [
        {{
          "pom_code": "POM code, null if absent",
          "point_name": "Point name",
          "point_name_zh": "Traditional Chinese point name",
          "variation": "Only condition/location used to distinguish duplicated POM rows; null if absent",
          "description": "How-to-measure/methodology/codes; null if same as point_name",
          "tolerance_minus": "Tol -, null if absent",
          "tolerance_plus": "Tol +, null if absent",
          "values": {{"XS": "value", "S": "value", "M": "value", "L": "value", "XL": "value", "XXL": "value"}}
        }}
      ]
    }}
  ]
}}

Rules:
1. Extract all rows in this chunk. Do not drop duplicate POM codes.
2. Separate Increment and Absolute charts if both appear.
3. Preserve fractions such as 18 1/2, -3/8, +1/4 exactly.
4. Use null for missing fields. Do not infer values. """.format(
            source_label=source_label,
            text=text,
        )

    def _extract_bom_sections_chunked() -> List[Any]:
        chunks = _page_chunks(bom_pages)
        if not chunks:
            return []
        print(f"  Chunked BOM 提取: {len(chunks)} chunks / {len(bom_pages)} candidate pages")

        def _process_chunk(index: int, chunk_pages: List[Tuple[str, str]]) -> Optional[BOMSection]:
            source_label, chunk_text = _build_chunk_text(chunk_pages)
            chunk_text = _limit_prompt_text(chunk_text, BOM_MAIN_TEXT_LIMIT, f"BOM chunk {index + 1}", ctx, BOM_CONTEXT_KEYWORDS)
            prompt = _build_bom_prompt(source_label, chunk_text)
            _log(ctx, f"BOM chunk {index + 1}/{len(chunks)} source={source_label} prompt_chars={len(prompt)}")
            try:
                response, usage = ctx.gemini_client.generate_text(prompt)
                _track_tokens(ctx, "bom_chunk", usage)
                bom_data = parse_llm_json_response(response)
                section = _bom_section_from_llm_data(bom_data, source_label, chunk_text)
                count = len(section.items) if section else 0
                print(f"    BOM chunk {index + 1}/{len(chunks)} ({source_label}): {count} items")
                _log(ctx, f"BOM chunk {index + 1}/{len(chunks)} items={count}")
                return section
            except Exception as e:
                print(f"    [Warning] BOM chunk {index + 1} failed ({source_label}): {e}")
                _log(ctx, f"BOM chunk {index + 1} failed source={source_label}: {e}")
                return None

        import concurrent.futures
        sections: List[BOMSection] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(SECTION_CHUNK_MAX_WORKERS, len(chunks))) as executor:
            futures = [executor.submit(_process_chunk, idx, chunk) for idx, chunk in enumerate(chunks)]
            for future in futures:
                section = future.result()
                if section and section.items:
                    sections.append(section)

        merged = _merge_bom_sections(sections)
        print(f"  Chunked BOM 合併完成: chunks={len(chunks)} merged_items={sum(len(s.items) for s in merged)}")
        _log(ctx, f"Chunked BOM merged chunks={len(chunks)} sections={len(sections)} items={sum(len(s.items) for s in merged)}")
        return merged

    def _extract_measurement_sections_chunked() -> List[Any]:
        chunks = _page_chunks(measurement_pages)
        if not chunks:
            return []
        print(f"  Chunked Measurement 提取: {len(chunks)} chunks / {len(measurement_pages)} candidate pages")

        def _process_chunk(index: int, chunk_pages: List[Tuple[str, str]]) -> List[MeasurementSection]:
            source_label, chunk_text = _build_chunk_text(chunk_pages)
            chunk_text = _limit_prompt_text(
                chunk_text,
                MEASUREMENT_MAIN_TEXT_LIMIT,
                f"Measurement chunk {index + 1}",
                ctx,
                MEASUREMENT_CONTEXT_KEYWORDS,
            )
            prompt = _build_measurement_prompt(source_label, chunk_text)
            _log(ctx, f"Measurement chunk {index + 1}/{len(chunks)} source={source_label} prompt_chars={len(prompt)}")
            try:
                response, usage = ctx.gemini_client.generate_text(prompt)
                _track_tokens(ctx, "measurement_chunk", usage)
                measurement_data = parse_llm_json_response(response)
                sections = _measurement_sections_from_llm_data(measurement_data, source_label, chunk_text)
                count = sum(len(section.points) for section in sections)
                print(f"    Measurement chunk {index + 1}/{len(chunks)} ({source_label}): {count} points")
                _log(ctx, f"Measurement chunk {index + 1}/{len(chunks)} points={count}")
                return sections
            except Exception as e:
                print(f"    [Warning] Measurement chunk {index + 1} failed ({source_label}): {e}")
                _log(ctx, f"Measurement chunk {index + 1} failed source={source_label}: {e}")
                return []

        import concurrent.futures
        sections: List[MeasurementSection] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(SECTION_CHUNK_MAX_WORKERS, len(chunks))) as executor:
            futures = [executor.submit(_process_chunk, idx, chunk) for idx, chunk in enumerate(chunks)]
            for future in futures:
                sections.extend(future.result())

        merged = _merge_measurement_sections(sections)
        print(f"  Chunked Measurement 合併完成: chunks={len(chunks)} merged_points={sum(len(s.points) for s in merged)}")
        _log(ctx, f"Chunked Measurement merged chunks={len(chunks)} sections={len(sections)} points={sum(len(s.points) for s in merged)}")
        return merged
    
    def _extract_bom_sections() -> List[Any]:
        if not bom_pages:
            return []

        local_sections: List[Any] = []
        print(f"  提取 BOM 詳細資料 ({len(bom_pages)} 頁)...")
        bom_content = "\n\n".join([f"--- {name} ---\n{content}" for name, content in bom_pages])

        context_supplement = ""
        if json_files:
            supplement_texts = []
            # 只取前 5 頁，通常包含 Header 和 Fabric/Trim
            for jf in json_files[:5]:
                try:
                    with open(jf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        blocks = data.get("parsing_res_list", [])
                        page_text = "\n".join([b.get("block_content", "") for b in blocks if b.get("block_content")])
                        supplement_texts.append(f"--- Page {jf.stem} Raw Text ---\n{page_text}")
                except Exception as e:
                    print(f"Warning reading JSON {jf}: {e}")
            context_supplement = "\n\n".join(supplement_texts)
            context_supplement = _limit_prompt_text(
                context_supplement,
                BOM_CONTEXT_LIMIT,
                "BOM raw context",
                ctx,
                BOM_CONTEXT_KEYWORDS,
            )
        bom_main_text = _limit_prompt_text(
            bom_content,
            BOM_MAIN_TEXT_LIMIT,
            "BOM markdown",
            ctx,
            BOM_CONTEXT_KEYWORDS,
        )

        bom_prompt = """你是服裝 Tech Pack 分析專家。請分析以下 BOM (Bill of Materials) 內容，提取完整且詳細的材料清單。

原始內容 (Markdown Tables):
{text}

補充內容 (Raw JSON Text - 若 Markdown 表格不完整請參考此處):
{context_supplement}

請仔細尋找並提取**所有**材料項目。
特別注意：
1. **主布料 (Body Fabric / Shell)**：務必找出 Main Fabric / Body 區塊 (常見於前幾頁 Raw Text 中 - 尋找 '1059002' 或 'Body' 等關鍵字)。
2. **忠於原文**：Remarks 必須逐字提取 (Verbatim)，禁止加入 "Likely", "Possibly", "(inferred)" 等推測性詞語。若無明確資訊請留空。
3. **區塊完整性**：涵蓋 Fabric, Trim, Label, Packaging, Wash, Graphic 等所有區塊。
4. **顏色欄位準確性**：
   - Example 1: 表格右側顯示 "NAVY UNIFORM 802". -> color="NAVY UNIFORM 802", color_code="802" (若可拆分).
   - Example 2: "gks266340-2A" -> 這是 Supplier Article/Color，若無特定欄位可放 remarks 或 color_info，但不要把 "NAVY UNIFORM" 錯放。
   - **禁止推測成分**：若沒寫 "Cotton"，不要自作聰明填 "Cotton (inferred)"。

輸出為 JSON 格式，包含:
{{
  "header_info": "頁眉資訊 (提取 Concept/Updated Date/Status 等資訊)",
  "items": [
    {{
      "product_code": "材料編碼",
      "material_name": "材料名稱",
      "material_name_zh": "繁體中文名稱",
      "category": "類別",
      "usage": "用途/部位 (如 Body, Hem, Neck)",
      "quantity": "用量/數量 (若欄位是 Usage/Qty 請拆分)",
      "common_qty": "Common Qty",
      "gauge": "Gauge",
      "ends": "Ends",
      "stitch_size": "Stitch size",
      "allocated_supplier": "Allocated Supplier",
      "composition": "成分 (NO inferred data)",
      "supplier": "供應商",
      "color_info": "顏色名稱 (如 NAVY UNIFORM 802)",
      "supplier_article_number": "Supplier Article Number / Supplier Article / Supplier Code",
      "specifications": "規格描述",
      "width": "幅寬",
      "weight": "克重",
      "comments": "Comments/備註 (Verbatim extraction. DO NOT prepend labels. Just the content)",
      "remarks": "備註 (若 Comments 已使用，remarks 可留空)"
    }}
  ]
}}
""".format(text=bom_main_text, context_supplement=context_supplement)
        _log(ctx, f"BOM prompt chars={len(bom_prompt)} main={len(bom_main_text)} context={len(context_supplement)}")

        try:
            response, usage = ctx.gemini_client.generate_text(bom_prompt)
            _track_tokens(ctx, "bom", usage)
            print(f"    BOM 提取完成 (tokens: {usage.get('total_tokens', 0)} | In: {usage.get('prompt_tokens', 0)}, Out: {usage.get('candidate_tokens', 0)}, Cached: {usage.get('cached_tokens', 0)})")

            # 使用健壯的 JSON 解析
            bom_data = parse_llm_json_response(response)
            if bom_data and "items" in bom_data and bom_data["items"]:
                print(f"    解析到 {len(bom_data['items'])} 個 BOM 項目")

                # 轉換為 BOMSection
                bom_items = []
                for item in bom_data["items"]:
                    usage_value = item.get("usage") or item.get("usage_qty") or item.get("part")
                    part_value = usage_value or item.get("part") or ""
                    composition_value = item.get("composition")
                    if not composition_value:
                        for candidate in (
                            item.get("comments"),
                            item.get("remarks"),
                            item.get("material_name"),
                            item.get("material_name_zh"),
                            item.get("specifications"),
                        ):
                            composition_value = _extract_composition_from_text(candidate)
                            if composition_value:
                                break
                    bom_item = BOMItem(
                        part=BilingualField(
                            original=part_value,
                            zh=part_value
                        ),
                        usage=BilingualField(
                            original=usage_value,
                            zh=usage_value
                        ) if usage_value else None,
                        quantity=item.get("quantity") or item.get("qty"),
                        common_qty=item.get("common_qty"),
                        gauge=item.get("gauge"),
                        ends=item.get("ends"),
                        stitch_size=item.get("stitch_size"),
                        allocated_supplier=BilingualField(
                            original=item.get("allocated_supplier", ""),
                            zh=item.get("allocated_supplier", "")
                        ) if item.get("allocated_supplier") else None,
                        comments=BilingualField(
                            original=item.get("comments", ""),
                            zh=item.get("comments", "")
                        ) if item.get("comments") else None,
                        supplier_article_number=item.get("supplier_article_number") or item.get("supplier_article"),
                        product_code=item.get("product_code"),
                        material_name=BilingualField(
                            original=item.get("material_name", ""),
                            zh=item.get("material_name_zh", item.get("material_name", ""))
                        ) if item.get("material_name") else None,
                        composition=BilingualField(
                            original=composition_value,
                            zh=composition_value
                        ) if composition_value else None,
                        color=BilingualField(
                            original=item.get("color_info", ""),
                            zh=item.get("color_info", "")
                        ) if item.get("color_info") else None,
                        supplier=BilingualField(
                            original=item.get("supplier", ""),
                            zh=item.get("supplier", "")
                        ) if item.get("supplier") else None,
                        remarks=BilingualField(
                            original=item.get("remarks", ""),
                            zh=item.get("remarks", "")
                        ) if item.get("remarks") else None,
                        width=item.get("width"),
                        weight=item.get("weight"),
                    )
                    bom_items.append(bom_item)

                if bom_items:
                    header_info = bom_data.get("header_info")
                    if isinstance(header_info, (dict, list)):
                        header_info = json.dumps(header_info, ensure_ascii=False)

                    local_sections.append(BOMSection(items=bom_items, header_info=header_info))
            else:
                print("    [Warning] BOM JSON 解析失敗或無有效項目")
        except Exception as e:
            print(f"    [Warning] BOM LLM 提取失敗: {e}")

        return local_sections

    def _extract_measurement_sections() -> List[Any]:
        if not measurement_pages:
            return []

        local_sections: List[Any] = []
        print(f"  提取 Measurement 詳細資料 ({len(measurement_pages)} 頁)...")
        measurement_content = "\n\n".join([f"--- {name} ---\n{content}" for name, content in measurement_pages])
        context_supplement = ""
        if json_files:
            supplement_texts = []
            for jf in json_files:
                try:
                    with open(jf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        blocks = data.get("parsing_res_list", [])
                        page_text = "\n".join([b.get("block_content", "") for b in blocks if b.get("block_content")])
                        if re.search(measurement_regex, page_text, re.IGNORECASE):
                            supplement_texts.append(f"--- Page {jf.stem} Raw Text ---\n{page_text}")
                except Exception as e:
                    print(f"Warning reading JSON {jf}: {e}")
            context_supplement = "\n\n".join(supplement_texts)
            context_supplement = _limit_prompt_text(
                context_supplement,
                MEASUREMENT_CONTEXT_LIMIT,
                "Measurement raw context",
                ctx,
                MEASUREMENT_CONTEXT_KEYWORDS,
            )
        measurement_main_text = _limit_prompt_text(
            measurement_content,
            MEASUREMENT_MAIN_TEXT_LIMIT,
            "Measurement markdown",
            ctx,
            MEASUREMENT_CONTEXT_KEYWORDS,
        )

        measurement_prompt = """You are a Tech Pack Analysis Expert. Analyze the following Measurement Chart pages.

Original Content:
{text}

Supplement (Raw JSON Text - use if Markdown table is incomplete):
{context_supplement}

CRITICAL INSTRUCTIONS:

1. **DETECT CHART TYPE**: Tech Packs often contain BOTH Increment and Absolute charts:
   - **Increment Chart**: Values like "-3/8", "+1/4", "0". These are DIFFERENCES from base size.
   - **Absolute Chart**: Real garment measurements like "18 1/2", "24".
   - Look for "Grade Rule Display" or page header clues.

2. **CREATE SEPARATE CHARTS**: If you detect BOTH types, output them as separate objects in "charts" array.

3. **HANDLE DUPLICATE POM CODES**: Same POM code may appear multiple times with different measurement conditions:
   - Example: "i5.29" with "FLATTEN OUT FULLNESS" vs normal measurement.
   - Use "variation" field to distinguish (e.g., "relaxed", "flattened", "stretched").
   - DO NOT de-duplicate or merge rows with the same POM code.

4. **EXTRACT ALL ROWS**: Do NOT leave any row empty. If a value exists in PDF, extract it. Verify E9.4, Bicep, etc. are not empty.

Output JSON format:
{{
  "charts": [
    {{
      "chart_type": "Increment OR Absolute",
      "header_info": "Page header info (ONLY Date, Time, Status, Version. DO NOT include Season/Brand/Style)",
      "size_range": ["XS", "S", "M", "L", "XL", "XXL"],
      "base_size": "M",
      "grading_rule_name": "Name of grading rule if stated",
      "unit": "inches or cm",
      "points": [
        {{
          "pom_code": "POM Code",
          "point_name": "Point Name",
          "point_name_zh": "Traditional Chinese Name",
          "variation": "Location/Condition ONLY (e.g. '2\" above', 'Relaxed'). NO HTM info. NO method codes like (G).",
          "description": "Methodology & Codes (e.g. '(G)', 'Seam to Seam'). If identical to point name, return null. NO '(inferred)'",
          "tolerance_minus": "Tol -",
          "tolerance_plus": "Tol +",
          "values": {{"XS": "val", "S": "val", "M": "val", "L": "val", "XL": "val", "XXL": "val"}}
        }}
      ]
    }}
  ]
}}

REMEMBER:
- Header Info: DATES & STATUS only.
- Variation: Only used to disambiguate same POMs (e.g. different state).
- Description: Methodology. If none, keep null. DO NOT COPY Point Name.
- "-3/8" means NEGATIVE INCREMENT.
""".format(text=measurement_main_text, context_supplement=context_supplement)
        _log(ctx, f"Measurement prompt chars={len(measurement_prompt)} main={len(measurement_main_text)} context={len(context_supplement)}")

        try:
            response, usage = ctx.gemini_client.generate_text(measurement_prompt)
            _track_tokens(ctx, "measurement", usage)
            print(f"    Measurement 提取完成 (tokens: {usage.get('total_tokens', 0)} | In: {usage.get('prompt_tokens', 0)}, Out: {usage.get('candidate_tokens', 0)}, Cached: {usage.get('cached_tokens', 0)})")

            # 使用健壯的 JSON 解析
            measurement_data = parse_llm_json_response(response)

            # 處理新的 charts 陣列格式 或 舊的單一格式 (向後兼容)
            charts = measurement_data.get("charts", [])
            if not charts and "points" in measurement_data:
                # 向後兼容: 舊格式直接包含 points
                charts = [measurement_data]

            total_points = sum(len(c.get("points", [])) for c in charts)
            print(f"    解析到 {len(charts)} 個圖表, 共 {total_points} 個測量點")

            for chart in charts:
                chart_type = chart.get("chart_type")
                points_data = chart.get("points", [])
                if not points_data:
                    continue

                # 轉換為 MeasurementSection
                measurement_points = []
                for pt in points_data:
                    # 洗刷 variation
                    variation = pt.get("variation")
                    if variation:
                        variation = variation.replace("(inferred)", "").strip()
                        if not variation or variation == "null":
                            variation = None

                    # 洗刷 description (HTM)
                    description = pt.get("description")
                    point_name = pt.get("point_name") or ""

                    if description:
                        description = description.replace("(inferred)", "").strip()
                        # 若 description 與 point_name 高度相似，則視為 placeholder
                        if description.lower().replace(" ", "") == point_name.lower().replace(" ", ""):
                            description = None

                    mp = MeasurementPoint(
                        pom_code=pt.get("pom_code"),
                        point_name=BilingualField(
                            original=point_name,
                            zh=pt.get("point_name_zh") or point_name
                        ),
                        variation=variation,
                        unit=chart.get("unit", "inches"),
                        tolerance=f"-{pt.get('tolerance_minus', '')} / +{pt.get('tolerance_plus', '')}" if pt.get('tolerance_minus') else None,
                        tolerance_minus=pt.get('tolerance_minus'),
                        tolerance_plus=pt.get('tolerance_plus'),
                        values=pt.get("values", {}),
                        how_to_measure=BilingualField(
                            original=description,
                            zh=description
                        ) if description else None,
                    )
                    measurement_points.append(mp)

                if measurement_points:
                    header_info = chart.get("header_info")
                    if isinstance(header_info, (dict, list)):
                        header_info = json.dumps(header_info, ensure_ascii=False)

                    # 設定 value_format: 基於數據特徵自動判定
                    value_format = None
                    base_size = chart.get("base_size")

                    if chart_type == "Increment" and base_size:
                        # 檢查數據特徵
                        is_mixed = False

                        # 找任何一個 row 來檢查 pattern
                        for pt in measurement_points:
                            base_val = pt.values.get(base_size, "").strip()
                            # 如果 Base 值是數字且沒有 +/- 符號 (排除 0)
                            if base_val and re.match(r"^\d", base_val) and "0" != base_val and "+" not in base_val and "-" not in base_val:
                                # 檢查是否有其他尺碼是用 +/- 表示
                                for k, v in pt.values.items():
                                    if k != base_size and ("+" in str(v) or "-" in str(v)):
                                        is_mixed = True
                                        break
                            if is_mixed:
                                break

                        if is_mixed:
                            value_format = f"base_at_{base_size}_increments_elsewhere"
                        else:
                            # 預設如果全是 +/- 則是標準 Increment
                            value_format = "pure_increments"

                    measurement_section = MeasurementSection(
                        chart_type=chart_type if chart_type in ("Increment", "Absolute") else None,
                        value_format=value_format,
                        size_range=chart.get("size_range"),
                        sample_size=chart.get("base_size"),
                        grading_rules=chart.get("grading_rule_name") or chart.get("grading_rule"),
                        header_info=header_info,
                        points=measurement_points
                    )
                    local_sections.append(measurement_section)
                    print(f"      - {chart_type or 'Unknown'} chart: {len(measurement_points)} points")
        except Exception as e:
            print(f"    [Warning] Measurement LLM 提取失敗: {e}")

        return local_sections

    def _extract_bom_sections_with_fallback() -> List[Any]:
        chunked_sections = _extract_bom_sections_chunked()
        chunked_items = sum(len(section.items) for section in chunked_sections if isinstance(section, BOMSection))
        if chunked_items > 0:
            return chunked_sections
        print("  [Fallback] Chunked BOM 無結果，改用舊版大 prompt")
        _log(ctx, "Chunked BOM empty; fallback to legacy combined prompt")
        return _extract_bom_sections()

    def _extract_measurement_sections_with_fallback() -> List[Any]:
        chunked_sections = _extract_measurement_sections_chunked()
        chunked_points = sum(len(section.points) for section in chunked_sections if isinstance(section, MeasurementSection))
        if chunked_points > 0:
            return chunked_sections
        print("  [Fallback] Chunked Measurement 無結果，改用舊版大 prompt")
        _log(ctx, "Chunked Measurement empty; fallback to legacy combined prompt")
        return _extract_measurement_sections()

    # 並行化 BOM / Measurement 兩個 LLM 請求，維持輸出順序為 BOM -> Measurement
    if bom_pages or measurement_pages:
        import concurrent.futures
        bom_future = None
        measurement_future = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            if bom_pages:
                bom_future = executor.submit(_extract_bom_sections_with_fallback)
            if measurement_pages:
                measurement_future = executor.submit(_extract_measurement_sections_with_fallback)

            if bom_future:
                extracted_sections.extend(bom_future.result())
            if measurement_future:
                extracted_sections.extend(measurement_future.result())
    
    return extracted_sections


def classify_images_with_llm(
    imgs_dir: Path,
    ctx: ExtractionContext,
    clustered_results: Optional[Dict] = None
) -> List[ImageInfo]:
    """使用 LLM 分類圖片"""
    print("\n[3/5] 圖片分類...")
    
    image_infos = []
    
    if not imgs_dir.exists():
        print("  [Warning] imgs 資料夾不存在")
        return image_infos
    
    # 收集要處理的圖片
    images_to_process = []
    
    if clustered_results:
        # 使用聚類的最高分圖片
        for cluster_name, info in clustered_results.items():
            best_img = info.get("best_image")
            if best_img:
                img_path = imgs_dir / best_img
                if img_path.exists():
                    images_to_process.append((str(img_path), cluster_name))
    else:
        # 處理所有圖片
        supported_formats = {'.jpg', '.jpeg', '.png', '.webp'}
        for img_file in imgs_dir.iterdir():
            if img_file.suffix.lower() in supported_formats:
                images_to_process.append((str(img_file), None))
    
    print(f"  要處理 {len(images_to_process)} 張圖片 (使用並發處理)")

    # 定義單張處理函數
    def process_single_image(args):
        img_path, cluster_id = args
        try:
            if not (ctx.use_llm and ctx.gemini_client):
                return ImageInfo(image_path=img_path, image_type="Unknown", description=BilingualField(original="LLM Disabled", zh="LLM 未啟用"), cluster_id=cluster_id)

            result, usage = ctx.gemini_client.generate_structured(
                IMAGE_CLASSIFICATION_PROMPT,
                LLMImageClassification,
                image_path=img_path
            )
            _track_tokens(ctx, "image_classification", usage)
            
            return ImageInfo(
                image_path=img_path,
                image_type=result.image_type,
                description=BilingualField(
                    original=result.description_original,
                    zh=result.description_zh
                ),
                feature_tags=result.feature_tags,
                related_section=result.related_section,
                cluster_id=cluster_id,
                colorway_spec=result.colorway_spec,
                artwork_details=result.artwork_details,
                image_role=result.image_role
            )
        except Exception as e:
            print(f"    [Warning] 圖片分類失敗 {Path(img_path).name}: {e}")
            return None

    # 使用線程池並發處理
    import concurrent.futures
    # 限制並發數為 5 以避免觸發 API 速率限制
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 移除了 [:10] 限制，改為處理所有圖片 (或可設定 limit)
        futures = {executor.submit(process_single_image, item): item for item in images_to_process}
        
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                image_infos.append(res)
                print(f"    {Path(res.image_path).name}: {res.image_type}")

    
    # 標記主圖 (is_primary)
    # 先排序確保確定性
    image_infos.sort(key=lambda x: x.image_path)
    
    seen_groups = set()
    for info in image_infos:
        # 以 (相關區塊, 圖片類型) 為分組依據
        group_key = (info.related_section, info.image_type)
        if group_key not in seen_groups:
            # 第一張遇到的設為主圖
            info.is_primary = True
            seen_groups.add(group_key)

    return image_infos


def _strip_html_tags(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = cleaned.replace("&amp;", "&")
    cleaned = cleaned.replace("&lt;", "<")
    cleaned = cleaned.replace("&gt;", ">")
    cleaned = cleaned.replace("&quot;", "\"")
    return cleaned


def _normalize_email_text(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = _strip_html_tags(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_page_index_from_stem(stem: str) -> Optional[int]:
    parts = stem.split("_")
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return None


def _extract_image_paths_from_md(content: str, run_dir: Path) -> List[str]:
    img_paths = []
    html_matches = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
    md_matches = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", content)
    for raw in html_matches + md_matches:
        raw = raw.strip()
        if not raw or raw.startswith(("http://", "https://", "data:")):
            continue
        img_path = Path(raw)
        if not img_path.is_absolute():
            img_path = run_dir / raw
        if img_path.exists():
            img_paths.append(str(img_path))
    return img_paths


def _pick_best_image(image_paths: List[str]) -> Optional[str]:
    best_path = None
    best_size = -1
    for path_str in image_paths:
        try:
            size = Path(path_str).stat().st_size
        except OSError:
            size = -1
        if size > best_size:
            best_size = size
            best_path = path_str
    return best_path


def _looks_like_email(text: str) -> bool:
    text_lower = text.lower()
    matched = [kw for kw in EMAIL_KEYWORDS if kw.lower() in text_lower]
    header_hit = any(
        re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        for patterns in EMAIL_HEADER_PATTERNS.values()
        for pat in patterns
    )
    addr_hit = EMAIL_ADDRESS_RE.search(text) is not None
    if len(matched) >= 2:
        return True
    if len(matched) >= 1 and (header_hit or addr_hit):
        return True
    return header_hit and addr_hit


def _extract_email_fields_from_text(text: str) -> Dict[str, Any]:
    normalized = _normalize_email_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    fields: Dict[str, Any] = {
        "date": None,
        "sender": None,
        "recipient": None,
        "subject": None,
        "content_summary": None,
        "action_items": None,
    }
    header_line_idxs = set()

    for idx, line in enumerate(lines):
        for field, patterns in EMAIL_HEADER_PATTERNS.items():
            if fields.get(field):
                continue
            for pat in patterns:
                match = re.match(pat, line, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    if value:
                        fields[field] = value
                        header_line_idxs.add(idx)
                    break

    if not fields["date"]:
        date_match = re.search(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", normalized)
        if not date_match:
            date_match = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", normalized)
        if date_match:
            fields["date"] = date_match.group(0)

    if not fields["subject"]:
        for idx, line in enumerate(lines):
            if idx in header_line_idxs:
                continue
            if re.search(r"\b(RE|FW|FWD)\b[: ]", line, re.IGNORECASE) or "Outlook" in line:
                fields["subject"] = line
                break

    if not fields["subject"]:
        for idx, line in enumerate(lines):
            if idx in header_line_idxs:
                continue
            low = line.lower()
            if low.startswith(("hi", "dear", "hello", "hi,", "dear,")):
                continue
            if 5 <= len(line) <= 120:
                fields["subject"] = line
                break

    body_lines = [line for idx, line in enumerate(lines) if idx not in header_line_idxs]
    summary = " ".join(body_lines).strip()
    if summary:
        fields["content_summary"] = summary[:800].rstrip()

    action_items = []
    for line in body_lines:
        if re.match(r"^\s*(?:[-*•✓☐]|\d+\.)\s+", line):
            item = re.sub(r"^\s*(?:[-*•✓☐]|\d+\.)\s+", "", line).strip()
            if item:
                action_items.append(item)
    if action_items:
        fields["action_items"] = action_items

    return fields


def _collect_email_text_candidates(
    md_files: Optional[List[Path]],
    json_files: Optional[List[Path]],
    run_dir: Path,
) -> List[Dict[str, Any]]:
    candidates = []
    seen_pages = set()

    for md_file in md_files or []:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[Warning] Reading {md_file.name} failed: {e}")
            continue
        if not content or not _looks_like_email(content):
            continue
        page_no = _parse_page_index_from_stem(md_file.stem)
        image_paths = _extract_image_paths_from_md(content, run_dir)
        candidates.append({
            "source_page": page_no,
            "text": content,
            "image_paths": image_paths,
            "source_name": md_file.name,
        })
        if page_no is not None:
            seen_pages.add(page_no)

    for json_file in json_files or []:
        page_no = _parse_page_index_from_stem(json_file.stem)
        if page_no in seen_pages:
            continue
        data = load_json_file(str(json_file))
        blocks = data.get("parsing_res_list", [])
        text = "\n".join(
            str(b.get("block_content", ""))
            for b in blocks
            if b.get("block_content")
        )
        if not text or not _looks_like_email(text):
            continue
        candidates.append({
            "source_page": page_no,
            "text": text,
            "image_paths": [],
            "source_name": json_file.name,
        })

    return candidates


def _to_bilingual(text: Optional[str]) -> Optional[BilingualField]:
    if not text:
        return None
    return BilingualField(original=text, zh=text)


def _looks_like_construction(text: str) -> bool:
    text_lower = text.lower()
    hits = 0
    for kw in CONSTRUCTION_KEYWORDS:
        if kw.isascii():
            if kw in text_lower:
                hits += 1
        else:
            if kw in text:
                hits += 1
    if OPTION_MARKER_RE.search(text):
        return True
    return hits >= 2


def _collect_construction_text_candidates(
    md_files: Optional[List[Path]],
    json_files: Optional[List[Path]],
    run_dir: Path,
) -> List[Dict[str, Any]]:
    candidates = []
    seen_pages = set()

    for md_file in md_files or []:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[Warning] Reading {md_file.name} failed: {e}")
            continue
        if not content or not _looks_like_construction(content):
            continue
        page_no = _parse_page_index_from_stem(md_file.stem)
        image_paths = _extract_image_paths_from_md(content, run_dir)
        candidates.append({
            "source_page": page_no,
            "text": content,
            "image_paths": image_paths,
            "source_name": md_file.name,
        })
        if page_no is not None:
            seen_pages.add(page_no)

    for json_file in json_files or []:
        page_no = _parse_page_index_from_stem(json_file.stem)
        if page_no in seen_pages:
            continue
        data = load_json_file(str(json_file))
        blocks = data.get("parsing_res_list", [])
        text = "\n".join(
            str(b.get("block_content", ""))
            for b in blocks
            if b.get("block_content")
        )
        if not text or not _looks_like_construction(text):
            continue
        candidates.append({
            "source_page": page_no,
            "text": text,
            "image_paths": [],
            "source_name": json_file.name,
        })

    return candidates


def _extract_bullet_items(text: str, max_items: int = 20) -> List[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullet_lines = []
    for line in lines:
        if re.match(r"^[-*•·]?\s*\d+[\).]", line):
            bullet_lines.append(re.sub(r"^[-*•·]?\s*\d+[\).]\s*", "", line))
        elif re.match(r"^[-*•·]\s+", line):
            bullet_lines.append(re.sub(r"^[-*•·]\s+", "", line))
    if not bullet_lines:
        bullet_lines = [line for line in lines if len(line) >= 4]
    return [line[:300].strip() for line in bullet_lines[:max_items] if line.strip()]


def _extract_document_filenames(text: str) -> List[str]:
    cleaned = _strip_html_tags(text)
    matches = DOCUMENT_FILENAME_RE.findall(cleaned)
    out = []
    seen = set()
    for match in matches:
        name = match.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def _filter_component_items(items: List[str]) -> List[str]:
    filtered = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        low = cleaned.lower()
        if re.search(r"<[^>]+>", cleaned):
            continue
        if any(keyword in low for keyword in ("disclaimer", "all rights reserved", "confidential", "copyright")):
            continue
        if cleaned.startswith(("##", "#")):
            continue
        if "http://" in low or "https://" in low:
            continue
        if re.search(r"\b(component\s+type|status|created|modified|displaying|result)\b", low):
            continue
        if re.search(r"\btech\s+pack\b", low):
            continue
        filtered.append(cleaned)
    return filtered


def _extract_components_from_html_tables(content: str) -> List[Component]:
    components = []
    tables = parse_html_tables(content)
    if not tables:
        return components

    header_keywords = [
        "component", "type", "status", "created", "modified",
        "bomcolormatrix", "cc name", "cc status", "cc number",
        "product sustainability attribute", "displaying", "result",
    ]

    for table in tables:
        for row in table:
            row_text = " ".join(cell.strip() for cell in row if cell).strip()
            if not row_text:
                continue
            if re.search(r"displaying\s+\d+\s+result", row_text, re.IGNORECASE):
                continue
            if re.search(r"\bcentric\b", row_text, re.IGNORECASE):
                continue
            header_hits = sum(1 for kw in header_keywords if kw in row_text.lower())
            if header_hits >= 2:
                continue
            if not re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", row_text):
                continue

            if not any(re.search(r"\bdesign\s+bom\b", cell, re.IGNORECASE) for cell in row):
                continue

            name_cell = max(row, key=lambda c: len(re.sub(r"\s+", "", c or "")))
            name_cell = name_cell.strip()
            if not name_cell:
                continue

            other_cells = [c.strip() for c in row if c and c.strip() and c.strip() != name_cell]
            component_type = None
            for cell in other_cells:
                if re.search(r"\bBOM\b", cell, re.IGNORECASE):
                    component_type = cell
                    break
            specs_text = " | ".join(other_cells) if other_cells else None

            components.append(Component(
                component_name=BilingualField(original=name_cell, zh=name_cell),
                component_type=_to_bilingual(component_type) if component_type else None,
                specifications=_to_bilingual(specs_text) if specs_text else None,
            ))

    return components


def _extract_composition_from_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text_clean = _strip_html_tags(text)
    for line in text_clean.splitlines():
        if not COMPOSITION_KEYWORD_RE.search(line):
            continue
        if "%" not in line:
            continue
        match = re.search(r"(composition|content|fiber\s*content|成分|成份)\s*[:：]?\s*(.+)", line, re.IGNORECASE)
        value = match.group(2).strip() if match else line.strip()
        if "%" in value:
            return value
    return None


def _normalize_date_str(date_str: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not date_str:
        return None, None
    original = date_str.strip()
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", original)
    if match:
        year, month, day = match.groups()
        try:
            normalized = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            normalized = None
        return normalized, original
    return None, original


def _apply_note_date_normalization(note: ConstructionNote) -> None:
    normalized, original = _normalize_date_str(note.date)
    raw_text = note.raw_text or ""
    if original:
        note.date_original = original
    if normalized:
        if raw_text and not re.search(r"\b\d{4}\b", raw_text):
            if re.search(r"\b\d{1,2}[/-]\d{1,2}\b", raw_text):
                note.date_original = raw_text
                note.date = None
                return
        note.date = normalized
    else:
        note.date = None


def _extract_section_title(text: str, patterns: List[str]) -> Optional[str]:
    for line in text.splitlines():
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return re.sub(r"^[#>\s]+", "", line).strip()
    return None


def extract_simple_sections(
    md_files: Optional[List[Path]],
    run_dir: Path,
) -> List[Any]:
    extracted = []
    if not md_files:
        return extracted

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[Warning] Reading {md_file.name} failed: {e}")
            continue
        if not content:
            continue

        page_no = _parse_page_index_from_stem(md_file.stem)
        image_paths = _extract_image_paths_from_md(content, run_dir)

        for section_type in ("Documents", "Inspiration", "Components"):
            patterns = SECTION_PATTERNS.get(section_type, [])
            if not patterns:
                continue
            if not any(re.search(pat, content, re.IGNORECASE) for pat in patterns):
                continue

            title = _extract_section_title(content, patterns)
            content_clean = _strip_html_tags(content)
            items = _extract_bullet_items(content_clean)
            if section_type == "Components":
                component_items = _extract_components_from_html_tables(content)
                if component_items:
                    extracted.append(ComponentsSection(
                        items=component_items,
                        source_page=page_no,
                        raw_text=content[:4000],
                    ))
                continue

            section_items = [
                SimpleSectionItem(text=BilingualField(original=item, zh=item))
                for item in items
            ]

            if section_type == "Documents":
                doc_names = _extract_document_filenames(content)
                section_items = [
                    SimpleSectionItem(text=BilingualField(original=item, zh=item))
                    for item in doc_names
                ]
                extracted.append(DocumentsSection(
                    title=_to_bilingual(title),
                    items=section_items,
                    image_paths=None,
                    source_page=page_no,
                    raw_text=content[:4000],
                ))
            elif section_type == "Inspiration":
                extracted.append(InspirationSection(
                    title=_to_bilingual(title),
                    items=section_items,
                    image_paths=image_paths or None,
                    source_page=page_no,
                    raw_text=content[:4000],
                ))

    return extracted


def _apply_inspiration_image_overrides(
    images: List[ImageInfo],
    md_files: Optional[List[Path]],
    run_dir: Path,
) -> None:
    if not images or not md_files:
        return
    inspiration_patterns = SECTION_PATTERNS.get("Inspiration", [])
    if not inspiration_patterns:
        return
    inspiration_paths = set()
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if not any(re.search(pat, content, re.IGNORECASE) for pat in inspiration_patterns):
            continue
        for img_path in _extract_image_paths_from_md(content, run_dir):
            inspiration_paths.add(img_path)

    if not inspiration_paths:
        return
    for img in images:
        if img.image_path in inspiration_paths:
            img.related_section = "Inspiration"
            img.image_role = "inspiration"


def _is_option_like(option: ConstructionOption) -> bool:
    texts = []
    if option.option_id:
        texts.append(option.option_id)
    if option.title and option.title.original:
        texts.append(option.title.original)
    if option.summary and option.summary.original:
        texts.append(option.summary.original)
    return any(OPTION_MARKER_RE.search(text) for text in texts if text)


def _option_text_contains(option: ConstructionOption, pattern: str) -> bool:
    texts = []
    if option.option_id:
        texts.append(option.option_id)
    if option.title and option.title.original:
        texts.append(option.title.original)
    if option.summary and option.summary.original:
        texts.append(option.summary.original)
    for attr in option.attributes or []:
        if attr.name and attr.name.original:
            texts.append(attr.name.original)
        if attr.value and attr.value.original:
            texts.append(attr.value.original)
        if attr.notes and attr.notes.original:
            texts.append(attr.notes.original)
    return any(re.search(pattern, text, re.IGNORECASE) for text in texts if text)


def _apply_option_updates_from_notes(
    options: List[ConstructionOption],
    notes: List[ConstructionNote],
) -> None:
    if not options or not notes:
        return
    cancel_pattern = re.compile(r"(取消|cancel|remove|改為|改成|revised|update)", re.IGNORECASE)
    herringbone_pattern = re.compile(r"(人字車|herringbone)", re.IGNORECASE)
    zigzag_pattern = re.compile(r"(zig\s*zag|人字車|herringbone)", re.IGNORECASE)

    for note in notes:
        content = note.content.original if note.content else ""
        if not content:
            continue
        option_ids = OPTION_MARKER_RE.findall(content)
        if option_ids and cancel_pattern.search(content):
            for opt in options:
                if opt.option_id and any(opt.option_id in opt_id for opt_id in option_ids):
                    opt.status = opt.status or "revised"
                    opt.latest_update = opt.latest_update or note.date
                    opt.decision = opt.decision or _to_bilingual(content)

        if cancel_pattern.search(content) and herringbone_pattern.search(content):
            for opt in options:
                if _option_text_contains(opt, herringbone_pattern.pattern):
                    opt.status = opt.status or "superseded"
                    opt.latest_update = opt.latest_update or note.date
                    opt.decision = opt.decision or _to_bilingual(content)

def extract_email_notes(
    image_infos: List[ImageInfo],
    ctx: ExtractionContext,
    md_files: Optional[List[Path]] = None,
    json_files: Optional[List[Path]] = None,
) -> List[EmailNote]:
    """提取 Email 截圖中的資訊"""
    print("\n[4/5] 提取 Email 內容...")
    
    email_notes = []
    seen_keys = set()
    email_images = [img for img in image_infos if img.image_type == "Email截圖"]
    
    if not email_images:
        print("  未發現 Email 截圖")
        # Do not return here, continue to text extraction
    else:
        print(f"  發現 {len(email_images)} 張 Email 截圖")
    
    # Limit email processing to avoid excessive tokens if there are too many
    max_emails = 10
    if len(email_images) > max_emails:
        print(f"  [Info] Email 截圖過多，僅處理前 {max_emails} 張")
        email_images = email_images[:max_emails]

    for img in email_images:
        try:
            print(f"  正在分析 Email: {Path(img.image_path).name} ...")
            
            if not (ctx.use_llm and ctx.gemini_client):
                 continue

            result, usage = ctx.gemini_client.generate_structured(
                EMAIL_EXTRACTION_PROMPT,
                EmailNote,
                image_path=img.image_path
            )
            _track_tokens(ctx, "email", usage)
            
            # 補完 image_path 資訊
            result.image_path = img.image_path
            result.source_page = img.source_page
            
            email_notes.append(result)
            if img.image_path:
                seen_keys.add(("image", img.image_path))
            if img.source_page is not None:
                seen_keys.add(("page", img.source_page))
            
        except Exception as e:
            print(f"    [Error] 分析 Email 失敗 ({Path(img.image_path).name}): {e}")



    # --- Text Based Extraction ---
    print(f"DEBUG: md_files={len(md_files) if md_files else None}, json_files={len(json_files) if json_files else None}, use_llm={ctx.use_llm}, has_client={bool(ctx.gemini_client)}")

    candidates = _collect_email_text_candidates(md_files, json_files, ctx.run_dir)
    if candidates:
        print(f"  Found {len(candidates)} email text candidates")
    else:
        print("  No email text candidates found")

    max_text_emails = 10
    if len(candidates) > max_text_emails:
        print(f"  [Info] Email 文字候選過多，僅處理前 {max_text_emails} 筆")
        candidates = candidates[:max_text_emails]

    for candidate in candidates:
        source_page = candidate.get("source_page")
        image_path = _pick_best_image(candidate.get("image_paths", []))
        if image_path and ("image", image_path) in seen_keys:
            continue
        if source_page is not None and ("page", source_page) in seen_keys:
            continue

        text = candidate.get("text", "")
        fallback = _extract_email_fields_from_text(text)

        if ctx.use_llm and ctx.gemini_client:
            try:
                result, usage = ctx.gemini_client.generate_structured(
                    EMAIL_EXTRACTION_PROMPT + f"\n\nEmail Text Content:\n{text[:5000]}",
                    EmailNote,
                    image_path=image_path,
                )
                _track_tokens(ctx, "email", usage)

                if not result.subject and fallback.get("subject"):
                    result.subject = _to_bilingual(fallback.get("subject"))
                if not result.content_summary and fallback.get("content_summary"):
                    result.content_summary = _to_bilingual(fallback.get("content_summary"))
                if not result.sender and fallback.get("sender"):
                    result.sender = fallback.get("sender")
                if not result.recipient and fallback.get("recipient"):
                    result.recipient = fallback.get("recipient")
                if not result.date and fallback.get("date"):
                    result.date = fallback.get("date")
                if not result.action_items and fallback.get("action_items"):
                    items = [_to_bilingual(item) for item in fallback.get("action_items", []) if item]
                    result.action_items = items or None

                if result.source_page is None:
                    result.source_page = source_page
                if result.image_path is None:
                    result.image_path = image_path

                email_notes.append(result)
                if image_path:
                    seen_keys.add(("image", image_path))
                if source_page is not None:
                    seen_keys.add(("page", source_page))
                continue
            except Exception as e:
                print(f"    [Error] 提取 Email 文字失敗 ({candidate.get('source_name')}): {e}")

        if fallback.get("content_summary") or fallback.get("subject"):
            email_note = EmailNote(
                date=fallback.get("date"),
                sender=fallback.get("sender"),
                recipient=fallback.get("recipient"),
                subject=_to_bilingual(fallback.get("subject")),
                content_summary=_to_bilingual(fallback.get("content_summary")),
                action_items=[_to_bilingual(item) for item in fallback.get("action_items", []) if item] or None,
                source_page=source_page,
                image_path=image_path,
            )
            email_notes.append(email_note)
            if image_path:
                seen_keys.add(("image", image_path))
            if source_page is not None:
                seen_keys.add(("page", source_page))

    return email_notes


def _parse_key_value_lines(text: str) -> List[ConstructionOptionAttribute]:
    attributes = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if ":" not in cleaned and "：" not in cleaned:
            continue
        parts = re.split(r"[:：]", cleaned, maxsplit=1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()
        value = parts[1].strip()
        if not key or not value:
            continue
        attributes.append(ConstructionOptionAttribute(
            name=BilingualField(original=key, zh=key),
            value=BilingualField(original=value, zh=value),
        ))
    return attributes


def _extract_options_from_text(text: str, page_no: Optional[int]) -> List[ConstructionOption]:
    matches = list(OPTION_MARKER_RE.finditer(text))
    if not matches:
        return []
    options = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        segment = text[start:end].strip()
        option_id = match.group(0).strip()
        segment_clean = _normalize_email_text(segment)
        summary = segment_clean.replace(option_id, "", 1).strip()
        attributes = _parse_key_value_lines(segment_clean)
        options.append(ConstructionOption(
            option_id=option_id,
            summary=_to_bilingual(summary[:800]) if summary else None,
            attributes=attributes or None,
            source_page=page_no,
            raw_text=segment[:1000],
        ))
    return options


def _extract_notes_from_text(text: str, page_no: Optional[int]) -> List[ConstructionNote]:
    notes = []
    normalized = _normalize_email_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    date_pattern = re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b")
    for line in lines:
        if date_pattern.search(line) or re.search(r"\bTD\b|\bRECAP\b|\bMEETING\b", line, re.IGNORECASE):
            source = None
            if re.search(r"\bTD\b", line, re.IGNORECASE):
                source = "TD"
            elif re.search(r"\bRECAP\b", line, re.IGNORECASE):
                source = "RECAP"
            elif re.search(r"\bMEETING\b", line, re.IGNORECASE):
                source = "MEETING"
            notes.append(ConstructionNote(
                date=date_pattern.search(line).group(0) if date_pattern.search(line) else None,
                source=_to_bilingual(source) if source else None,
                content=_to_bilingual(line),
                source_page=page_no,
                raw_text=line[:800],
            ))
    if not notes and lines:
        notes.append(ConstructionNote(
            content=_to_bilingual(" ".join(lines)[:800]),
            source_page=page_no,
            raw_text=normalized[:1000],
        ))
    return notes


def extract_construction_notes_and_options(
    ctx: ExtractionContext,
    md_files: Optional[List[Path]] = None,
    json_files: Optional[List[Path]] = None,
) -> Tuple[List[ConstructionNote], List[ConstructionOption]]:
    print("\n[4.5/5] 提取作工備註/選項...")
    notes: List[ConstructionNote] = []
    options: List[ConstructionOption] = []
    seen_option_keys = set()

    candidates = _collect_construction_text_candidates(md_files, json_files, ctx.run_dir)
    if not candidates:
        print("  未發現作工相關文字候選")
        return notes, options
    _log(ctx, f"Construction candidates total: {len(candidates)}")
    for idx, candidate in enumerate(candidates, start=1):
        name = candidate.get("source_name")
        page = candidate.get("source_page")
        text_len = len(candidate.get("text", ""))
        _log(ctx, f"  #{idx:02d} {name} page={page} text_len={text_len}")

    max_candidates = 8
    if len(candidates) > max_candidates:
        print(f"  [Info] 作工文字候選過多，僅處理前 {max_candidates} 筆")
        _log(ctx, f"Construction candidates truncated to first {max_candidates}")
        candidates = candidates[:max_candidates]

    for candidate in candidates:
        text = candidate.get("text", "")
        source_page = candidate.get("source_page")
        image_path = _pick_best_image(candidate.get("image_paths", []))

        if ctx.use_llm and ctx.gemini_client:
            try:
                result, usage = ctx.gemini_client.generate_structured(
                    CONSTRUCTION_EXTRACTION_PROMPT + f"\n\nText:\n{text[:6000]}",
                    ConstructionExtractionResult,
                    image_path=image_path,
                )
                _track_tokens(ctx, "construction", usage)
                for opt in result.options or []:
                    if not _is_option_like(opt):
                        note_text = None
                        if opt.summary and opt.summary.original:
                            note_text = opt.summary.original
                        elif opt.title and opt.title.original:
                            note_text = opt.title.original
                        if note_text:
                            note = ConstructionNote(
                                content=_to_bilingual(note_text),
                                source_page=source_page,
                                raw_text=opt.raw_text or text[:1000],
                            )
                            _apply_note_date_normalization(note)
                            notes.append(note)
                        continue
                    if opt.source_page is None:
                        opt.source_page = source_page
                    if opt.raw_text is None:
                        opt.raw_text = text[:1000]
                    key = (opt.option_id or opt.summary.original if opt.summary else "") + f":{source_page}"
                    if key in seen_option_keys:
                        continue
                    seen_option_keys.add(key)
                    options.append(opt)
                for note in result.notes or []:
                    if note.source_page is None:
                        note.source_page = source_page
                    if note.raw_text is None:
                        note.raw_text = text[:1000]
                    _apply_note_date_normalization(note)
                    notes.append(note)
                continue
            except Exception as e:
                print(f"    [Error] 作工抽取失敗 ({candidate.get('source_name')}): {e}")

        fallback_options = _extract_options_from_text(text, source_page)
        for opt in fallback_options:
            key = (opt.option_id or opt.summary.original if opt.summary else "") + f":{source_page}"
            if key in seen_option_keys:
                continue
            seen_option_keys.add(key)
            options.append(opt)
        for note in _extract_notes_from_text(text, source_page):
            _apply_note_date_normalization(note)
            notes.append(note)

    _apply_option_updates_from_notes(options, notes)
    return notes, options


def _enrich_construction_notes_from_emails(
    notes: List[ConstructionNote],
    email_notes: List[EmailNote],
) -> None:
    if not notes or not email_notes:
        return

    email_payloads = []
    for idx, email in enumerate(email_notes):
        text_parts = []
        if email.subject and email.subject.original:
            text_parts.append(email.subject.original)
        if email.content_summary and email.content_summary.original:
            text_parts.append(email.content_summary.original)
        email_text = " ".join(text_parts).lower()
        email_payloads.append({
            "index": idx,
            "text": email_text,
            "date": email.date,
        })

    for note in notes:
        if note.date and note.source:
            continue
        note_text = note.content.original if note.content and note.content.original else ""
        if not note_text:
            continue
        tokens = [t for t in re.split(r"\W+", note_text.lower()) if len(t) >= 4]
        best = None
        best_hits = 0
        for payload in email_payloads:
            hits = sum(1 for token in tokens if token in payload["text"])
            if hits > best_hits:
                best_hits = hits
                best = payload
        if best and best_hits >= 2:
            if not note.date and best.get("date"):
                note.date = best.get("date")
            if not note.source:
                source_value = "Email"
                if "review" in best["text"] or "客評" in best["text"] or "評語" in best["text"]:
                    source_value = "Customer Review"
                note.source = _to_bilingual(source_value)


# ==============================================================================
# Async 版本提取函數 — 將 sync LLM 呼叫包裝成 async
# ==============================================================================

async def _async_extract_sections_with_llm(
    full_text: str,
    ctx: ExtractionContext,
    md_files: List[Path],
    json_files: Optional[List[Path]] = None,
) -> List[Any]:
    """非同步版 extract_sections_with_llm — 用 asyncio.to_thread 包裝"""
    return await asyncio.to_thread(
        extract_sections_with_llm, full_text, ctx, md_files, json_files
    )


async def _async_classify_images_with_llm(
    imgs_dir: Path,
    ctx: ExtractionContext,
    clustered_results: Optional[Dict] = None,
) -> List[ImageInfo]:
    """
    非同步版 classify_images_with_llm — 用 AsyncGeminiClient 真正並行。
    如果沒有 async_gemini_client 則 fallback 到 sync 版。
    """
    if not (ctx.use_llm and ctx.async_gemini_client):
        return await asyncio.to_thread(
            classify_images_with_llm, imgs_dir, ctx, clustered_results
        )

    print("\n[3/5] 圖片分類 (Native Async)...")

    if not imgs_dir.exists():
        print("  [Warning] imgs 資料夾不存在")
        return []

    images_to_process = []
    if clustered_results:
        for cluster_name, info in clustered_results.items():
            best_img = info.get("best_image")
            if best_img:
                img_path = imgs_dir / best_img
                if img_path.exists():
                    images_to_process.append((str(img_path), cluster_name))
    else:
        supported_formats = {'.jpg', '.jpeg', '.png', '.webp'}
        for img_file in imgs_dir.iterdir():
            if img_file.suffix.lower() in supported_formats:
                images_to_process.append((str(img_file), None))

    print(f"  要處理 {len(images_to_process)} 張圖片 (asyncio.gather 並行)")

    async def process_one(img_path: str, cluster_id):
        try:
            result, usage = await ctx.async_gemini_client.generate_structured(
                IMAGE_CLASSIFICATION_PROMPT,
                LLMImageClassification,
                image_path=img_path,
            )
            _track_tokens(ctx, "image_classification", usage)
            return ImageInfo(
                image_path=img_path,
                image_type=result.image_type,
                description=BilingualField(
                    original=result.description_original,
                    zh=result.description_zh,
                ),
                feature_tags=result.feature_tags,
                related_section=result.related_section,
                cluster_id=cluster_id,
                colorway_spec=result.colorway_spec,
                artwork_details=result.artwork_details,
                image_role=result.image_role,
            )
        except Exception as e:
            print(f"    [Warning] 圖片分類失敗 {Path(img_path).name}: {e}")
            return None

    results = await asyncio.gather(
        *(process_one(p, c) for p, c in images_to_process),
        return_exceptions=True,
    )

    image_infos = []
    for r in results:
        if isinstance(r, Exception):
            print(f"    [Warning] 圖片分類例外: {r}")
        elif r is not None:
            image_infos.append(r)
            print(f"    {Path(r.image_path).name}: {r.image_type}")

    # 標記主圖
    image_infos.sort(key=lambda x: x.image_path)
    seen_groups = set()
    for info in image_infos:
        group_key = (info.related_section, info.image_type)
        if group_key not in seen_groups:
            info.is_primary = True
            seen_groups.add(group_key)

    return image_infos


async def _async_extract_email_notes(
    image_infos: List[ImageInfo],
    ctx: ExtractionContext,
    md_files: Optional[List[Path]] = None,
    json_files: Optional[List[Path]] = None,
) -> List[EmailNote]:
    """非同步版 extract_email_notes — 用 asyncio.to_thread 包裝"""
    return await asyncio.to_thread(
        extract_email_notes, image_infos, ctx, md_files, json_files
    )


async def _async_extract_construction(
    ctx: ExtractionContext,
    md_files: Optional[List[Path]] = None,
    json_files: Optional[List[Path]] = None,
) -> Tuple[List, List]:
    """非同步版 extract_construction_notes_and_options"""
    return await asyncio.to_thread(
        extract_construction_notes_and_options, ctx, md_files, json_files
    )


# ==============================================================================
# 主要非同步提取函數 — asyncio.gather 全並行
# ==============================================================================

async def extract_techpack_async(
    run_dir: str,
    api_key: Optional[str] = None,
    clustered_results: Optional[Dict] = None,
    config: Optional[Any] = None,
    ctx: Optional[ExtractionContext] = None,
    pre_classified_images: Optional[List[Dict]] = None,
    progress_callback: Optional[Any] = None,
    image_provider_callback: Optional[Any] = None,
    use_vertex: bool = False,
) -> TechPackStructured:
    """主要提取函數 (非同步版)

    Args:
        run_dir: OCR 輸出目錄
        api_key: Gemini / Vertex AI API Key
        clustered_results: 聚類結果 (舊版相容)
        config: 萃取配置
        ctx: 萃取上下文
        pre_classified_images: 預先分類的圖片列表
        progress_callback: 進度回呼
        image_provider_callback: 圖片提供者回呼
        use_vertex: 是否使用 Vertex AI
    """
    from .llm import HAS_GENAI

    run_path = Path(run_dir)
    if not run_path.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    if ctx is None:
        gemini_client = None
        async_client = None
        use_llm = False
        if api_key and HAS_GENAI:
            try:
                gemini_client = GeminiClient(api_key, use_vertex=use_vertex)
                async_client = AsyncGeminiClient(api_key, use_vertex=use_vertex)
                use_llm = True
                mode_str = "Vertex AI" if use_vertex else "AI Studio"
                print(f"Gemini API 已連接 ({mode_str})")
            except Exception as e:
                print(f"[Warning] Gemini 初始化失敗: {e}")
        ctx = ExtractionContext(
            run_dir=run_path,
            api_key=api_key,
            gemini_client=gemini_client,
            async_gemini_client=async_client,
            use_llm=use_llm,
            config=config,
            progress_callback=progress_callback,
        )
    else:
        ctx.run_dir = run_path
        ctx.api_key = api_key
        ctx.config = config
        if progress_callback:
            ctx.progress_callback = progress_callback
        if ctx.gemini_client is None and api_key and HAS_GENAI:
            try:
                ctx.gemini_client = GeminiClient(api_key, use_vertex=use_vertex)
                ctx.async_gemini_client = AsyncGeminiClient(api_key, use_vertex=use_vertex)
                ctx.use_llm = True
                mode_str = "Vertex AI" if use_vertex else "AI Studio"
                print(f"Gemini API 已連接 ({mode_str})")
            except Exception as e:
                print(f"[Warning] Gemini 初始化失敗: {e}")

    # Helper to report progress safely
    def report_progress(p: float, msg: str):
        if ctx and ctx.progress_callback:
            try:
                ctx.progress_callback(p, msg)
            except Exception:
                pass
        print(f"[Progress {int(p)}%] {msg}")

    report_progress(5, "初始化完成，開始收集檔案...")

    # 收集檔案
    files = collect_ocr_files(run_path)

    # 合併 Markdown
    full_text = merge_all_markdown(files["md_files"])

    if not full_text:
        print("[Error] 沒有可處理的 Markdown 內容")
        return TechPackStructured()

    report_progress(10, "全並行處理啟動中 (asyncio)...")

    # ==================================================================
    # 全並行處理 (asyncio.gather)
    # ==================================================================
    import time as _time
    _gather_start = _time.time()
    print("\n[Async Parallel] 全速啟動: Basic Info / 區塊 / 圖片+Email / 作工備註 同時進行")

    _task_timings = {}  # task_name -> (start, end)

    async def _task_basic_info():
        """Task 1: Basic Info (regex + HTML parsing, 快速)"""
        t0 = _time.time()
        result = await asyncio.to_thread(extract_with_hard_matching, full_text, config)
        _task_timings["Basic Info"] = (_time.time() - t0)
        report_progress(30, "Basic Info 提取完成")
        return result

    async def _task_sections():
        """Task 2: 區塊提取 (BOM, Measurement...)"""
        t0 = _time.time()
        result = await _async_extract_sections_with_llm(
            full_text, ctx, files["md_files"], files["json_files"]
        )
        _task_timings["Sections (BOM+Measurement)"] = (_time.time() - t0)
        report_progress(50, "區塊提取完成")
        return result

    async def _task_images_and_emails():
        """Task 3: 圖片分類 + Email 提取"""
        t0 = _time.time()
        report_progress(15, "正在分類圖片與提取 Email...")
        local_images = []
        raw_images_data = pre_classified_images

        if not raw_images_data and image_provider_callback:
            import inspect
            if inspect.iscoroutinefunction(image_provider_callback):
                print("[Info] 執行圖片處理回呼 (Native Async)...")
                raw_images_data = await image_provider_callback()
            else:
                print("[Info] 執行圖片處理回呼 (Sync → Thread)...")
                raw_images_data = await asyncio.to_thread(image_provider_callback)

        _img_done = _time.time()

        if raw_images_data:
            print(f"[Info] 使用預分類/回呼結果: {len(raw_images_data)} 張圖片")
            for pc in raw_images_data:
                description_text = pc.get("description", "")
                img_type_val = pc.get("img_type", "其他")
                local_images.append(ImageInfo(
                    image_id=str(pc.get("image_id", "")),
                    image_path=pc.get("image_path", ""),
                    image_type=img_type_val,
                    description=BilingualField(original=description_text, zh=description_text),
                    feature_tags=pc.get("feature_tags", []),
                    is_primary=img_type_val in ["成衣實體設計圖", "平面線段設計圖"],
                    source_page=0
                ))
        else:
            print("[Info] 無預分類結果，執行 LLM 圖片分類...")
            local_images = await _async_classify_images_with_llm(
                files["imgs_dir"], ctx, clustered_results
            )

        _apply_inspiration_image_overrides(local_images, files["md_files"], ctx.run_dir)
        _task_timings["Image Classification"] = (_time.time() - t0)
        print(f"[Timing] Image Classification: {_time.time() - t0:.2f}s")

        _email_start = _time.time()
        local_emails = await _async_extract_email_notes(
            local_images, ctx, files["md_files"], files["json_files"]
        )
        _task_timings["Email Extraction"] = (_time.time() - _email_start)
        _task_timings["Images+Email (Total)"] = (_time.time() - t0)
        report_progress(70, "圖片與 Email 提取完成")
        return local_images, local_emails

    async def _task_construction():
        """Task 4: 作工備註/選項"""
        t0 = _time.time()
        result = await _async_extract_construction(
            ctx, files["md_files"], files["json_files"]
        )
        _task_timings["Construction Notes"] = (_time.time() - t0)
        report_progress(80, "作工備註提取完成")
        return result

    # asyncio.gather — 全部同時啟動
    results = await asyncio.gather(
        _task_basic_info(),
        _task_sections(),
        _task_images_and_emails(),
        _task_construction(),
        return_exceptions=True,
    )
    _gather_elapsed = _time.time() - _gather_start

    # ── 耗時摘要 ──
    print("\n" + "="*60)
    print("  Extraction Timing Summary")
    print("="*60)
    for name, elapsed in sorted(_task_timings.items(), key=lambda x: -x[1]):
        bar = "█" * int(min(elapsed / max(_gather_elapsed, 0.01) * 30, 30))
        print(f"  {name:<30s} {elapsed:>7.2f}s  {bar}")
    print("-"*60)
    print(f"  {'Total Wall Time':<30s} {_gather_elapsed:>7.2f}s")
    print("="*60 + "\n")

    # 解析結果 (帶例外處理)
    basic_info = BasicInfo()
    sections = []
    images = []
    email_notes = []
    construction_notes = []
    construction_options = []

    # Task 1: Basic Info
    if isinstance(results[0], Exception):
        print(f"[Error] Basic Info Task 失敗: {results[0]}")
    else:
        basic_info = results[0]
        print("[Async] Basic Info 提取完成")

    # Task 2: Sections
    if isinstance(results[1], Exception):
        print(f"[Error] 區塊提取 Task 失敗: {results[1]}")
    else:
        sections = results[1]
        print("[Async] 區塊提取完成")

        # Post-process: Measurement Translation Fallback
        MEASUREMENT_MAPPING = {
            "neck width": "領寬", "front neck drop": "前領深", "back neck drop": "後領深",
            "chest": "胸圍", "bust": "胸圍", "waist": "腰圍", "hip": "臀圍", "seat": "臀圍",
            "sleeve length": "袖長", "across shoulder": "肩寬", "shoulder width": "肩寬",
            "body length": "衣長", "bottom opening": "下擺", "sweep": "下擺", "hem": "下擺",
            "armhole": "袖攏", "cuff opening": "袖口", "cuff width": "袖口寬",
            "trim height": "邊飾高度", "collar height": "領高", "inseam": "褲內長", "outseam": "褲長",
            "thigh": "大腿圍", "knee": "膝圍", "leg opening": "褲口寬"
        }

        for section in sections:
            if section.section_type == "Measurement" and hasattr(section, 'points') and section.points:
                for point in section.points:
                    if point.point_name and hasattr(point.point_name, 'original') and point.point_name.original:
                        orig = point.point_name.original
                        zh = point.point_name.zh
                        if not zh or zh == orig or zh == "-":
                            orig_lower = orig.lower().strip()
                            if orig_lower in MEASUREMENT_MAPPING:
                                point.point_name.zh = MEASUREMENT_MAPPING[orig_lower]
                            else:
                                for key, val in MEASUREMENT_MAPPING.items():
                                    if key in orig_lower:
                                        point.point_name.zh = val
                                        break

    # Task 3: Images + Email
    if isinstance(results[2], Exception):
        print(f"[Error] 圖片/Email Task 失敗: {results[2]}")
    else:
        images, email_notes = results[2]
        print("[Async] 圖片與 Email 提取完成")

    # Task 4: Construction
    if isinstance(results[3], Exception):
        print(f"[Error] 作工備註 Task 失敗: {results[3]}")
    else:
        construction_notes, construction_options = results[3]
        print("[Async] 作工備註提取完成")

    # 補抓 Documents / Components / Inspiration (快速，本地 regex)
    report_progress(92, "正在執行額外區塊補抓...")
    extra_sections = extract_simple_sections(files["md_files"], ctx.run_dir)
    if extra_sections:
        sections.extend(extra_sections)

    # Enrichment: Email -> Construction Notes
    _enrich_construction_notes_from_emails(construction_notes, email_notes)

    # 組裝結果
    report_progress(95, "正在組裝最終結構化輸出...")

    # Token 統計 — 合併 sync + async client（兩者可能分別被不同階段使用）
    _sync = ctx.gemini_client
    _async = ctx.async_gemini_client
    _total_tokens = (_sync.total_tokens if _sync else 0) + (_async.total_tokens if _async else 0)
    _prompt_tokens = (_sync.prompt_tokens if _sync else 0) + (_async.prompt_tokens if _async else 0)
    _candidate_tokens = (_sync.candidate_tokens if _sync else 0) + (_async.candidate_tokens if _async else 0)
    _cached_tokens = (_sync.cached_tokens if _sync else 0) + (_async.cached_tokens if _async else 0)

    print(f"\n[Token Debug] sync_client: total={_sync.total_tokens if _sync else 'N/A'}, "
          f"prompt={_sync.prompt_tokens if _sync else 'N/A'}, "
          f"candidate={_sync.candidate_tokens if _sync else 'N/A'}")
    print(f"[Token Debug] async_client: total={_async.total_tokens if _async else 'N/A'}, "
          f"prompt={_async.prompt_tokens if _async else 'N/A'}, "
          f"candidate={_async.candidate_tokens if _async else 'N/A'}")
    print(f"[Token Debug] combined: total={_total_tokens}, prompt={_prompt_tokens}, candidate={_candidate_tokens}")

    result = TechPackStructured(
        basic_info=basic_info,
        sections=sections,
        images=images,
        email_notes=email_notes,
        construction_notes=construction_notes,
        construction_options=construction_options,
        metadata=DocumentMetadata(
            filename=run_path.name,
            total_pages=len(files["json_files"]),
            extraction_version="1.0.0"
        ),
        extraction_summary={
            "sections_detected": len(sections),
            "images_processed": len(images),
            "email_notes": len(email_notes),
            "construction_notes": len(construction_notes),
            "construction_options": len(construction_options),
            "llm_tokens_used": _total_tokens,
            "llm_input_tokens": _prompt_tokens,
            "llm_output_tokens": _candidate_tokens,
            "llm_cached_tokens": _cached_tokens,
        }
    )
    _ensure_bilingual_translations(result)

    return result


def extract_techpack(
    run_dir: str,
    api_key: Optional[str] = None,
    clustered_results: Optional[Dict] = None,
    config: Optional[Any] = None,
    ctx: Optional[ExtractionContext] = None,
    pre_classified_images: Optional[List[Dict]] = None,
    progress_callback: Optional[Any] = None,
    image_provider_callback: Optional[Any] = None,
    use_vertex: bool = False,
) -> TechPackStructured:
    """同步版 wrapper — 內部用 asyncio.run() 呼叫 async 版本"""
    return asyncio.run(extract_techpack_async(
        run_dir=run_dir,
        api_key=api_key,
        clustered_results=clustered_results,
        config=config,
        ctx=ctx,
        pre_classified_images=pre_classified_images,
        progress_callback=progress_callback,
        image_provider_callback=image_provider_callback,
        use_vertex=use_vertex,
    ))
