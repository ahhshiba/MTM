# Database Schema (Detailed)

本文件為資料庫完整結構說明（欄位/型別/預設值/索引/關聯）。  

---

## 1. Enum 型別

### 1.1 `document_status`
- `uploaded`
- `ocr_processing`
- `ocr_done`
- `vlm_review`
- `structuring`
- `done`
- `canceled`
- `error`

### 1.2 `run_status`
- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`

### 1.3 `chat_role`
- `system`
- `user`
- `assistant`

---

## 2. 資料表與欄位

### 2.1 `documents`
用途：文件主檔，代表一份 PDF 的最新狀態與主資料。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | character varying | NO | |
| title | text | YES | |
| file_path | text | NO | |
| page_count | integer | NO | |
| status | document_status | NO | 'uploaded' |
| error_reason | text | YES | |
| owner_user_id | character varying | YES | |
| created_at | timestamptz | NO | now() |
| updated_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `documents_pkey` (id)

Indexes:
- `documents_pkey` on (id) [unique]
- `idx_documents_status` on (status)
- `idx_documents_owner_created` on (owner_user_id, created_at DESC)

Notes:
- `error_reason` / `owner_user_id` 目前未使用，後續啟用。

---

### 2.2 `document_versions`
用途：同一份 document 的版本管理（版本號遞增）。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | bigint | NO | nextval('document_versions_id_seq') |
| document_id | character varying | NO | |
| version_no | integer | NO | |
| label | text | YES | |
| created_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `document_versions_pkey` (id)
- FK: `document_versions_document_id_fkey` → documents(id)
- UNIQUE: `document_versions_document_id_version_no_key` (document_id, version_no)

Indexes:
- `document_versions_pkey` on (id) [unique]
- `document_versions_document_id_version_no_key` on (document_id, version_no) [unique]
- `idx_doc_versions_document` on (document_id, version_no DESC)

---

### 2.3 `ocr_runs`
用途：一次 OCR 執行的紀錄（與 job_id、輸出路徑、錯誤訊息關聯）。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | bigint | NO | nextval('ocr_runs_id_seq') |
| document_id | character varying | NO | |
| document_version_id | bigint | NO | |
| status | run_status | NO | 'queued' |
| engine | text | NO | 'paddleocr-vl' |
| options_json | jsonb | YES | |
| output_dir_path | text | NO | |
| started_at | timestamptz | YES | |
| finished_at | timestamptz | YES | |
| created_at | timestamptz | NO | now() |
| job_id | character varying | YES | |
| error_code | character varying | YES | |
| error_message | text | YES | |
| updated_at | timestamptz | YES | |

Constraints / FK:
- PK: `ocr_runs_pkey` (id)
- FK: `ocr_runs_document_id_fkey` → documents(id)
- FK: `ocr_runs_document_version_id_fkey` → document_versions(id)

Indexes:
- `ocr_runs_pkey` on (id) [unique]
- `idx_ocr_runs_doc_ver` on (document_id, document_version_id)
- `idx_ocr_runs_job_id` on (job_id)
- `idx_ocr_runs_status` on (status)


---

### 2.4 `pages`
用途：每頁 PDF 的資訊與渲染圖路徑。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | bigint | NO | nextval('pages_id_seq') |
| document_id | character varying | NO | |
| page_no | integer | NO | |
| render_image_path | text | YES | |
| is_reviewed | boolean | NO | false |
| reviewed_at | timestamptz | YES | |
| created_at | timestamptz | NO | now() |
| updated_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `pages_pkey` (id)
- FK: `pages_document_id_fkey` → documents(id)
- UNIQUE: `pages_document_id_page_no_key` (document_id, page_no)

Indexes:
- `pages_pkey` on (id) [unique]
- `pages_document_id_page_no_key` on (document_id, page_no) [unique]
- `idx_pages_document` on (document_id, page_no)
- `idx_pages_reviewed` on (document_id, is_reviewed)

---

### 2.5 `page_ocr_artifacts`
用途：每頁 OCR 產物路徑（json / md / vis）。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | bigint | NO | nextval('page_ocr_artifacts_id_seq') |
| ocr_run_id | bigint | NO | |
| page_id | bigint | NO | |
| result_json_path | text | YES | |
| result_md_path | text | YES | |
| vis_image_path | text | YES | |
| created_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `page_ocr_artifacts_pkey` (id)
- FK: `page_ocr_artifacts_ocr_run_id_fkey` → ocr_runs(id)
- FK: `page_ocr_artifacts_page_id_fkey` → pages(id)
- UNIQUE: `page_ocr_artifacts_ocr_run_id_page_id_key` (ocr_run_id, page_id)

Indexes:
- `page_ocr_artifacts_pkey` on (id) [unique]
- `page_ocr_artifacts_ocr_run_id_page_id_key` on (ocr_run_id, page_id) [unique]
- `idx_page_artifacts_run` on (ocr_run_id)

---

### 2.6 `images`
用途：OCR 解析出的圖像區塊裁圖。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | character varying | NO | nextval('images_id_seq') |
| ocr_run_id | bigint | NO | |
| page_id | bigint | NO | |
| bbox_json | jsonb | NO | |
| image_path | text | NO | |
| sort_order | integer | NO | 0 |
| created_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `images_pkey` (id)
- FK: `images_ocr_run_id_fkey` → ocr_runs(id)
- FK: `images_page_id_fkey` → pages(id)

Indexes:
- `images_pkey` on (id) [unique]
- `idx_images_ocr_run` on (ocr_run_id)
- `idx_images_page` on (page_id, sort_order)

---

### 2.7 `vlm_sessions`
用途：每一張圖片對應一個 VLM 對話 session。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | character varying | NO | |
| image_id | character varying | NO | |
| model | text | NO | 'gemini' |
| system_prompt | text | YES | |
| finalized | boolean | NO | false |
| finalized_at | timestamptz | YES | |
| created_at | timestamptz | NO | now() |
| updated_at | timestamptz | NO | now() |
| aux_image_path | text | YES | |

Constraints / FK:
- PK: `vlm_sessions_pkey` (id)
- FK: `vlm_sessions_image_id_fkey` → images(id)

Indexes:
- `vlm_sessions_pkey` on (id) [unique]
- `idx_vlm_sessions_image` on (image_id, created_at DESC)
- `idx_vlm_sessions_finalized` on (finalized)

---

### 2.8 `vlm_messages`
用途：VLM 多輪對話訊息。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | bigint | NO | nextval('vlm_messages_id_seq') |
| session_id | character varying | NO | |
| role | chat_role | NO | |
| content | text | NO | |
| created_at | timestamptz | NO | now() |
| response_json | jsonb | YES | |
| prompt_tokens | integer | YES | |
| candidate_tokens | integer | YES | |
| total_tokens | integer | YES | |

Constraints / FK:
- PK: `vlm_messages_pkey` (id)
- FK: `vlm_messages_session_id_fkey` → vlm_sessions(id)

Indexes:
- `vlm_messages_pkey` on (id) [unique]
- `idx_vlm_messages_session` on (session_id, created_at)

---

## 3. 後續功能表（目前不啟用）

### 3.1 `exports`
用途：輸出MTM最終格式相關產物。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | character varying | NO | |
| document_id | character varying | NO | |
| document_version_id | bigint | NO | |
| format | text | NO | |
| file_path | text | NO | |
| created_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `exports_pkey` (id)
- FK: `exports_document_id_fkey` → documents(id)
- FK: `exports_document_version_id_fkey` → document_versions(id)

Indexes:
- `exports_pkey` on (id) [unique]
- `idx_exports_document` on (document_id, document_version_id, created_at DESC)

---

### 2.9 `extraction_runs`
用途：結構化萃取執行記錄 (BOM / Measurement / Basic Info)。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | integer | NO | nextval('extraction_runs_id_seq') |
| ocr_run_id | integer | NO | |
| document_id | character varying | NO | |
| status | text | NO | 'pending' |
| model | text | YES | 'gemini-2.5-flash' |
| mode | text | YES | 'auto' |
| total_tokens | integer | YES | 0 |
| raw_result_path | text | YES | |
| bbox_result_path | text | YES | |
| error_message | text | YES | |
| created_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `extraction_runs_pkey` (id)
- FK: `extraction_runs_ocr_run_id_fkey` → ocr_runs(id)

Indexes:
- `extraction_runs_pkey` on (id) [unique]
- `idx_extraction_runs_ocr_run` on (ocr_run_id)

---

### 2.10 `extraction_llm_calls`
用途：萃取過程中的 LLM 呼叫記錄。

| 欄位 | 型別 | 可為空 | 預設值 |
| --- | --- | --- | --- |
| id | integer | NO | nextval('extraction_llm_calls_id_seq') |
| extraction_run_id | integer | NO | |
| call_type | text | NO | |
| prompt | text | YES | |
| response | text | YES | |
| total_tokens | integer | YES | |
| duration_ms | integer | YES | |
| created_at | timestamptz | NO | now() |

Constraints / FK:
- PK: `extraction_llm_calls_pkey` (id)
- FK: `extraction_llm_calls_extraction_run_id_fkey` → extraction_runs(id)

Indexes:
- `extraction_llm_calls_pkey` on (id) [unique]
- `idx_extraction_llm_calls_run` on (extraction_run_id)

---

## 4. 關聯與使用重點

- **documents** 是所有流程核心，`document_versions` 與 `ocr_runs` 皆由此延伸。
- **ocr_runs** 與 **page_ocr_artifacts/images** 對應 OCR 產物。
- **vlm_sessions/messages** 以 images 為入口，對應多輪對話。
- `exports` 與 `structure_runs` 目前不啟用，但已有完整 FK 與索引。
