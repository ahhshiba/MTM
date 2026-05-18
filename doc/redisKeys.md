# Redis Keys 說明（Local / Lab）

本文件整理 Local 與 Lab Redis 的 key 命名、TTL、狀態欄位定義。  
Redis 在此專案目前主要用於「狀態快取」，暫無設計排隊邏輯。

---

## 1. Local Redis（本機）

### 1.1 Job 狀態
**Key**
- `local:ocr:job:{local_job_id}`

**TTL**
- `LOCAL_JOB_TTL_SECONDS`（預設 24h，寫入時會刷新 TTL）

**用途**
- 本機 OCR job state（由 Local Backend 建立/更新）
- 前端查詢 status 時的來源

**欄位**
```json
{
  "local_job_id": "uuid",
  "lab_job_id": "uuid",
  "document_id": "sha256...",
  "document_version_id": 123,
  "document_version_no": 1,
  "ocr_run_id": 8,
  "status": "queued|running|done|failed|canceled|error",
  "step": "creating|queued|ocr|parse_and_mapping|finished|error",
  "progress": 0.0,
  "output_dir": "/lab/path/...",
  "cancel_requested": false,
  "error_code": null,
  "error_message": null,
  "created_at": 1700000000,
  "updated_at": 1700000000
}
```

### 1.2 文件版本快取
**Key**
- `local:ocr:doc:{document_id}:latest_version`

**TTL**
- `LOCAL_JOB_TTL_SECONDS`（與 job 相同）

**用途**
- 快速取得 document 最新版本號，避免每次查 DB

**內容**
```
"3"
```

---

## 2. Lab Redis（實驗室）

### 2.1 OCR Job 狀態
**Key**
- `ocr:job:{lab_job_id}`

**TTL**
- `JOB_STATE_TTL_SECONDS`（預設 7 天）

**用途**
- OCR 執行狀態、進度、錯誤資訊
- Local 端會呼叫 Lab `/jobs/ocr/{lab_job_id}` 讀取

**欄位（範例）**
```json
{
  "status": "queued|running|done|failed|canceled",
  "step": "queued|ocr|parse_and_mapping|finished|error",
  "document_id": "sha256...",
  "document_version_id": 123,
  "ocr_run_id": 8,
  "output_dir": "/lab/path/...",
  "progress": 0.52,
  "current_page": 3,
  "total_pages": 12,
  "cancel_requested": false,
  "error_code": null,
  "error_message": null,
  "updated_at": 1700000000
}
```

**更新時機**
- `POST /jobs/ocr` 建立時寫入 `queued`
- OCR 執行中更新 `progress` / `step`
- 完成時更新 `status=done`
- 取消或錯誤時更新 `status=failed/canceled`

---

## 3. 設計重點與注意事項

1. **Redis 不作為 Queue**
   - 目前沒有監聽 Redis 拉任務的 worker
   - 背景任務由 Lab API 直接啟動

2. **Local / Lab Redis key prefix 不同**
   - 避免同一 Redis 時互相覆蓋

3. **TTL 會刷新**
   - 每次寫入都會更新 TTL，避免狀態過期

