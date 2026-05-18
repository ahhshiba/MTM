# MTM 系統安裝指南

## 文件資訊

| 項目 | 內容 |
|------|------|
| 文件版本 | 1.0 |
| 系統版本 | MTM POC v1.0 |
| 最後更新 | 2026-02-09 |

---

## 1. 文件目的

本文件提供 MTM 系統的完整安裝與部署指南，協助客戶在生產環境中快速、正確地完成系統部署。


---

## 2. 系統概述

MTM (Material Tech Management) 是一套基於 AI 的技術文件智慧處理系統，整合 OCR 與 VLM 技術，提供以下核心功能：

### 核心功能

1. **智慧文件辨識 (OCR)**
   - 自動辨識 PDF 文件中的文字、表格與圖像
   - 支援多頁文件批次處理
   - 基於 PaddleOCR-VL 模型

2. **AI 對話分析 (VLM)**
   - 透過 Gemini VLM 進行圖片理解與問答
   - 支援多輪對話，保留上下文
   - 可針對特定圖片區域進行深度分析

3. **結構化資料萃取 (Extract)**
   - 自動萃取 BOM（物料清單）、尺寸表等結構化資料
   - 輸出標準化 JSON 格式
   - 支援中英雙語對照
   - 整合 OCR 與 VLM 結果，提供完整的文件結構化資料

4. **雙模式介面**
   - **User Mode**：簡化流程，適合一般使用者
   - **Developer Mode**：完整除錯視圖，顯示詳細處理資訊

### 系統架構

```
┌─────────────┐
│  Frontend   │ (Port 3000, Next.js UI)
│  (Browser)  │
└──────┬──────┘
       │
┌──────▼──────┐
│   Backend   │ (Port 8001, API Gateway)
└──────┬──────┘
       │
┌──────▼──────┐
│ Lab Service │ (Port 9000, OCR & VLM Processing)
└──────┬──────┘
       │
   ┌───┴────────────────┬──────────────┐
   │                    │              │
┌──▼────────┐  ┌────────▼─┐  ┌────────▼────────┐
│ PostgreSQL │  │  Redis   │  │  Paddle vLLM    │
│   (DB)     │  │ (Cache)  │  │ (OCR Engine)    │
└────────────┘  └──────────┘  └─────────────────┘
```

---

## 3. 硬體與軟體需求

### 3.1 硬體需求

| 組件 | 最低需求 | 建議規格 | 備註 |
|------|---------|---------|------|
| **CPU** | 8 核心 | 16 核心以上 | 支援 x86_64 架構 |
| **記憶體** | 32 GB | 64 GB 以上 | 建議預留 50% 供 GPU 共享記憶體使用 |
| **GPU** | NVIDIA RTX 4060 (8GB VRAM) | RTX 4090 / A100 (24GB+ VRAM) | 必須支援 CUDA 11.8+ |
| **VRAM** | 8 GB | 24 GB 以上 | vLLM 模型載入需 6-8 GB |
| **系統磁碟** | 100 GB SSD | 500 GB NVMe SSD | 用於系統與 Docker 映像檔 |
| **資料磁碟** | 500 GB | 1 TB 以上 | 用於 OCR 資料、資料庫、模型檔案 |
| **網路** | 1 Gbps | 10 Gbps | 內網頻寬，若使用遠端存取建議採用 VPN |

### 3.2 軟體需求

| 軟體 | 版本需求 | 驗證指令 |
|------|---------|---------|
| **作業系統** | Ubuntu 22.04 LTS 或更新版本 | `lsb_release -a` |
| **NVIDIA Driver** | 525.x 或更新（支援 CUDA 12.0+） | `nvidia-smi` |
| **Docker Engine** | 24.0 或更新版本 | `docker --version` |
| **Docker Compose** | 2.20 或更新版本 | `docker compose version` |
| **NVIDIA Container Toolkit** | 1.14 或更新版本 | `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` |

### 3.3 網路需求

| 項目 | 說明 |
|------|------|
| **內部通訊埠** | Docker 容器間內部網路通訊 |
| **對外開放埠** | 3000 (Frontend), 8001 (Backend), 9000 (Lab Service) |
| **外部 API 存取** | 需能連線至 Google Gemini API (`generativelanguage.googleapis.com`) |
| **防火牆** | 若從外部網路存取，建議透過 VPN（如 Tailscale、WireGuard） |

---

## 4. 檔案清單確認

