
# 系統開發文件

本文件描述本專案的 **三層式架構**、**Tailscale 網路拓樸**、以及系統層面的設計與維運考量。  
API 詳細清單請參考：`apiReadme.md`（作為附件延伸說明）。

---

## 0. 目錄

- [1. 系統目標與範圍](#section-1)
- [2. 三層式架構](#section-2)
- [3. Tailscale 網路拓樸與安全考量](#section-3)
- [4. 系統資料流（單一檔案流程）](#section-4)
- [5. 主要資料存放](#section-5)
- [6. 可用性與錯誤處理](#section-6)
- [7. 部署與啟動](#section-7)
- [8. 文件結構與建議補充附件](#section-8)
- [9. 附件](#section-9)
- [10. 環境變數設定](#section-10)

---

<a id="section-1"></a>
## 1. 系統目標與範圍

**目標**
- 提供一條完整的流程：**上傳 PDF → OCR → 結果預覽 → 選圖 → Gemini VLM 對話 → 最終審核**
- 前端只需連**本機端 API**，**本機端**負責與**Lab電腦服務**溝通
- OCR 結果與 VLM 資料集中在 Lab 端，避免分散或洩漏

**核心功能**
- **雙模式介面 (Dual Mode UI)**:
  - **User Mode**: 簡化流程 (上傳 -> 處理進度 -> 最終審閱)，適合一般操作。
  - **Developer Mode**: 完整除錯視圖 (OCR結果、VLM對話、結構化資料預覽)，適合開發與驗證。
- **雙語結構化萃取 (Bilingual AI Extraction)**:
  - 自動提取 BOM、尺寸表 (Measurement)、Basic Info。
  - **中英對照**: 保留原始英文術語，並提供繁體中文翻譯 (如 "Neck Width" -> "領寬")。
  - 支援字典與 LLM 混合翻譯機制，確保專業術語準確性。

**不在本機端處理**
- OCR 執行（只在 Lab）
- DB/Redis OCR結果的實際寫入邏輯（由 Lab Service 負責）
- 檔案長期儲存（檔案留在 Lab）

---

<a id="section-2"></a>
## 2. 三層式架構

### 2.1 Frontend（Next.js）
- 使用者操作入口
- 只呼叫 `/api/ocr/*`（Next.js API）
- 不直接連 Local/Lab 或 DB

### 2.2 Local Backend（本機）
- 作為 **安全中介層**
- 負責建立 `local_job_id` 與 document id / document version
- 將請求轉送至 Lab Service
- Local Redis 保存狀態與版本快取
- 直接讀 PostgreSQL 作為 token 統計來源（避免前端直連 DB）

### 2.3 Lab Service（實驗室）
- OCR 任務建立與背景執行
- OCR 產物結果入庫（PostgreSQL）
- OCR job 狀態寫入 Lab Redis
- 提供 OCR 結果檔案與 VLM 對話 API
- 呼叫 Gemini API

### 系統架構圖
![系統架構圖](./doc/System_Architecture_Diagram.png)

---

<a id="section-3"></a>
## 3. Tailscale 網路拓樸與安全考量

**為什麼要使用 Tailscale**
- 讓本機與 Lab 透過私網 IP 互通
- 不需暴露 Lab Service 到公網
- 可利用 ACL 控制哪些裝置可存取

**安全考量**
- 前端不接觸 DB/Redis
- 本機端只存 metadata / job state，避免檔案外洩
- 後續可以在 Local 端加白名單/權限驗證，降低風險

---

<a id="section-4"></a>
## 4. 系統資料流（單一檔案流程）

1. 使用者上傳 PDF（Frontend → Next API → Local）
2. Local 建立 `document_id` / `version_no` → 寫 Local Redis +  DB（document_versions）
3. Local 轉送 PDF 到 Lab（multipart）
4. Lab 建立 OCRRun + 寫 Redis job state → 背景執行 OCR
5. 前端輪詢 Local（Local 再送request 到 Lab，同步當前 Lab Redis 狀態）
6. OCR 完成後，前端透過 Local 代理取得存在Lab電腦裡的頁面、檔案與圖片
7. 使用者選想要送入偵測的圖片 → Local 代理呼叫 Lab VLM（Gemini）
8. Token 統計由 Local 直接查 DB

---

<a id="section-5"></a>
## 5. 主要資料存放

Redis 與 Postgres 皆架設在 Lab 端的機器上
**Local Redis**
- `local:ocr:job:{local_job_id}`
- `local:ocr:doc:{document_id}:latest_version`

**Lab Redis**
- `ocr:job:{lab_job_id}`

**Lab PostgreSQL**
- `documents` / `document_versions`
- `ocr_runs` / `pages` / `page_ocr_artifacts` / `images`
- `vlm_sessions` / `vlm_messages`

---

<a id="section-6"></a>
## 6. 可用性與錯誤處理

**常見錯誤來源**
- Lab API timeout / 5xx → Local 回 502/504
- Gemini 503/429 → Lab 端做重試後仍失敗才回 502
- Lab Redis / DB 連線異常

**建議監控**
- Local / Lab 服務 log
- Redis 連線狀況
- PostgreSQL 連線與慢查
- Gemini API 失敗率

---

<a id="section-7"></a>
## 7. 部署與啟動

**Local Backend**
- 啟動於本機（面向前端）
- 需能連到 Lab 的 Tailscale IP

**Lab Service**
- 啟動於實驗室電腦（OCR 與 VLM 執行節點）
- OCR 結果與原檔案只存 Lab

**Frontend**
- 只打 Next.js `/api/ocr/*` Proxy
- Local API Base 預設 `http://127.0.0.1:8001`

---

<a id="section-8"></a>
## 8. 文件結構與補充附件

目前已有：
- `systemReadme.md`（本文件，系統架構）
- `apiReadme.md`（API 詳細清單）
- `databaseSchema.md`（資料表結構及欄位關聯說明）
- `redisKeys.md`（Redis 的 key 命名、TTL、狀態欄位定義）

---



<a id="section-9"></a>
## 9. 附件

### 9.1 [API 說明文件 (apiReadme.md)](./doc/apiReadme.md)

### 9.2 [Database Schema (databaseSchema.md)](./doc/databaseSchema.md)

### 9.3 [Redis Keys (redisKeys.md)](./doc/redisKeys.md)

---

<a id="section-10"></a>
## 10. 環境變數設定

本專案使用 `.env` 檔案管理敏感設定。請依照以下步驟設定：

### 10.1 Backend (本機端)

```bash
cd backend
cp .env.example .env
# 編輯 .env 填入實際的設定值
```

必要的環境變數：

| 變數名稱 | 說明 | 範例 |
|---------|------|------|
| DATABASE_URL | PostgreSQL 連線字串 | postgresql://user:password@localhost:5432/mtm_poc |
| REDIS_URL | Redis 連線字串 | redis://:password@localhost:6379/0 |
| LAB_API_BASE_URL | Lab Service 的 API 位址 | http://100.122.33.28:9000 |
| PADDLE_OCR_VLLM_URL | PaddleOCR vLLM 服務位址 | http://100.122.33.28:8000/v1 |
| LAB_DATA_ROOT | 實驗室檔案系統掛載路徑 | /lab_data/documents |
| LOCAL_UPLOAD_ROOT | 本機上傳檔案暫存路徑 | ./uploads |

### 10.2 Lab Service (實驗室端)

```bash
cd lab_service
cp .env.example .env
# 編輯 .env 填入實際的設定值
```

必要的環境變數：

| 變數名稱 | 說明 | 範例 |
|---------|------|------|
| DATABASE_URL | PostgreSQL 連線字串 (psycopg2 格式) | postgresql+psycopg2://user:password@127.0.0.1:5432/mtm_poc |
| REDIS_URL | Redis 連線字串 | redis://:password@127.0.0.1:6379/0 |
| PADDLE_VLLM_URL | PaddleOCR vLLM 服務位址 | http://127.0.0.1:8080/v1 |
| OCR_DATA_ROOT | OCR 結果輸出路徑 | /home/lab321/ocr_result |
| GEMINI_API_KEY | Gemini API 金鑰 | (從 Google AI Studio 取得) |
| GEMINI_MODEL | Gemini 模型名稱 | gemini-2.5-flash |

### 10.3 注意事項

- `.env` 檔案已被加入 `.gitignore`，不會被提交到版本控制
- 請勿將包含真實密碼的 `.env` 檔案提交到 GitHub
- 部署時請確保各服務的 `.env` 檔案已正確設定

