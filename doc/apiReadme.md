# API 說明文件（Frontend → Local Backend → Lab Service）

本文件描述目前專案中 **Next.js API → 本機 Local Backend → 實驗室 Lab Service** 的完整 API 代理鏈，以及每個 API 的用途、輸入/輸出、是否涉及 PostgreSQL 或 Redis。

---

## 1. 整體架構與代理關係

**三層角色**
- **Next.js API（Frontend）**：只做轉發（proxy），避免前端直接打本機或實驗室 API。
- **Local Backend（本機）**：建立 `local_job_id`、紀錄 Local Redis、管理 document/version、代理 Lab API。
- **Lab Service（實驗室）**：OCR 執行與結果入庫、OCR 結果檔案讀取、Gemini VLM 對話。

**代理流程概念**
```
Browser → Next.js API (/api/ocr/...) → Local Backend (/local/ocr/...)
                                        └→ Lab Service (/jobs/ocr, /results/ocr, /vlm)
```

**資料存放**
- **Local Redis（本機）**：Local job state + document 版本快取
- **Lab Redis（實驗室）**：OCR job state（進度、步驟）
- **Lab PostgreSQL（實驗室）**：documents / document_versions / ocr_runs / pages / artifacts / images / vlm_sessions / vlm_messages

---

## 2. Next.js API（Frontend Proxy）

> 這一層只做轉發，不存 DB/Redis。  
> API Base 由 `LOCAL_API_BASE` 決定，預設 `http://127.0.0.1:8001`。

### 2.1 OCR 任務
- `POST /api/ocr/jobs` → `POST /local/ocr/jobs`
  - **用途**：上傳 PDF，建立 OCR 任務
  - **儲存**：無（純代理）

- `GET /api/ocr/jobs/{localJobId}` → `GET /local/ocr/jobs/{local_job_id}`
  - **用途**：查詢 OCR 任務狀態（Local 會同步 Lab）
  - **儲存**：無

- `POST /api/ocr/jobs/{localJobId}/cancel` → `POST /local/ocr/jobs/{local_job_id}/cancel`
  - **用途**：取消 OCR
  - **儲存**：無

- `GET /api/ocr/jobs/{localJobId}/results` → `GET /local/ocr/jobs/{local_job_id}/results`
  - **用途**：取得 OCR 結果 JSON（頁面、圖片、artifact URL）
  - **儲存**：無

### 2.2 OCR 產物（檔案代理）
- `GET /api/ocr/results/images/{imageId}` → `/local/ocr/results/images/{image_id}`
- `GET /api/ocr/results/pages/{pageId}/render_image` → `/local/ocr/results/pages/{page_id}/render_image`
- `GET /api/ocr/results/artifacts/{artifactId}/result_json` → `/local/ocr/results/artifacts/{artifact_id}/result_json`
- `GET /api/ocr/results/artifacts/{artifactId}/result_md` → `/local/ocr/results/artifacts/{artifact_id}/result_md`
- `GET /api/ocr/results/artifacts/{artifactId}/vis_image` → `/local/ocr/results/artifacts/{artifact_id}/vis_image`

### 2.3 VLM
- `POST /api/ocr/vlm/sessions` → `/local/ocr/vlm/sessions`
- `GET /api/ocr/vlm/sessions/{sessionId}` → `/local/ocr/vlm/sessions/{session_id}`
- `POST /api/ocr/vlm/sessions/{sessionId}/messages` → `/local/ocr/vlm/sessions/{session_id}/messages`

### 2.4 Token 統計（Local DB 直查）
- `GET /api/ocr/vlm/sessions/{sessionId}/tokens` → `/local/ocr/vlm/sessions/{session_id}/tokens`
- `POST /api/ocr/vlm/tokens` → `/local/ocr/vlm/tokens`

---

## 3. Local Backend API（本機）

> 主要負責：  
> - 建立 `local_job_id`  
> - 版本控管（document_versions）  
> - Local Redis 狀態  
> - 代理 Lab API  
> - Token 直接讀 DB

### 3.1 `POST /local/ocr/jobs`
**用途**  
上傳 PDF，建立 local job，並轉送 Lab 建立 OCR job。

