# 打包與安裝流程詳解（Windows + Linux，VPN-only）

> 本文件提供「完整可落地」的打包與安裝步驟，涵蓋：
> - Docker 打包（前端 / 後端 / AI / OCR）
> - docker-compose 組裝
> - 一鍵安裝器流程
> - Windows（WSL2）與 Linux 分流
> - 50 系列 GPU 自編譯 wheel 的支援策略

---

## 0) 前置原則
- **一鍵安裝器負責主機層依賴**（GPU Driver / Docker / NVIDIA Toolkit / WSL2）。
- **所有服務一鍵啟動**：`docker compose up -d`。
- **VPN-only**：不對公網開放，使用者先連 VPN 再存取服務。

---

## 1) Docker 打包規劃
### 1.1 服務清單
- `lab_service`（含 OCR pipeline + paddleocr doc_parser）
- `paddle_vllm`（你現有 vLLM Docker）
- `backend`（你後端 API）
- `frontend`（前端靜態站）
- `postgres` / `redis`

### 1.2 兩種 OCR Image（因 50 系列需求）
- **官方版**：`lab_service:official`
- **50 系列版**：`lab_service:rtx50`（內含你自編譯 `.whl`）

安裝器會依 GPU 型號選擇拉取哪個 image。

---

## 2) lab_service OCR 容器化流程
### 2.1 目標
讓 `paddleocr doc_parser` 在容器內執行，不依賴主機 conda。

### 2.2 方案 A（最快）
**打包你目前成功的 conda 環境**
1) 在現有主機上確認 conda env 可跑：
   - `conda run -n llama paddleocr doc_parser -h`
2) 使用 `conda-pack` 將 env 打包成 tar.gz
3) 在 Dockerfile 中解壓到固定路徑
4) `PATH` 指向此 conda env
5) `lab_service` 啟動時仍使用：
   - `conda run -n llama paddleocr doc_parser ...`

### 2.3 方案 B（乾淨可重現）
**在 Dockerfile 內重新安裝**
1) 以 CUDA base image 為基底（建議選擇較保守版本）
2) 安裝 conda / mamba
3) 安裝 `paddlepaddle-gpu` + `paddleocr`
4) 安裝必要依賴（opencv、numpy、Pillow 等）

### 2.4 50 系列 wheel 支援
- 在 `lab_service:rtx50` image 中：
  - `pip install /opt/wheels/your_whl_file.whl`
- 在 `lab_service:official` image 中：
  - 使用官方套件

### 2.5 目前實際版本基準（你的現況）
**50 系列：**
- `paddleocr` 3.3.2
- `paddlepaddle-gpu` 3.1.0
- `paddlex` 3.3.11

**40 系列：**
- `paddleocr` 3.3.2
- `paddlepaddle-gpu` 3.2.2
- `paddlex` 3.3.11

---

## 3) vLLM Docker 組裝
### 3.1 直接搬入 compose
將你目前的命令搬進 `docker-compose.yml`：
- `image: ccr-.../paddlex-genai-vllm-server:latest`
- `command: python3 -m vllm.entrypoints.openai.api_server ...`
- `volumes:` 模型資料掛載
- `gpus: all`

### 3.2 服務內部呼叫
在 `lab_service` 的環境變數中設：
- `PADDLE_VLLM_URL=http://paddle_vllm:8080/v1`

---

## 4) backend / frontend Docker 化
### 4.1 backend
- 建一個 Dockerfile：
  - 安裝依賴
  - 啟動 `uvicorn` 或 `gunicorn`
- 透過環境變數指向 `lab_service` 內網 URL

### 4.2 frontend
- build 成靜態檔
- 用 `nginx` image serve
- 指向 backend URL（容器內或 VPN IP）

---

## 5) docker-compose 組裝規格
### 5.1 必要服務
- `lab_service`
- `paddle_vllm`
- `backend`
- `frontend`
- `postgres`
- `redis`

### 5.2 Volume 與資料路徑
- `./data/ocr` → `/data/ocr`
- `./data/postgres` → `/var/lib/postgresql/data`
- `./data/redis` → `/data`
- `./data/paddle_models` → `/root/.paddlex/official_models`

### 5.3 服務相依
- `lab_service` 依賴 `postgres` / `redis` / `paddle_vllm`
- `backend` 依賴 `lab_service`
- `frontend` 依賴 `backend`

---

## 6) VPN-only 部署流程
### 6.1 為什麼 VPN-only
- 不暴露公網
- 減少安全維護成本
- 內部人員透過 VPN 即可存取

### 6.2 推薦流程
1) GPU 主機先安裝 VPN server（WireGuard 或 Tailscale）
2) 內部人員安裝 VPN client
3) 使用 VPN IP 存取 `frontend` 或 `backend`

---

## 7) 一鍵安裝器流程（核心重點）
### 7.1 共用流程（Windows / Linux）
1) 檢查 GPU 型號
2) 檢查/安裝 NVIDIA Driver
3) 安裝 Docker
4) 安裝 NVIDIA Container Toolkit
5) 安裝 VPN（WireGuard / Tailscale）
6) 下載服務包（compose + configs）
7) 生成 `.env`
8) 判斷 GPU 型號 → 拉對 image
9) `docker compose up -d`
10) 顯示服務網址（VPN IP）

### 7.2 Windows 流程（需 WSL2）
1) 安裝 WSL2
2) 在 WSL2 內執行 Linux 安裝流程
3) Docker Desktop 使用 WSL2 backend

### 7.3 Linux 流程
- 直接執行腳本完成上述步驟

---

## 8) `.env` 產生規則
- 安裝器可讓使用者選填：
  - Postgres 帳密
  - Redis 密碼
  - Gemini API Key
- 未填則使用預設值

---

## 9) 交付物清單
### Phase 1
- 本文件（打包流程）
- 安裝流程草案
- docker-compose 規格草案

### Phase 2
- Dockerfile（lab_service / backend / frontend）
- docker-compose.yml
- Windows 安裝器（EXE）
- Linux 安裝器（script or package）

---

## 10) 建議優先順序
1) 先完成 Docker 化（lab_service + OCR）
2) 再做 compose 一鍵啟動
3) 最後做一鍵安裝器
