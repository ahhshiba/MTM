# app/services/extraction/patterns.py
"""
Extraction Regex Patterns
自 techpack_extractor.py 提取的 Regex 模式
"""

# ==============================================================================
# 硬比對 (Regex) 模式
# ==============================================================================

HARD_MATCH_PATTERNS = {
    # Style / 款號
    "style_no": [
        r"(?:Style\s*(?:No\.?|Number|#)?|款號|款式編號|Article\s*No\.?)[:\s]*([A-Z0-9\-]+)",
        r"(?:款號|Style)[:\s]*([A-Z0-9\-]{4,})",
    ],
    # Season / 季節
    "season": [
        r"(?:Season|季節)[:\s]*((?:SS|FW|AW|Spring|Summer|Fall|Winter|Autumn)[\s\-]?\d{2,4})",
        r"\b(SS|FW|AW)\s*\d{2,4}\b",
    ],
    # Brand / 品牌
    "brand": [
        r"(?:Brand|品牌|廠牌)[:\s]*([A-Za-z0-9\s]+?)(?:\n|$|,)",
    ],
    # Gender / 性別
    "gender": [
        r"(?:Gender|性別)[:\s]*(Men|Women|Unisex|男|女|中性)",
    ],
    # Category / 類別
    "category": [
        r"(?:Category|類別|品類)[:\s]*([A-Za-z\s]+?)(?:\n|$|,)",
    ],
    # Order No / 訂單編號
    "order_no": [
        r"(?:Order\s*(?:No\.?|Number)|訂單編號|PO\s*(?:No\.?|Number)?)[:\s]*([A-Z0-9\-]+)",
    ],
    # Date / 日期
    "date": [
        r"(?:Date|日期)[:\s]*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    ],
    # Version / 版本
    "version": [
        r"(?:Version|Ver\.|版本|Rev\.?)[:\s]*([\d\.]+|[A-Z])",
    ],
}

# Section 偵測模式 (更寬鬆，適用於 HTML 表格標題)
SECTION_PATTERNS = {
    "BOM": [
        r"BOM\s*Details",
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:BOM|Bill\s+of\s+Materials?|材料清單|物料清單)",
        r"Product.*Material\s*Name.*Supplier",  # BOM 表格欄位特徵
    ],
    "Measurement": [
        r"Measurement\s*Chart",
        r"POM\s*Name.*Description.*Tol",  # Measurement 表格欄位特徵
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Measurement|尺寸|Size\s+Spec|規格表)",
    ],
    "Components": [
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Components?|組件|部件)",
    ],
    "Item": [
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Item\s+(?:Info|Description)|品項)",
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:General\s+Info|基本資訊)",
    ],
    "Evaluation": [
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Evaluation|評估|Testing|測試|Quality)",
    ],
    "Construction": [
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Construction|工藝|製程|Sewing|車縫)",
    ],
    "Colorway": [
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Colorway|配色|Color\s+Combo|顏色)",
    ],
    "Documents": [
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Documents?|Document\s+List|File\s+List|Attachments?|文件清單|附件|參考文件)",
    ],
    "Inspiration": [
        r"(?:^|\n|>)\s*(?:#+\s*)?(?:Inspiration|Inspo|Mood\s*Board|Reference\s*Image|參考圖|靈感)",
    ],
}
