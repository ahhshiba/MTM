from pathlib import Path

def lab_doc_root(doc_id: str) -> Path:
    return Path("/lab_data/documents") / doc_id

def lab_ocr_run_dir(doc_id: str, version: int) -> Path:
    return lab_doc_root(doc_id) / "ocr" / f"run_{version}"

def lab_ocr_page_dir(doc_id: str, version: int, page_no: int) -> Path:
    return lab_ocr_run_dir(doc_id, version) / f"page_{page_no:03d}"
