from fastapi import FastAPI
from app.api.routers import local_ocr

app = FastAPI(title="OCR Backend")

app.include_router(local_ocr.router)
