ARG CUDA_IMAGE=nvidia/cuda:11.8.0-base-ubuntu22.04
ARG CONDA_TAR=./mtm_env.tar.gz

FROM ${CUDA_IMAGE} AS env_builder
ARG CONDA_TAR

RUN mkdir -p /opt/conda/envs/mtm_env
COPY ${CONDA_TAR} /tmp/mtm_env.tar.gz
RUN tar -xzf /tmp/mtm_env.tar.gz -C /opt/conda/envs/mtm_env \
    && /opt/conda/envs/mtm_env/bin/python /opt/conda/envs/mtm_env/bin/conda-unpack \
    && rm -f /tmp/mtm_env.tar.gz

FROM ${CUDA_IMAGE} AS runtime

RUN apt-get update && apt-get install -y \
    curl ca-certificates bzip2 \
    libglib2.0-0 libgl1 \
    python3 python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=env_builder /opt/conda/envs/mtm_env /opt/conda/envs/mtm_env
ENV PATH=/opt/conda/envs/mtm_env/bin:$PATH

WORKDIR /app
COPY lab_service/ /app/

RUN /opt/conda/envs/mtm_env/bin/python -m compileall -b /app \
    && find /app -name "*.py" -type f ! -name "__init__.py" -delete

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