在開始安裝前，請確認您已收到以下檔案：

### 4.1 必要檔案

- [ ] `compose.yaml` - Docker Compose 編排檔案
- [ ] `.env.example` - 環境變數範本檔案
- [ ] `docker/schema.sql` - 資料庫初始化 SQL 腳本
- [ ] `mtm_images.tar` - Docker 映像檔壓縮包（或分割檔 `mtm_images.tar.part-*`）


### 4.2 選用文件

- [ ] 安裝指南（本文件）
- [ ] 產品部署手冊 (`product_deployment_manual.md`)
- [ ] API 參考文件 (`apiReadme.md`)
- [ ] 資料庫結構文件 (`databaseSchema.md`)
- [ ] Redis Keys 說明 (`redisKeys.md`)

---

## 5. 環境準備

### 5.1 驗證主機運算環境

在開始安裝前，請先驗證主機是否滿足所有需求：

```bash
# 1. 檢查作業系統版本
lsb_release -a
# 預期輸出：Ubuntu 22.04 或更新版本

# 2. 檢查 NVIDIA 驅動
nvidia-smi
# 預期輸出：應顯示 GPU 資訊與驅動版本（525.x 或更新）

# 3. 檢查 Docker
docker --version
# 預期輸出：Docker version 24.0 或更新

# 4. 檢查 Docker Compose
docker compose version
# 預期輸出：Docker Compose version 2.20 或更新

# 5. 檢查 NVIDIA Container Toolkit（關鍵步驟）
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
# 預期輸出：應顯示與主機相同的 GPU 資訊，證明 Docker 可正常使用 GPU
```

> **重要提示**：如果第 5 步失敗，表示 NVIDIA Container Toolkit 未正確安裝，請先完成 5.2 ~ 5.4 節的安裝步驟。

### 5.2 安裝 NVIDIA Driver（如未安裝）

```bash
# 自動安裝推薦的驅動版本
sudo ubuntu-drivers autoinstall

# 重新啟動系統以載入驅動
sudo reboot

# 重啟後驗證
nvidia-smi
```

### 5.3 安裝 Docker Engine（如未安裝）

```bash
# 1. 更新套件索引
sudo apt-get update

# 2. 安裝必要工具
sudo apt-get install -y ca-certificates curl gnupg

# 3. 新增 Docker 官方 GPG 金鑰
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# 4. 設定 Docker 儲存庫
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. 安裝 Docker Engine 與 Compose
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 6. （選用）將當前使用者加入 docker 群組（避免每次都需要 sudo）
sudo usermod -aG docker $USER
newgrp docker

# 7. 驗證安裝
docker --version
docker compose version
```

### 5.4 安裝 NVIDIA Container Toolkit（關鍵步驟）

```bash
# 1. 新增 NVIDIA Container Toolkit 儲存庫
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. 安裝
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. 配置 Docker Runtime
sudo nvidia-ctk runtime configure --runtime=docker

# 4. 重啟 Docker 服務
sudo systemctl restart docker

# 5. 驗證（關鍵步驟）
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
# 若成功顯示 GPU 資訊，即代表安裝完成
```

---

## 6. 系統安裝步驟

### 6.1 準備部署目錄

建議將所有部署檔案放置於統一目錄，例如 `/opt/mtm` 或 `/home/user/mtm_deployment`：

```bash
# 建立部署目錄（以 /opt/mtm 為例）
sudo mkdir -p /opt/mtm
sudo chown -R $USER:$USER /opt/mtm
cd /opt/mtm

# 建立必要的資料夾結構
mkdir -p docker db/data redis/data ocr_data
```

### 6.2 放置部署檔案

```bash
# 將交付的檔案複製到對應位置
# 1. 主要配置檔案（放在部署目錄根目錄）
#    - compose.yaml
#    - .env.example （需複製並重新命名為 .env）

# 2. 資料庫初始化腳本
#    - 將 schema.sql 放入 ./docker/schema.sql
#    - compose 建議只掛載單一檔案：
#      ./docker/schema.sql:/docker-entrypoint-initdb.d/01_schema.sql:ro
#    - schema.sql 建議僅保留 schema 建立語句，避免含以下內容：
#      * SET transaction_timeout ...
#      * ALTER ... OWNER TO ...
#      * 非 SQL 檔案混入 init 目錄



# 驗證目錄結構
tree -L 2 .
# 預期輸出：
# .
# ├── compose.yaml
# ├── .env.example
# ├── docker/
# │   └── schema.sql
# ├── db/
# │   └── data/
# ├── redis/
# │   └── data/
# ├── ocr_data/
```

