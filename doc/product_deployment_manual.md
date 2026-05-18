# MTM 系統產品部署手冊

## 文件資訊

| 項目 | 內容 |
|------|------|
| 文件版本 | 2.0 |
| 系統版本 | MTM POC v1.0 |
| 最後更新 | 2026-02-09 |

---

## 1. 文件目的與範圍

本文件提供 MTM 系統的**完整部署架構說明**與**生產環境最佳實踐**

**涵蓋範圍**：
- 系統架構與各組件詳細說明
- 部署模式與環境配置
- 資料流與通訊機制
- 安全加固與合規建議
- 故障排除與診斷流程

**相關文件**：
- [客戶安裝指南](./customer_install_quickstart.md) - 實際安裝步驟
- [API 參考文件](./apiReadme.md) - API 端點詳細說明
- [資料庫結構](./databaseSchema.md) - 資料表設計
- [Redis Keys 說明](./redisKeys.md) - 快取鍵值設計

---

## 2. 系統架構總覽

### 2.1 核心設計理念

MTM 系統採用**微服務架構**與**容器化部署**，遵循以下設計原則：

1. **關注點分離**：Frontend（展示）、Backend（中介代理）、Lab Service（運算處理）
2. **無狀態服務**：所有狀態儲存於 PostgreSQL 或 Redis，服務本身可水平擴展
3. **GPU 資源隔離**：AI 推理服務（Lab Service、Paddle vLLM）獨立運行，避免資源競爭
4. **資料持久化**：所有重要資料透過 Docker Volume 持久化儲存
5. **內部服務發現**：透過 Docker Compose 內建 DNS 進行服務間通訊

### 2.2 服務組成

系統由以下六個核心服務組成：

| 服務名稱 | 技術棧 | 職責 | 埠號 | GPU 需求 |
|---------|--------|------|------|----------|
| **Frontend** | Next.js 20 | 使用者介面，雙模式 UI（User/Developer） | 3000 (→80) | X |
| **Backend** | Python FastAPI | API Gateway，本地任務編排，連線 Lab Service | 8001 | X |
| **Lab Service** | Python FastAPI | OCR 工作流引擎，VLM 對話管理，資料入庫 | 9000 | V |
| **Paddle vLLM** | vLLM + PaddleOCR-VL | OCR/VLM 模型推理服務 | 8080 | V |
| **PostgreSQL** | PostgreSQL 16 | 結構化資料儲存（文件、OCR 結果、VLM 對話） | 5432 | X |
| **Redis** | Redis 7 | 任務狀態快取、工作佇列、版本快取 | 6379 | X |

### 2.3 系統資料流

```
使用者
  │
  ▼
┌─────────────────┐
│    Frontend     │ 使用者上傳 PDF，選擇 User/Developer 模式
│   (Next.js)     │
└────────┬────────┘
         │ HTTP REST API
         ▼
┌─────────────────┐
│    Backend      │ 1. 建立 local_job_id + document_id
│   (FastAPI)     │ 2. 轉送請求至 Lab Service
│                 │ 3. 提供狀態輪詢代理
└────────┬────────┘
         │ HTTP REST API
         ▼
┌─────────────────┐
│  Lab Service    │ 1. 建立 OCRRun，寫入 PostgreSQL
│   (FastAPI)     │ 2. 背景執行 OCR 工作流
│                 │ 3. 呼叫 Paddle vLLM 進行推理
│                 │ 4. 結果寫入 DB + Redis
└─────┬───────┬───┘
      │       │
      │       ▼
      │  ┌─────────────────┐
      │  │  Paddle vLLM    │ OCR 模型推理（PaddleOCR-VL）
      │  │  (vLLM Server)  │ 輸入：圖片 → 輸出：文字 + 座標
      │  └─────────────────┘
      │
      ▼
┌─────────────────┐  ┌─────────────────┐
│   PostgreSQL    │  │      Redis      │
│  (Documents,    │  │  (Job State,    │
│   OCR Results,  │  │   Cache, TTL)   │
│   VLM Sessions) │  │                 │
└─────────────────┘  └─────────────────┘
```

**流程說明**：

1. **上傳階段**：
   - Frontend → Backend：建立 `document_id` 與 `version_no`
   - Backend → Lab Service：轉送 PDF 檔案（multipart/form-data）
   - Lab Service：儲存檔案至 `/data/ocr/documents/`，建立 `OCRRun` 記錄

