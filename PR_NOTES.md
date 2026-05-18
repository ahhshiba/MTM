## 雙語結構化萃取與前端模組化更新 (Bilingual Extraction & Frontend Modularization)

## 功能說明

本次更新主要包含三大核心：
1. **雙語結構化萃取 (Bilingual Extraction)**: 自動提取 BOM、尺寸表 (Measurement) 與基本資訊，並由後端確保 "Neck Width -> 領寬" 等專業術語的中英對照翻譯。
2. **前端模組化與全英文介面**: 將原本龐大的 `PreviewStep` 重構為多個獨立 Panel (BasicInfo / BOM / Measurement...)，提升維護性；並將 開發者模式 (Developer Mode) 全面中文化轉為標準英文介面。
3. **進度條與錯誤處理**: Lab Service 現在透過 Redis 即時回報萃取進度，前端可顯示精確的進度條與錯誤訊息。

---

## 主要變更

### Lab Service

- **[engine.py](lab_service/app/services/extraction/engine.py)**
  - 實作全並行萃取邏輯 (Measure/BOM/Images 同時執行)。
  - 新增 `MEASUREMENT_MAPPING` 字典作為翻譯後備機制 (Backup Fallback)。
- **[prompts.py](lab_service/app/services/extraction/prompts.py)**
  - 優化 System Prompts，加入詳細的術語對照表 (Glossary)，強制 LLM 生成雙語欄位。
- **[api/extraction.py](lab_service/app/api/extraction.py)** (與 models.py)
  - 新增 `/extraction/*` 系列 API。
  - 支援進度追蹤 (Redis key: `extraction:{id}`)。
  - 新增 `extraction_runs` 與 `extraction_llm_calls` 資料表。

### Backend (Local Proxy)

- **[local_ocr.py](backend/app/api/routers/local_ocr.py)**
  - 新增 Proxy Endpoints:
    - `POST /local/ocr/extraction/start`
    - `GET /local/ocr/extraction/{id}`
    - `GET /local/ocr/extraction/{id}/result`
    - `GET /local/ocr/extraction/by-ocr/{ocr_run_id}`

### Frontend

- **[PreviewStep.jsx](frontend/app/components/steps/PreviewStep.jsx)**
  - **模組化重構**: 拆分為 `BasicInfoPanel`, `BomPanel`, `MeasurementPanel` 等子組件。
  - **BilingualText**: 新增共用雙語顯示元件 (上方英文 bold / 下方中文 muted)。
  - **English UI**: 所有 Label, Header, Button 全面改為英文 (Developer Mode)。
- **[StepNav.jsx](frontend/app/components/StepNav.jsx)**
  - 開發者模式步驟名稱中文化 -> 英文化 ("Extraction", "Data Preview")。
- **[useExtraction.js](frontend/app/hooks/useExtraction.js)**
  - 新增 Hook 封裝萃取啟動、輪詢進度、錯誤處理邏輯。

---

## 雙語萃取與介面流程

1. **Extraction (Step 3)**:
   - 點擊 "Start Extraction" -> 觸發後端並行任務。
   - 顯示 Redis 即時進度條。
2. **Data Preview (Step 4)**:
   - **Bilingual Display**: BOM 與 Measurement 表格顯示 "Original (English)" 為主，下方附帶 "Chinese (ZH)" 翻譯。
   - **English Interface**: 側邊欄與標題均為英文，符合開發者使用習慣。

---

## 測試

- [x] **Bilingual Extraction**: 確認 "Neck Width", "Chest" 等術語能正確顯示中文翻譯 (LLM 或 Dictionary fallback)。
- [x] **Frontend Refactor**: 確認拆分後的 Panel (BOM/Measurement) 功能與資料顯示正常。
- [x] **English UI**: 確認 Sidebar、Table Header、Empty State ("No Data") 均顯示英文。
- [x] **API Connectivity**: 確認 Frontend -> Local Proxy -> Lab Service 資料流暢通。
