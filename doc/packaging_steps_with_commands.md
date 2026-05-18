# 打包與安裝步驟（含完整指令）

> 依你的需求整理：
> - OCR 走 conda-pack
> - 50 系列 / 40 系列分開 image
> - CUDA 12.8 / Python 3.10
> - backend: uvicorn
> - frontend: npm

---

## 1) 直接打包「現有可用」的 conda 環境

> 你要的是「整份環境」而不是只裝幾個套件。\n> 所以不要新建空白 env，直接打包你已經成功跑起來的 env。

### 1.1 安裝 conda-pack
```bash
conda install -n base -c conda-forge conda-pack
```

### 1.2 找出目前能跑的 env 名稱
```bash
conda env list
```

### 1.3 直接打包現有 env
```bash
# 你目前的環境命名：
# - paddleocr: llama
# - lab_service: mtm_api
#
# 建議：直接打包「paddleocr 能跑的環境」(llama)，
# 讓容器內用同一套環境跑 lab_service + paddleocr。
#
# 40 系列機器上（假設 llama40 是你的 40 系列環境名）
conda pack -n llama40 -o /tmp/llama40.tar.gz
#
# 50 系列機器上（假設 llama50 是你的 50 系列環境名）
conda pack -n llama50 -o /tmp/llama50.tar.gz
```

> 如果你兩種環境都在同一台機器，也可以在同一台上打包兩個 env。\n> 若不是，請在各自能跑的主機上打包後再集中放到 build 機器。

### 1.4（可選）把 `mtm_api` 依賴併入 `llama` 再打包
> 如果你希望 **單一 conda env** 同時跑 `lab_service + paddleocr`，\n> 可以把 `lab_service/requirements.txt` 裝進 `llama`。\n> 這樣容器內只有一套環境，最簡單。

```bash
# 以 40 系列 env 為例
conda activate llama40
pip install -r /path/to/MTM_POC/lab_service/requirements.txt
conda deactivate

# 以 50 系列 env 為例
conda activate llama50
pip install -r /path/to/MTM_POC/lab_service/requirements.txt
conda deactivate
```

完成後再進行打包：
```bash
conda pack -n llama40 -o /tmp/llama40.tar.gz
conda pack -n llama50 -o /tmp/llama50.tar.gz
```

---

## 2) lab_service Dockerfile（共用）
建立：`docker/lab_service.Dockerfile`

```Dockerfile
ARG CUDA_IMAGE
FROM ${CUDA_IMAGE}

RUN apt-get update && apt-get install -y \
    curl ca-certificates bzip2 \
    libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

ARG CONDA_TAR
RUN mkdir -p /opt/conda/envs/llama
COPY ${CONDA_TAR} /tmp/llama.tar.gz
RUN tar -xzf /tmp/llama.tar.gz -C /opt/conda/envs/llama \
    && /opt/conda/envs/llama/bin/conda-unpack \
    && rm /tmp/llama.tar.gz

ENV PATH=/opt/conda/envs/llama/bin:$PATH

WORKDIR /app
COPY lab_service/ /app/
RUN pip install -r /app/requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

---

## 3) build 兩個 lab_service image
```bash
# 40 系列
docker build -f docker/lab_service.Dockerfile \
  --build-arg CUDA_IMAGE=nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04 \
  --build-arg CONDA_TAR=/tmp/llama40.tar.gz \
  -t mtm/lab_service:official .

# 50 系列
docker build -f docker/lab_service.Dockerfile \
  --build-arg CUDA_IMAGE=nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04 \
  --build-arg CONDA_TAR=/tmp/llama50.tar.gz \
  -t mtm/lab_service:rtx50 .
```

---

## 4) backend Dockerfile
建立：`docker/backend.Dockerfile`

```Dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY backend/ /app/
RUN pip install -r /app/requirements.txt

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build：
```bash
docker build -f docker/backend.Dockerfile -t mtm/backend:latest .
```

---

## 5) frontend Dockerfile
建立：`docker/frontend.Dockerfile`

```Dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/ /app/
RUN npm install
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/out /usr/share/nginx/html
EXPOSE 80
```

Build：
```bash
docker build -f docker/frontend.Dockerfile -t mtm/frontend:latest .
```

---

## 6) docker-compose.yml 範例
```yaml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: mtm
      POSTGRES_PASSWORD: mtm
      POSTGRES_DB: mtm_poc
    volumes:
      - ./data/postgres:/var/lib/postgresql/data

  redis:
    image: redis:7
    command: ["redis-server", "--requirepass", "mtm"]
    volumes:
      - ./data/redis:/data

  paddle_vllm:
    image: ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddlex-genai-vllm-server:latest
    command: >
      python3 -m vllm.entrypoints.openai.api_server
      --model /root/.paddlex/official_models/PaddleOCR-VL
      --served-model-name PaddleOCR-VL-0.9B
      --host 0.0.0.0
      --port 8080
      --trust-remote-code
      --max-model-len 8192
      --gpu-memory-utilization 0.4
    ports:
      - "8080:8080"
    shm_size: "8g"
    volumes:
      - ./data/paddle_models:/root/.paddlex/official_models
    gpus: all

  lab_service:
    image: ${LAB_SERVICE_IMAGE}
    environment:
      DATABASE_URL: postgresql+psycopg2://mtm:mtm@postgres:5432/mtm_poc
      REDIS_URL: redis://:mtm@redis:6379/0
      PADDLE_VLLM_URL: http://paddle_vllm:8080/v1
      OCR_DATA_ROOT: /data/ocr
    volumes:
      - ./data/ocr:/data/ocr
    depends_on:
      - postgres
      - redis
      - paddle_vllm
    gpus: all
    ports:
      - "8001:8001"

  backend:
    image: mtm/backend:latest
    depends_on:
      - lab_service
    ports:
      - "8000:8000"

  frontend:
    image: mtm/frontend:latest
    depends_on:
      - backend
    ports:
      - "3000:80"
```

啟動：
```bash
# 40 系列
export LAB_SERVICE_IMAGE=mtm/lab_service:official
docker compose up -d

# 50 系列
export LAB_SERVICE_IMAGE=mtm/lab_service:rtx50
docker compose up -d
```

---

## 7) 重點提醒
- 主機仍需 NVIDIA driver + Docker + NVIDIA toolkit
- CUDA runtime 版本需與主機 driver 相容
- OCR / DB / Redis / 模型資料要用 volume 保存

---

## 8) 推送到 Docker Hub（範例）
> 將本機 image 重新 tag 後推到 Docker Hub。\n> 範例使用帳號 `yourname`，請換成你的帳號。

### 8.1 登入
```bash
docker login
```

### 8.2 tag + push
```bash
# lab_service 40 系列
docker tag mtm/lab_service:official yourname/mtm-lab-service:official
docker push yourname/mtm-lab-service:official

# lab_service 50 系列
docker tag mtm/lab_service:rtx50 yourname/mtm-lab-service:rtx50
docker push yourname/mtm-lab-service:rtx50

# backend
docker tag mtm/backend:latest yourname/mtm-backend:latest
docker push yourname/mtm-backend:latest

# frontend
docker tag mtm/frontend:latest yourname/mtm-frontend:latest
docker push yourname/mtm-frontend:latest
```