2. **處理階段**：
   - Lab Service 背景 Worker 執行 OCR Pipeline
   - 呼叫 Paddle vLLM 進行頁面推理
   - 將結果寫入 PostgreSQL（`pages`, `images`, `page_ocr_artifacts`）
   - 更新 Redis 任務狀態（`ocr:job:{job_id}`）

3. **輪詢階段**：
   - Frontend 定期向 Backend 查詢狀態
   - Backend 代理查詢 Lab Service
   - Lab Service 從 Redis 讀取最新狀態並回傳

4. **VLM 對話階段**：
   - 使用者選擇圖片進行 VLM 分析
   - Frontend → Backend → Lab Service → Gemini API
   - 對話歷史儲存於 PostgreSQL `vlm_sessions` + `vlm_messages`
5. **結構化資料萃取 (Extract)**：
   - 整合 OCR 文字識別與 VLM 圖片理解結果
   - 自動萃取 BOM（物料清單）、尺寸表等結構化資料
   - 將非結構化文件轉換為標準化 JSON 格式
   - 支援中英雙語欄位對照
   - 輸出結果儲存於 PostgreSQL，供後續查詢與匯出使用
---

## 3. 部署模式

### 3.1 單機部署（當前推薦）

**適用場景**：
- 中小規模使用
- GPU 資源有限（單一 GPU 主機）
- 快速部署與維護

**架構圖**：

```
┌─────────────────────────────────────────────────┐
│         GPU 主機 (Ubuntu 22.04)                  │
│  ┌───────────────────────────────────────────┐  │
│  │      Docker Compose 網路                   │  │
│  │                                            │  │
│  │  ┌─────────┐  ┌─────────┐  ┌───────────┐ │  │
│  │  │Frontend │  │ Backend │  │Lab Service│ │  │
│  │  └─────────┘  └─────────┘  └───────────┘ │  │
│  │                                  │         │  │
│  │       │             │            ▼         │  │
│  │       │             │      ┌──────────┐   │  │
│  │       │             │      │Paddle    │   │  │
│  │       │             │      │vLLM      │   │  │
│  │       │             │      └──────────┘   │  │
│  │       │             │            │         │  │
│  │       ▼             ▼            ▼         │  │
│  │  ┌────────────┐  ┌──────────────────┐    │  │
│  │  │ PostgreSQL │  │      Redis       │    │  │
│  │  └────────────┘  └──────────────────┘    │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  Volume 掛載：                                   │
│  - ./db/data → PostgreSQL                       │
│  - ./redis/data → Redis                         │
│  - ./ocr_data → Lab Service                     │
└─────────────────────────────────────────────────┘
```


### 3.2 分散式部署（未來擴展）

**適用場景**：
- 大規模使用
- 多 GPU 資源可用（GPU 叢集）
- 需要高可用性與負載均衡

**架構概念**：

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Web Server 1 │      │ Web Server 2 │      │ GPU Server 1 │
│ - Frontend   │      │ - Frontend   │      │ - Lab Svc    │
│ - Backend    │      │ - Backend    │      │ - Paddle vLLM│
└──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                     │                      │
       └──────────┬──────────┘                      │
                  │                                 │
           ┌──────▼─────────┐              ┌───────▼───────┐
           │  Load Balancer │              │ GPU Server 2  │
           └────────────────┘              │ - Lab Svc     │
                                           │ - Paddle vLLM │
                                           └───────────────┘
                  │
      ┌───────────┴───────────┐
      │                       │
┌─────▼──────┐        ┌───────▼─────┐
│ PostgreSQL │        │    Redis    │
│  (Primary) │        │  (Cluster)  │
└────────────┘        └─────────────┘
```



---

## 4. Docker Compose 配置詳解

### 4.1 服務依賴關係

```yaml
services:
  postgres:      # 基礎服務，無依賴
  redis:         # 基礎服務，無依賴
  
  paddle_vllm:   # 依賴：無（獨立推理服務）
  
  lab_service:   # 依賴：postgres, redis, paddle_vllm
    depends_on:
      - postgres
      - redis
      - paddle_vllm
  
  backend:       # 依賴：lab_service, postgres, redis
    depends_on:
      - lab_service
      - redis
      - postgres
  
  frontend:      # 依賴：backend
    depends_on:
      - backend
```

**啟動順序**：
1. `postgres` + `redis` 首先啟動
2. `paddle_vllm` 同時啟動（與 DB 無關）
3. `lab_service` 等待 postgres, redis, paddle_vllm 就緒
4. `backend` 等待 lab_service 就緒
5. `frontend` 最後啟動

### 4.2 GPU 資源配置

**需要 GPU 的服務**：

```yaml
paddle_vllm:
  gpus: all  # 使用所有可用 GPU
  
