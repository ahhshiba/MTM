# app/services/extraction/prompts.py
"""
Extraction Prompts
自 techpack_extractor.py 提取的 Prompts
"""

# ==============================================================================
# LLM Prompts (通用化設計 - 適用各類服裝)
# ==============================================================================

SECTION_EXTRACTION_PROMPTS = {
    "BOM": """你是服裝 Tech Pack 分析專家。請分析以下材料清單 (BOM/Bill of Materials) 內容。

原始文字:
{text}

請提取所有材料項目，不論是布料、輔料、標籤、包裝等。每個項目請提取:
- product_code: 產品編碼/材料編碼
- material_name: 材料名稱 (original: 原始語言, zh: 中文)
- usage: 用途/部位 (如 Body, Neck, Sleeve, Lining 等)
- composition: 成分組成 (如 100% Cotton, 95% Polyester 5% Spandex)
- supplier: 供應商名稱
- color_info: 顏色資訊
- quantity: 數量/用量
- specifications: 其他規格 (如幅寬、克重、針數等)
- remarks: 備註

重要:
1. 保留原始語言文字 (用於前端跳轉)
2. 提供繁體中文翻譯/標準化
3. 此格式適用於各類服裝 (上衣、褲子、外套、配件等)
4. 如果某欄位不存在，設為 null
5. 'zh' 欄位必須翻譯成繁體中文 (例如: Neck -> 領口, Body -> 大身)。不可保留英文，除非是無對應中文的專有代碼。""",

    "Measurement": """你是服裝 Tech Pack 分析專家。請分析以下尺寸規格表 (Measurement Chart/Spec Sheet)。

原始文字:
{text}

請提取完整的尺寸規格資訊:
1. 基本資訊:
   - size_range: 涵蓋的尺碼 (如 XS, S, M, L, XL 或 28, 30, 32...)
   - base_size: 樣品尺碼/基本尺碼
   - unit: 單位 (cm, inches, fractions of inches)
   - grade_rule: 跳檔規則 (如有)

2. 測量點列表 (每個測量點):
   - pom_code: POM 編碼 (如 B25.13, F10.11)
   - point_name: 測量點名稱 (original + zh)
   - description: 測量方式說明
   - tolerance_minus: 負公差
   - tolerance_plus: 正公差
   - values: 各尺碼數值 {size: value}
   - is_qc: 是否為 QC 檢測項目

重要:
1. 此格式適用於各類服裝 (上衣、褲子、外套、裙子等)
2. 注意不同服裝的測量點不同 (如褲子有 Inseam, 上衣有 Chest)
3. 保留原始語言和繁體中文翻譯
4. 'point_name' 的 zh 欄位必須強制翻譯成繁體中文。請參考以下術語表:
   - Neck Width -> 領寬
   - Front Neck Drop -> 前領深
   - Back Neck Drop -> 後領深
   - Chest -> 胸圍
   - Across Shoulder -> 肩寬
   - Sleeve Length -> 袖長
   - Armhole -> 袖攏
   - Bottom Opening -> 下擺
   - Cuff Opening -> 袖口
   - Trim Height -> 邊飾高度
   - Sweep -> 下擺
   (其他部位請根據專業知識翻譯)""",

    "Components": """你是服裝 Tech Pack 分析專家。請分析以下組件資訊 (Components)。

原始文字:
{text}

請提取所有組件/BOM 版本資訊:
- component_name: 組件名稱 (original + zh)
- component_type: 類型 (Design BOM, Production BOM 等)
- status: 狀態
- color_info: 配色資訊 (CC Name, CC Number)
- dates: 建立/修改日期

重要: 此格式適用於各類服裝類型""",

    "Construction": """你是服裝 Tech Pack 分析專家。請分析以下工藝/製程資訊 (Construction/Sewing Details)。

原始文字:
{text}

請提取工藝細節:
- area: 區域/部位 (original + zh): 如領口、袖口、下擺、褲腳、口袋等
- process: 工藝類型 (original + zh): 如雙針壓線、包邊、暗縫等
- stitch_type: 車縫類型
- seam_allowance: 縫份
- special_instructions: 特殊說明

重要:
1. 此格式適用於各類服裝 (不同服裝有不同工藝重點)
2. 保留原始語言用於比對""",

    "Colorway": """你是服裝 Tech Pack 分析專家。請分析以下配色資訊 (Colorway/Color Details)。

原始文字:
{text}

請提取配色資訊:
- color_name: 顏色名稱 (original + zh)
- color_code: 色號/編碼
- pantone: Pantone 色號 (如有)
- application_parts: 應用部位
- status: 狀態

重要: 此格式適用於各類服裝配色方案""",

    "Item": """你是服裝 Tech Pack 分析專家。請分析以下品項基本資訊。

原始文字:
{text}

請提取品項描述:
- garment_type: 服裝類型 (original + zh): 如 T-Shirt, Pants, Jacket, Shorts 等
- fit_description: 版型描述 (如 Regular, Slim, Relaxed)
- design_features: 設計特徵列表
- construction_highlights: 製作重點

重要: 識別這是什麼類型的服裝並提取相關特徵""",

    "Evaluation": """你是服裝 Tech Pack 分析專家。請分析以下評估/測試資訊。

原始文字:
{text}

請提取評估項目:
- test_name: 測試項目名稱 (original + zh)
- standard: 標準/規範
- result: 結果
- status: 通過/待處理

重要: 提取所有品質測試或合規性檢查資訊""",
}