### 6.3 載入 Docker 映像檔

#### 方式 A：單一映像檔

```bash
# 載入映像檔
docker load -i mtm_images.tar

# 驗證映像檔已載入
docker images | grep mtm
# 預期輸出應包含：
# - mtm/frontend
# - mtm/backend
# - mtm/lab_service
```

#### 方式 B：分割映像檔

如果映像檔因大小限制被分割（如 `mtm_images.tar.part-aa`, `mtm_images.tar.part-ab` ...）：

```bash
# 合併分割檔案
cat mtm_images.tar.part-* > mtm_images.tar

# 載入映像檔
docker load -i mtm_images.tar

# 驗證
docker images | grep mtm
```

### 6.4 配置環境變數

```bash
# 複製環境變數範本
cp .env.example .env

# 使用您偏好的編輯器編輯 .env
nano .env  # 或使用 vim、vi 等
```

**必須配置的環境變數**：

```env
# ===== 資料庫配置 =====
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<請設定強密碼>
POSTGRES_DB=mtm_poc

# ===== Redis 配置 =====
REDIS_PASSWORD=<請設定強密碼>

# ===== GPU 與模型配置 =====
VLLM_GPU_MEM_UTIL=0.6                    # GPU 記憶體使用率（0.0-1.0）
OCR_DATA_HOST=./ocr_data                 # OCR 輸出資料夾路徑

# ===== Docker 映像檔名稱 =====
LAB_SERVICE_IMAGE=mtm/lab_service:protected
BACKEND_IMAGE=mtm/backend:protected

# ===== 效能調校 =====
WORKER_MAX_CONCURRENCY=1                 # OCR 並行處理數（建議從 1 開始）
JOB_STATE_TTL_SECONDS=604800             # Job 狀態保留時間（7 天）
OCR_SUBPROCESS_TIMEOUT_SECONDS=0         # OCR 超時設定（0 表示不限制）

# ===== Gemini API 配置 =====
# 若未使用 Gemini 相關功能可先留空
GEMINI_API_KEY=

# ===== 服務埠號配置 =====
LAB_PORT=9000
BACKEND_PORT=8001
FRONTEND_PORT=3000
```

