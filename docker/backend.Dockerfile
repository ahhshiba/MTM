# FROM python:3.10-slim

# WORKDIR /app
# COPY backend/ /app/
# RUN pip install -r /app/requirements.txt

# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

####################protect
FROM python:3.10-slim

WORKDIR /app
COPY backend/ /app/
RUN pip install -r /app/requirements.txt

RUN python -m compileall -b /app && \
    find /app -name "*.py" -type f ! -name "__init__.py" -delete

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]