**輸入（multipart/form-data）**
- `file`：PDF 檔（必填，<=10MB）

**流程**
1. 驗證 PDF / 大小  
2. `document_id = sha256(file_bytes)`  
3. 查 Redis 快取版本，必要時查 DB（document_versions）
4. 寫入 DB（documents + document_versions）  
5. Local Redis 建立 `local:ocr:job:{local_job_id}`  
6. 呼叫 Lab：`POST /jobs/ocr`（multipart）  
7. 回寫 Local Redis（lab_job_id / ocr_run_id / status）

**涉及儲存**
- Local Redis （job state + latest version）
- PostgreSQL （documents / document_versions）
- Lab Redis （由 Lab API 寫入）
- DB （由 Lab API 寫入）

**輸出（範例）**
```json
{
  "local_job_id": "uuid",
  "lab_job_id": "uuid",
  "ocr_run_id": 8,
  "status": "queued",
  "output_dir": "/lab/path/xxx",
  "document_id": "sha256...",
  "document_version_id": 123,
  "document_version_no": 1,
  "created_at": 1700000000
}
```

### 3.2 `GET /local/ocr/jobs/{local_job_id}`
**用途**  
查詢 Local job 狀態，並同步 Lab Redis 狀態。

**流程**
1. 讀 Local Redis  
2. 若有 `lab_job_id` → 呼叫 Lab `/jobs/ocr/{lab_job_id}`  
3. 合併狀態更新回 Local Redis  

**涉及儲存**
- Local Redis   
- Lab Redis （讀取）

### 3.3 `POST /local/ocr/jobs/{local_job_id}/cancel`
**用途**  
取消 OCR。

**流程**
1. 從 Local Redis 取得 `lab_job_id`
2. 呼叫 Lab `/jobs/ocr/{lab_job_id}/cancel`
3. Local Redis 設定 `cancel_requested=true`

**涉及儲存**
- Local Redis   
- Lab Redis （寫入 cancel）

### 3.4 `GET /local/ocr/jobs/{local_job_id}/results`
**用途**  
取得 OCR 結果（pages / images / artifacts）。

**流程**
1. 讀 Local Redis 取得 `ocr_run_id`
2. 呼叫 Lab `/results/ocr/{ocr_run_id}`

**涉及儲存**
- Local Redis （讀取）
- DB （讀取 OCR 結果）

### 3.5 OCR 產物代理
**用途**  
Local 代理 Lab 檔案存取，避免前端直連 Lab。

- `GET /local/ocr/results/images/{image_id}`
- `GET /local/ocr/results/pages/{page_id}/render_image`
- `GET /local/ocr/results/artifacts/{artifact_id}/result_json`
- `GET /local/ocr/results/artifacts/{artifact_id}/result_md`
- `GET /local/ocr/results/artifacts/{artifact_id}/vis_image`

**涉及儲存**
- DB （查路徑）
- Lab 檔案系統 （讀檔）

### 3.6 VLM（Proxy）
- `POST /local/ocr/vlm/sessions`
  - 代理 Lab `/vlm/sessions`
  - **涉及儲存**：DB （vlm_sessions / vlm_messages）

- `GET /local/ocr/vlm/sessions/{session_id}`
  - 代理 Lab `/vlm/sessions/{session_id}`

- `POST /local/ocr/vlm/sessions/{session_id}/messages`
  - 代理 Lab `/vlm/sessions/{session_id}/messages`
  - **涉及儲存**：DB（vlm_messages）

### 3.7 Token 統計（Local 直查 DB ）
> 直接連 PostgreSQL，不經 Lab API。

- `GET /local/ocr/vlm/sessions/{session_id}/tokens`
  - 查詢 `vlm_messages`，回傳單一 session token 總和

- `POST /local/ocr/vlm/tokens`
  - Body: `{ "session_ids": ["id1", "id2"] }`
  - 回傳多個 session token + 總合

**涉及儲存**
- PostgreSQL（vlm_messages）

### 3.8 結構化萃取 (Extraction)
- `POST /local/ocr/extraction/start`
  - **用途**: 啟動結構化萃取任務 (BOM, Measurement, Basic Info)。
  - **Body**: `{ "ocr_job_id": "...", "images": [...] }`