> **重要提示**：
> - `POSTGRES_PASSWORD` 和 `REDIS_PASSWORD` 請務必設定強密碼
> - 使用 VLM 對話功能時，`GEMINI_API_KEY` 需從 [Google AI Studio](https://aistudio.google.com/app/apikey) 取得
> - `VLLM_GPU_MEM_UTIL` 建議設為 0.6，若 GPU VRAM 較大可調高至 0.8

### 6.5 啟動系統

```bash
# 確認當前目錄包含 compose.yaml
ls -l compose.yaml

# 啟動所有服務（背景模式）
docker compose up -d

# 查看服務狀態
docker compose ps
```

**預期輸出**（所有服務狀態應為 `Up` 或 `Running`）：

```
NAME                    IMAGE                           STATUS
mtm-backend-1           mtm/backend:protected           Up
mtm-frontend-1          mtm/frontend:latest             Up
mtm-lab_service-1       mtm/lab_service:protected       Up
mtm-paddle_vllm-1       ccr-.../paddlex-genai-...       Up
mtm-postgres-1          postgres:16                     Up
mtm-redis-1             redis:7                         Up
```

### 6.6 查看啟動日誌

```bash
# 查看所有服務日誌
docker compose logs -f

# 僅查看特定服務（例如：lab_service）
docker compose logs -f lab_service

# 查看最近 100 行日誌
docker compose logs --tail=100
```

**關鍵檢查點**：
- `postgres`：應顯示 `database system is ready to accept connections`
- `paddle_vllm`：應顯示 `Uvicorn running on` 或模型載入完成訊息
- `lab_service`：應顯示 `Application startup complete`
- `backend`：應顯示 `Application startup complete`
- `frontend`：應顯示 `ready started server on 0.0.0.0:80`

---

## 7. 系統驗證

### 7.1 基本健康檢查

```bash
# 1. 檢查所有容器是否正常運行
docker compose ps

# 2. 檢查 Frontend 是否可存取
curl -s http://127.0.0.1:3000 | head -n 20

# 3. 檢查 Backend API 文件
curl -s http://127.0.0.1:8001/docs | head -n 20

# 4. 檢查 Lab Service API 文件
curl -s http://127.0.0.1:9000/docs | head -n 20

# 5. 檢查資料庫連線（使用容器內環境變數）
docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
# 應顯示資料表清單（documents, ocr_runs, pages 等）

# 6. 檢查 Redis 連線
docker compose exec redis redis-cli -a "${REDIS_PASSWORD}" ping
# 應輸出：PONG
```

### 7.2 功能驗證

開啟瀏覽器，訪問以下網址進行功能驗證：

| 服務 | URL | 驗證項目 |
|------|-----|---------|
| **Frontend** | `http://<主機IP>:3000` | 確認 UI 可正常載入，能切換 User/Developer 模式 |
| **Backend API Docs** | `http://<主機IP>:8001/docs` | 確認 Swagger UI 可開啟，API 列表完整 |
| **Lab Service API Docs** | `http://<主機IP>:9000/docs` | 確認 Swagger UI 可開啟，OCR 與 VLM API 可見 |

**完整流程測試**：
1. 在 Frontend 上傳一份測試 PDF 檔案
2. 觀察 Processing 步驟顯示 OCR 與 VLM 進度
3. 確認能在 Final Review 步驟檢視萃取結果
4. 驗證資料是否正確儲存至資料庫

---

## 8. 日常維運

### 8.1 常用指令

```bash
# 啟動系統
docker compose up -d

# 停止系統（保留資料）
docker compose down

# 停止系統並刪除資料（危險操作！）
docker compose down -v

# 重啟特定服務
docker compose restart backend

# 重啟所有服務
docker compose restart

# 查看即時日誌
docker compose logs -f

# 查看資源使用狀況
docker stats

# 查看 GPU 使用狀況
nvidia-smi -l 1  # 每秒更新
```

### 8.2 資料備份

**資料庫備份**：

```bash
# 備份資料庫（匯出 SQL）
docker compose exec -T postgres sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup_$(date +%Y%m%d_%H%M%S).sql

# 還原資料庫
cat backup_20260209_120000.sql | docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

**檔案資料備份**：

```bash
# 備份重要資料目錄
tar -czf mtm_backup_$(date +%Y%m%d).tar.gz \
  db/data \
  redis/data \
  ocr_data \
  .env

# 還原
tar -xzf mtm_backup_20260209.tar.gz
```

### 8.3 系統升級

```bash
# 1. 停止服務
docker compose down

# 2. 備份資料（重要！）
tar -czf mtm_backup_before_upgrade_$(date +%Y%m%d).tar.gz db/data redis/data ocr_data .env

# 3. 載入新版映像檔
docker load -i mtm_images_v2.tar

# 4. 更新 .env 檔案中的映像檔版本（如需要）
# 例如：LAB_SERVICE_IMAGE=mtm/lab_service:v2.0

# 5. 啟動新版本
docker compose up -d

# 6. 驗證服務
docker compose ps
docker compose logs -f
```

### 8.4 系統回滾

如果升級後出現問題：

```bash
# 1. 停止新版本
docker compose down

# 2. 還原資料（如有備份）
tar -xzf mtm_backup_before_upgrade_20260209.tar.gz

# 3. 修改 .env 檔案，恢復舊版映像名稱
# 例如：LAB_SERVICE_IMAGE=mtm/lab_service:v1.0

# 4. 啟動舊版本
docker compose up -d
```

---

## 9. 常見問題排查

### 9.1 資料庫初始化失敗

**症狀**：服務啟動後報錯 `relation "documents" does not exist`

**原因**：`schema.sql` 未正確執行

**解決方式**：

```bash
# 1. 停止所有服務
docker compose down

# 2. 刪除資料庫資料（會清空所有資料！）
rm -rf db/data

# 3. 確認 schema.sql 位置正確
ls -l docker/schema.sql

# 4. 重新啟動
docker compose up -d

# 5. 檢查資料表是否建立成功
docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

### 9.2 Frontend 無法連線至 Backend

**症狀**：瀏覽器顯示 `fetch failed` 或 `ECONNREFUSED`

**可能原因與解決**：

```bash
# 1. 檢查 Backend 是否正常運行
docker compose ps backend
docker compose logs backend

# 2. 確認 compose.yaml 中 frontend 的環境變數設定正確
#    應為：LOCAL_API_BASE=http://backend:8001
#    而非：LOCAL_API_BASE=http://localhost:8001
# 3. 若使用 Next.js rewrites，目標也必須是 backend 而非 localhost
#    destination: http://backend:8001/local/ocr/:path*

# 4. 重啟 Frontend
docker compose restart frontend
```

### 9.3 OCR 任務卡住或失敗

**症狀**：上傳 PDF 後進度條不動，或顯示處理失敗

**可能原因與解決**：

```bash
# 1. 檢查 paddle_vllm 是否正常啟動
docker compose logs paddle_vllm | grep -i "error\|warning"

# 2. 檢查 paddle_vllm 模型是否成功載入
#    注意：請確認掛載的模型目錄存在且完整
docker compose logs paddle_vllm | grep -i "model"

# 3. 檢查 GPU 記憶體是否足夠
nvidia-smi

# 4. 檢查 lab_service 日誌
docker compose logs lab_service --tail=100

# 5. 若 vLLM 模型載入失敗，可能需要調降 GPU 記憶體使用率
#    編輯 .env，調整：VLLM_GPU_MEM_UTIL=0.5
docker compose restart paddle_vllm lab_service
```

### 9.4 GPU 無法被 Docker 識別

**症狀**：容器啟動時報錯 `could not select device driver "" with capabilities: [[gpu]]`

**解決方式**：

```bash
# 1. 確認 NVIDIA Container Toolkit 已安裝
nvidia-ctk --version

# 2. 重新配置 Docker Runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 3. 測試 GPU 存取
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

# 4. 若仍失敗，檢查 /etc/docker/daemon.json
cat /etc/docker/daemon.json
# 應包含：
# {
#   "runtimes": {
#     "nvidia": {
#       "path": "nvidia-container-runtime",
#       "runtimeArgs": []
#     }
#   }
# }
```

### 9.5 記憶體不足 (OOM)

**症狀**：服務意外重啟，日誌顯示 `Killed` 或 `Out of Memory`

**解決方式**：

```bash
# 1. 檢查系統記憶體使用狀況
free -h
docker stats

# 2. 減少並行處理數
#    編輯 .env：WORKER_MAX_CONCURRENCY=1

# 3. 降低 GPU 記憶體使用率
#    編輯 .env：VLLM_GPU_MEM_UTIL=0.4

# 4. 增加系統 swap（臨時方案）
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

### 9.6 Gemini API 連線失敗

**症狀**：VLM 對話功能無法使用，日誌顯示 `Gemini API error`

**解決方式**：

```bash
# 1. 驗證 API Key 是否正確
#    檢查 .env 中的 GEMINI_API_KEY

# 2. 測試網路連線
curl -I https://generativelanguage.googleapis.com

# 3. 檢查防火牆或代理設定
#    確保可連線至 Google API

# 4. 若使用代理，可能需要在 compose.yaml 中設定 HTTP_PROXY
```

---

## 10. 安全建議

### 10.1 密碼安全

- [ ] 將 `POSTGRES_PASSWORD` 和 `REDIS_PASSWORD` 更改為高強度密碼（至少 16 字元，包含大小寫、數字、符號）
- [ ] 不要將 `.env` 檔案提交至版本控制系統
- [ ] 定期更換資料庫與 Redis 密碼

### 10.2 網路安全

- [ ] 生產環境建議使用 VPN（如 Tailscale、WireGuard）存取，不要直接暴露至公網
- [ ] 如需對外開放，建議使用反向代理（如 Nginx）並啟用 HTTPS/SSL
- [ ] 設定防火牆規則，僅開放必要的埠號
- [ ] 考慮使用 Cloudflare Tunnel 或類似服務提供安全存取

### 10.3 資料安全

- [ ] 定期備份資料庫與重要資料目錄
- [ ] 備份檔案應加密保存
- [ ] 測試備份還原流程，確保備份可用
- [ ] 設定自動化備份排程（例如：每日凌晨 2 點）

### 10.4 存取控制

- [ ] 限制能夠存取主機的使用者
- [ ] 使用 SSH 金鑰認證，停用密碼登入
- [ ] 定期檢視系統存取日誌
- [ ] 考慮實施多因素認證 (MFA)

---

## 11. 對外存取配置（VPN 建議）

如需讓外部使用者存取系統，建議採用以下方式之一：

### 11.1 Tailscale VPN（推薦）

```bash
# 1. 在主機上安裝 Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# 2. 啟動並登入
sudo tailscale up

# 3. 取得 Tailscale IP
tailscale ip -4
# 例如：100.122.33.28

# 4. 使用者透過 Tailscale VPN 連線後，即可使用此 IP 存取系統
# http://100.122.33.28:3000
```

### 11.2 Cloudflare Tunnel（快速測試）

```bash
# 1. 安裝 cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# 2. 建立臨時公開連結（僅用於測試）
cloudflared tunnel --url http://localhost:3000
# 會輸出類似：https://xxx.trycloudflare.com
```

> **重要提醒**：生產環境不建議直接暴露至公網，請優先採用 VPN 方案。

---

## 12. 檢查清單

部署完成後，請逐項確認：

- [ ] **環境驗證**
  - [ ] `nvidia-smi` 顯示 GPU 資訊正常
  - [ ] `docker --version` 版本符合需求
  - [ ] `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` 測試通過

- [ ] **檔案確認**
  - [ ] `compose.yaml` 已放置於部署目錄
  - [ ] `.env` 已配置且包含所有必要變數
  - [ ] `docker/schema.sql` 已放置正確位置

- [ ] **服務啟動**
  - [ ] `docker compose ps` 顯示所有服務為 `Up` 狀態
  - [ ] `docker compose logs` 無嚴重錯誤訊息

- [ ] **功能驗證**
  - [ ] Frontend UI 可正常開啟 (`http://<IP>:3000`)
  - [ ] Backend API 文件可存取 (`http://<IP>:8001/docs`)
  - [ ] Lab Service API 文件可存取 (`http://<IP>:9000/docs`)
  - [ ] 資料庫連線正常（`docker compose exec -T postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'` 顯示資料表）
  - [ ] 上傳測試 PDF，OCR 流程可正常完成
  - [ ] VLM 對話功能可正常使用

- [ ] **安全設定**
  - [ ] 資料庫與 Redis 密碼已更改為強密碼
  - [ ] Gemini API Key 已正確配置
  - [ ] VPN 或安全存取機制已設定（若需對外開放）

- [ ] **維運準備**
  - [ ] 已建立初始資料備份
  - [ ] 已記錄系統配置資訊（IP、埠號、版本等）
  - [ ] 已交接維運聯絡人與支援管道

---


## 附錄 A：目錄結構範例

```
/opt/mtm/
├── compose.yaml              # Docker Compose 編排檔案
├── .env                      # 環境變數配置（機敏資訊，勿提交版本控制）
├── .env.example              # 環境變數範本
├── docker/
│   └── schema.sql            # 資料庫初始化腳本
├── db/
│   └── data/                 # PostgreSQL 資料目錄（持久化）
├── redis/
│   └── data/                 # Redis 資料目錄（持久化）
├── ocr_data/                 # OCR 輸出資料（持久化）
│   ├── documents/
│   ├── pages/
│   └── images/
```

---

## 附錄 B：環境變數完整參考

| 變數名稱 | 預設值 | 說明 |
|---------|-------|------|
| `POSTGRES_USER` | `postgres` | PostgreSQL 使用者名稱 |
| `POSTGRES_PASSWORD` | *必填* | PostgreSQL 密碼 |
| `POSTGRES_DB` | `mtm_poc` | PostgreSQL 資料庫名稱 |
| `REDIS_PASSWORD` | *必填* | Redis 密碼 |
| `VLLM_GPU_MEM_UTIL` | `0.6` | vLLM GPU 記憶體使用率 (0.0-1.0) |
| `OCR_DATA_HOST` | `./ocr_data` | OCR 輸出主機路徑 |
| `LAB_SERVICE_IMAGE` | `mtm/lab_service:protected` | Lab Service Docker 映像名稱 |
| `BACKEND_IMAGE` | `mtm/backend:protected` | Backend Docker 映像名稱 |
| `WORKER_MAX_CONCURRENCY` | `1` | OCR Worker 最大並行數 |
| `JOB_STATE_TTL_SECONDS` | `604800` | Job 狀態保留時間（秒） |
| `OCR_SUBPROCESS_TIMEOUT_SECONDS` | `0` | OCR 子進程超時時間（0=無限制） |
| `GEMINI_API_KEY` | *選填* | 啟用 Gemini 對話功能時必填 |
| `LAB_PORT` | `9000` | Lab Service 對外埠號 |
| `BACKEND_PORT` | `8001` | Backend 對外埠號 |
| `FRONTEND_PORT` | `3000` | Frontend 對外埠號 |