lab_service:
  gpus: all  # 需要 GPU 進行 OCR 預處理
```

**GPU 記憶體管理**：

- `VLLM_GPU_MEM_UTIL=0.6`：vLLM 保留 60% GPU VRAM
- 剩餘 40% 可供 Lab Service 或其他任務使用

### 4.3 Volume 掛載策略

| Volume | 主機路徑 | 容器路徑 | 用途  |
|--------|---------|---------|------|
| **DB Data** | `./db/data` | `/var/lib/postgresql/data` | PostgreSQL 資料檔案 |
| **Redis Data** | `./redis/data` | `/data` | Redis RDB 快照 |
| **OCR Data** | `./ocr_data` | `/data/ocr` | 上傳 PDF、OCR 輸出 |
| **DB Init** | `./docker/schema.sql` | `/docker-entrypoint-initdb.d/01_schema.sql` | 資料庫初始化腳本（單檔掛載） |

> **說明**：`paddle_vllm` 容器使用 Baidu 官方映像檔，已內建 PaddleOCR-VL 模型。

---

## 5. 環境變數配置指南

### 5.1 環境變數分類

**資料庫與快取**：
```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<強密碼>
POSTGRES_DB=mtm_poc

REDIS_PASSWORD=<強密碼>
```

**GPU 與模型**：
```env
# GPU 記憶體使用率 (0.0-1.0)
VLLM_GPU_MEM_UTIL=0.6
OCR_DATA_HOST=./ocr_data
```

**Docker 映像檔**：
```env
LAB_SERVICE_IMAGE=mtm/lab_service:protected
BACKEND_IMAGE=mtm/backend:protected
FRONTEND_IMAGE=mtm/frontend:latest
```

**效能調校**：
```env
# OCR Worker 並行數（建議從 1 開始，逐步增加）
WORKER_MAX_CONCURRENCY=1

# Job 狀態在 Redis 中的保留時間（604800 = 7天）
JOB_STATE_TTL_SECONDS=604800

# OCR 子進程超時（0 = 無限制，生產環境建議設定 300-600）
OCR_SUBPROCESS_TIMEOUT_SECONDS=0
```

**外部 API**：
```env
# 使用 VLM 對話時必填；未啟用該功能可留空
GEMINI_API_KEY=
```

**服務埠號**（如需修改）：
```env
LAB_PORT=9000
BACKEND_PORT=8001
FRONTEND_PORT=3000
```

### 5.2 開發 vs 生產環境配置建議

| 環境變數 | 開發環境 | 生產環境 | 說明 |
|---------|---------|---------|------|
| `POSTGRES_PASSWORD` | `devpass123` | `<強密碼>` | 生產環境必須使用強密碼 |
| `REDIS_PASSWORD` | `devredis` | `<強密碼>` | 同上 |
| `VLLM_GPU_MEM_UTIL` | `0.5` | `0.7` | 生產環境可提高以充分利用 GPU |
| `WORKER_MAX_CONCURRENCY` | `1` | `2-4` | 視 GPU 與 CPU 資源調整 |
| `OCR_SUBPROCESS_TIMEOUT_SECONDS` | `0` | `300-600` | 生產環境應設定超時避免卡死 |
| `JOB_STATE_TTL_SECONDS` | `86400` (1天) | `604800` (7天) | 生產環境保留更長時間便於追蹤 |

---

## 6. 安全加固建議



### 6.1 網路安全

**內部通訊**：
- 所有服務間通訊透過 Docker 內部網路（`bridge` 模式）
- 無需額外加密（已在隔離網路中）

**對外存取**：
- **強烈建議**：使用 VPN（Tailscale、WireGuard）
- **不建議**：直接暴露至公網

**若必須對外開放**：
```yaml
# 使用 Nginx 反向代理 + SSL/TLS
# 僅開放 Frontend (3000) 至公網
# Backend (8001) 與 Lab Service (9000) 僅內網可存取
```

### 6.2 資料加密

**傳輸加密**：
- 若透過公網存取，必須使用 HTTPS/SSL
- Gemini API 通訊已內建 HTTPS

**靜態資料加密**（可選）：
- PostgreSQL：啟用 `pgcrypto` 擴充，加密敏感欄位
- 檔案系統：使用 LUKS 或 dm-crypt 加密 Volume 掛載目錄

### 6.3 存取控制

**Docker Socket 保護**：
```bash
# 限制 docker.sock 存取權限
sudo chmod 660 /var/run/docker.sock
sudo chown root:docker /var/run/docker.sock
```

**防火牆規則**（使用 `ufw` 範例）：
```bash
# 僅允許特定 IP 存取
# 將 192.168.1.0 替換為實際內網網段
sudo ufw allow from 192.168.1.0/24 to any port 3000
sudo ufw allow from 192.168.1.0/24 to any port 8001
sudo ufw allow from 192.168.1.0/24 to any port 9000