- `GET /local/ocr/extraction/{extraction_id}`
  - **用途**: 查詢萃取進度。

- `GET /local/ocr/extraction/{extraction_id}/result`
  - **用途**: 取得最終結構化 JSON。
  - **輸出結構**: 支援雙語欄位。
    ```json
    {
      "basic_info": {
        "season": {
            "original": "Summer 2026",
            "zh": "2026 夏季"
        }
      },
      "sections": [
        {
          "section_type": "Measurement",
          "points": [
            {
              "point_name": {
                "original": "Neck Width",
                "zh": "領寬"
              }
            }
          ]
        }
      ]
    }
    ```

- `GET /local/ocr/extraction/by-ocr/{ocr_run_id}`
  - **用途**: 根據 OCR Run ID 取得最新萃取記錄（含狀態、Token數、結果路徑）。

---

## 4. Lab Service API（實驗室）

### 4.1 `POST /jobs/ocr`
**用途**  
建立 OCR 任務（建立 OCRRun + Redis job + 背景 OCR）。

**輸入（multipart/form-data）**
- `document_id` (string)
- `document_version_id` (int)
- `output_folder_name` (string)
- `file` (PDF)

**涉及儲存**
- DB （documents / document_versions / ocr_runs）
- Lab Redis（ocr:job:{job_id}）
- Lab 檔案系統（upload_file/{job_id}.pdf, OCR_DATA_ROOT）

### 4.2 `GET /jobs/ocr/{job_id}`
**用途**  
從 Lab Redis 讀取 OCR job state。

**涉及儲存**
- Lab Redis 

### 4.3 `POST /jobs/ocr/{job_id}/cancel`
**用途**  
標記取消（寫入 Redis，worker 會檢查）。

**涉及儲存**
- Lab Redis 

### 4.4 `GET /results/ocr/{ocr_run_id}`
**用途**  
從 DB 讀取 OCR 結果並整理成 pages/images/artifacts 結構。

**涉及儲存**
- DB （ocr_runs / pages / page_ocr_artifacts / images）

### 4.5 檔案存取
- `GET /results/ocr/artifacts/{artifact_id}/result_json`
- `GET /results/ocr/artifacts/{artifact_id}/result_md`
- `GET /results/ocr/artifacts/{artifact_id}/vis_image`
- `GET /results/ocr/images/{image_id}`
- `GET /results/ocr/pages/{page_id}/render_image`

**涉及儲存**
- DB （查檔案路徑）
- Lab 檔案系統 （實體檔案）

### 4.6 VLM
- `POST /vlm/sessions`
  - 建立 session，呼叫 Gemini 並寫入第一輪訊息
- `GET /vlm/sessions/{session_id}`
  - 讀取 session + messages
- `POST /vlm/sessions/{session_id}/messages`
  - 追加對話 + 呼叫 Gemini

**涉及儲存**
- DB （vlm_sessions / vlm_messages）
- 外部 API （Gemini）

### 4.7 結構化萃取 (Extraction)
- `POST /extraction/start`
  - **用途**: 背景執行結構化萃取。
  - **進度追蹤**: Redis `extraction:{id}` (status, progress 0-1)。

- `GET /extraction/{extraction_id}`
  - **用途**: 取得萃取狀態 (Status)、進度 (Progress)、Token 統計。

- `GET /extraction/{extraction_id}/result`
  - **用途**: 讀取最終結構化 JSON 檔案。

- `GET /extraction/by-ocr/{ocr_run_id}`
  - **用途**: 查詢該 OCR 任務最新的萃取記錄。

**涉及儲存**
- DB (`extraction_runs` / `extraction_llm_calls`)
- Lab Redis (`extraction:{id}`)
- Lab 檔案系統 (結果 JSON)

---

## 5. Redis / DB Key 與資料來源

**Local Redis**
- `local:ocr:job:{local_job_id}`：Local job state  
- `local:ocr:doc:{document_id}:latest_version`：最新版本快取

**Lab Redis**
- `ocr:job:{job_id}`：OCR job state

**PostgreSQL（主要表）**
- `documents`
- `document_versions`
- `ocr_runs`
- `pages`
- `page_ocr_artifacts`
- `images`
- `vlm_sessions`
- `vlm_messages`