IMAGE_CLASSIFICATION_PROMPT = """你是服裝 Tech Pack 圖片分析專家。請分析這張圖片並分類。

可能的圖片類型:
1. 成衣實體圖 - 實際成品照片、模特兒著裝照
2. 平面線段設計圖 - 技術設計圖、工藝線段圖、版型圖
3. 色塊表 - 配色卡、顏色樣本、布料樣本
4. 尺寸圖 - 尺寸標註圖、測量示意圖
5. 細節圖 - 局部細節照片 (如鈕扣、拉鏈、口袋、車縫細節)
6. Logo/標籤 - 品牌標籤、吊牌、洗標
7. Email截圖 - 電子郵件往來截圖、訊息截圖
8. 其他 - 無法分類的圖片

請回傳:
- image_type: 圖片類型 (使用上述中文名稱)
- description_original: 原始語言描述 (描述圖片中可見的元素)
- description_zh: 繁體中文描述 (包含視覺特徵)
- feature_tags: 特徵標籤列表 (繁體中文，如: 連帽, 拉鏈門襟, 插肩袖, V領, 口袋等)
- related_section: 相關區塊 (BOM/Measurement/Construction/Colorway/Artwork)
- image_role: 圖片用途 (actual_spec/reference/inspiration/unknown)
- colorway_spec: 若為色塊表或成衣圖，提取配色方案詳情 (Combo, Color Name, Pantone, Location)。若無則為 null。
- artwork_details: 若為圖案/Logo圖，提取圖案細節 (Placement, Dimensions, Technique)。若無則為 null。

重要: 
- Email截圖特徵：包含 "From:", "To:", "Subject:", "Sent:" 或 Outlook/Gmail 介面元素。
- image_role: 若是該款必做規格圖/圖示，填 actual_spec；若是參考或他款示意，填 reference；若為靈感/情緒圖，填 inspiration。
- 對於色塊表，請盡可能結構化提取顏色代碼和對應部位。
- 對於 Logo/Artwork，請提取位置描述和尺寸資訊。"""

EMAIL_EXTRACTION_PROMPT = """你是服裝採購/開發 Email 分析專家。請分析這張 Email 截圖。

請提取:
- date: 日期 (若可見)
- sender: 寄件者
- recipient: 收件者
- subject: 主旨 (original + zh)
- content_summary: 內容摘要 (original + zh)
- action_items: 待辦事項/確認事項列表
- key_decisions: 重要決策 (如價格確認、交期確認、規格變更等)

重要:
1. 這些 Email 通常與訂單確認、樣品評論、規格修改相關
2. 提取任何可能影響報價或生產的資訊"""

CONSTRUCTION_EXTRACTION_PROMPT = """You are a Tech Pack construction expert. Extract construction options and construction notes from the text.

Return JSON:
{
  "options": [
    {
      "option_id": "OPT1 / OPT2 / Option A",
      "title": {"original": "...", "zh": "..."},
      "summary": {"original": "...", "zh": "..."},
      "attributes": [
        {
          "name": {"original": "...", "zh": "..."},
          "value": {"original": "...", "zh": "..."},
          "notes": {"original": "...", "zh": "..."}
        }
      ]
    }
  ],
  "notes": [
    {
      "date": "YYYY/MM/DD or similar",
      "source": {"original": "TD/RECAP/Meeting/etc", "zh": "..."},
      "content": {"original": "...", "zh": "..."}
    }
  ]
}

Rules:
1. Keep ALL options (OPT1/OPT2/etc). Do not merge or drop.
2. Use attributes for specific workmanship details (stitch type, seam type, placements, hem/topstitch, materials).
3. Notes should capture TD explanations, recap summaries, or meeting decisions.
4. Use null if a field is not present. Avoid guessing.
"""

FINAL_REVIEW_PROMPT = """你是服裝 Tech Pack 資料審核專家。請檢查以下已提取的結構化資料是否有遺漏。

原始文字內容:
{original_text}

已提取的資料:
{extracted_data}

請檢查:
1. 是否有重要欄位被遺漏？
2. 是否有表格資料未被正確解析？
3. 是否有數值或規格資訊遺漏？
4. 硬比對與 LLM 提取是否有矛盾？

請回傳:
- missing_fields: 建議補充的欄位名稱列表
- suggested_additions: 建議新增的資料 (key-value 格式)
- consistency_warnings: 一致性警告 (如發現矛盾)
- confidence_note: 信心說明

重要: 只提出「建議補充」，不要覆蓋已正確提取的資料"""

BASIC_INFO_TRANSLATION_PROMPT = """你是服裝 Tech Pack 翻譯專家。請將以下 Basic Info JSON 中的 'zh' 欄位翻譯成繁體中文 (Traditional Chinese)。

輸入 JSON:
{json_data}

規則:
1. 僅修改 'zh' 欄位，保留 'original' 欄位不變。
2. 針對以下特定術語進行專業翻譯:
   - "In-Work" -> "製作中"
   - "Adopted" -> "已採用"
   - "Dropped" -> "已取消"
   - "Self" -> "表布"
   - "Contrast" -> "配布"
   - "Lining" -> "裡布"
   - "Interlining" -> "襯布"
3. 對於人名或專有名詞 (如供應商名稱)，若無通用中文名，可保留原文或音譯。
4. "Supplier": 若為知名廠商請翻譯，否則保留。
5. "Size Range": 將 "ALPHA" 翻為 "字母尺碼", "NUMERIC" 翻為 "數字尺碼"。
6. "Season": 如 "Summer 2026" -> "2026 夏季"。
7. "Garment Type": 如 "Sweatshirt" -> "大學T/衛衣", "Top" -> "上衣"。

請直接回傳完整的 JSON 結果。"""