# 啟用防火牆
sudo ufw enable
```

---

## 7. 故障排除指南

### 7.1 診斷流程

```
問題發生
   │
   ▼
┌─────────────────┐
│ 檢查容器狀態     │  docker compose ps
│ 是否全部 Up？    │
└────┬───────┬────┘
     │       │
  是 │       │ 否
     │       ▼
     │  ┌──────────────────┐
     │  │ 查看啟動失敗的    │  docker compose logs <service>
     │  │ 服務日誌         │  docker compose up <service>
     │  └──────────────────┘
     │
     ▼
┌─────────────────┐
│ 檢查服務回應     │  curl localhost:3000/8001/9000
│ HTTP 200？      │
└────┬───────┬────┘
     │       │
  是 │       │ 否
     │       ▼
     │  ┌──────────────────┐
     │  │ 檢查服務內部錯誤  │  docker compose logs -f <service>
     │  │ 是否有 Exception？│  查看應用程式日誌
     │  └──────────────────┘
     │
     ▼
┌─────────────────┐
│ 檢查資源使用     │  docker stats
│ CPU/記憶體/GPU   │  nvidia-smi
│ 是否正常？      │  df -h
└────┬───────┬────┘
     │       │
  是 │       │ 否
     │       ▼
     │  ┌──────────────────┐
     │  │ 資源不足：        │  增加硬體資源
     │  │ - 清理磁碟       │  調降並行數
     │  │ - 降低 GPU 使用   │  重啟服務
     │  └──────────────────┘
     │
     ▼
┌─────────────────┐
│ 檢查資料庫/Redis │  psql 連線測試
│ 連線是否正常？   │  redis-cli PING
└─────────────────┘
```

### 7.2 常見錯誤碼與解決方案

| 錯誤訊息 | 可能原因 | 解決方案 |
|---------|---------|---------|
| `relation "documents" does not exist` | 資料庫未初始化 | 刪除 `./db/data` 並重新啟動 |
| `CUDA out of memory` | GPU VRAM 不足 | 降低 `VLLM_GPU_MEM_UTIL` 或減少並行數 |
| `connection refused` (Frontend→Backend) | Backend 未啟動或網路配置錯誤 | 檢查 `LOCAL_API_BASE=http://backend:8001` |
| `Gemini API 429 Too Many Requests` | API 配額超限 | 等待或升級 API 計畫 |
| `Redis connection timeout` | Redis 密碼錯誤或未啟動 | 檢查 `REDIS_PASSWORD` 與 `docker compose ps redis` |
| `Permission denied` (Volume 掛載) | 檔案權限問題 | `sudo chown -R $USER:$USER ./db ./redis ./ocr_data` |

### 7.3 效能問題診斷

**症狀：OCR 處理很慢**

```bash
# 1. 檢查 GPU 使用率
nvidia-smi

# 若 GPU 使用率低 (<50%)
#   → 可能是 CPU 瓶頸，檢查 WORKER_MAX_CONCURRENCY

# 若 GPU 使用率高 (>90%) 但處理慢
#   → 可能是模型載入問題，檢查 paddle_vllm 日誌

# 2. 檢查 paddle_vllm 日誌
docker compose logs paddle_vllm | grep -i "latency\|throughput"

# 3. 檢查資料庫查詢效能
docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
  SELECT query, mean_exec_time, calls 
  FROM pg_stat_statements 
  ORDER BY mean_exec_time DESC 
  LIMIT 10;
"'
```

**症狀：記憶體不足**

```bash
# 1. 查看記憶體使用
free -h
docker stats

# 2. 識別記憶體消耗大戶
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}" | sort -k2 -h

# 3. 調整策略
#   - 降低 WORKER_MAX_CONCURRENCY
#   - 增加系統 swap
#   - 考慮升級硬體
```

---

## 8. 版本記錄

| 版本 | 日期 | 變更內容 | 作者 |
|------|------|---------|------|
| 1.0 | 2026-02-09 | 現階段系統初版部署文件 | - |



