# 一鍵安裝需求文件（Windows + Linux）

## 1) 目標
提供非工程師也能使用的「一鍵安裝 + 一鍵啟動」流程，並支援 GPU。
- 使用者只需點擊安裝檔（或執行腳本）即可完成安裝並啟動服務。
- 安裝器會自動下載所需依賴（不走離線包）。

## 2) 目標平台
- Windows（主要）
- Linux（次要）
- 兩者流程一致（包裝形式可不同）。

## 3) 一鍵安裝器職責
### 3.1 主機前置依賴（自動檢查 + 自動安裝）
- NVIDIA GPU 驅動
- Docker 執行環境
- NVIDIA Container Toolkit（Linux）/ WSL2 + NVIDIA 支援（Windows）

### 3.2 服務包配置
- 下載或解壓「服務包」（docker-compose + 設定檔）
- 固定安裝位置（每個 OS 預設）：
  - Windows: `C:\MTM`
  - Linux: `/opt/mtm`
- 建立必要資料夾：
  - OCR 輸出：`data/ocr`
  - Postgres 資料：`data/postgres`
  - Redis 資料：`data/redis`
  - Paddle 模型：`data/paddle_models`

### 3.3 環境變數（使用者可輸入，皆有預設值）
安裝時可選填，未填則使用預設值。
- `DATABASE_URL=postgresql+psycopg2://mtm:mtm@postgres:5432/mtm_poc`
- `REDIS_URL=redis://:mtm@redis:6379/0`
- `PADDLE_VLLM_URL=http://paddle_vllm:8080/v1`
- `OCR_DATA_ROOT=/data/ocr`
- `WORKER_MAX_CONCURRENCY=1`
- `JOB_STATE_TTL_SECONDS=604800`
- `OCR_SUBPROCESS_TIMEOUT_SECONDS=0`
- `GEMINI_API_KEY=`（可空）
- `GEMINI_MODEL=gemini-2.5-flash`
- `GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta`
- `GEMINI_TIMEOUT_SECONDS=30`

### 3.4 啟動
- 執行 `docker compose up -d` 啟動完整服務。
- 進行基本健康檢查並提示成功/失敗原因。

## 4) 執行堆疊（Docker Compose）
必要容器（單一指令啟動）：
1) `lab_service`
2) `postgres`
3) `redis`
4) `paddle_vllm`（GPU）

## 5) 網路/存取模式（VPN-only）
部署採 **VPN-only**，不對公網開放。
- 每個廠商各自在本機 GPU 主機安裝並運行。
- 內部使用者先連 VPN，再用 VPN IP/hostname 存取服務。
- 避免服務直接暴露公網，降低安全維護風險。

## 6) 資料擁有權與儲存
- 所有資料只存放在廠商本機。
- 不依賴外部 DB/Redis。
- Docker volumes 綁定到安裝路徑下的資料夾。

## 7) GPU/Driver 限制（不可迴避）
- NVIDIA 驅動必須安裝在主機。
- 容器使用 GPU 必須依賴主機驅動與 toolkit。
- Docker 無法在容器內替代安裝主機驅動。

## 8) 非目標範圍
- 不支援無 GPU 或 CPU-only 部署。
- 不支援不使用 Docker 的部署。
- 不支援集中式/共享 DB/Redis。

## 9) 錯誤處理要求
安裝器需清楚提示以下問題：
- 未偵測到 NVIDIA GPU
- 驅動安裝失敗
- Docker 安裝失敗或需重開機
- NVIDIA Container Toolkit / WSL2 不可用

## 10) 使用者體驗要求
- 流程最少提示、無需手動編輯檔案。
- 唯一可選輸入：Gemini API Key（可跳過）。
- 安裝完成後可用桌面捷徑或單一指令啟動。

## 11) 交付物（Phase 1）
- 需求文件（本文件）
- 高階架構圖（可沿用既有圖）
- 安裝流程草案（Windows / Linux）

## 12) 交付物（Phase 2）
- Windows 安裝器（EXE）
- Linux 安裝器（script 或 package）
- 服務包（docker-compose + lab_service image + 設定檔）

