import time

from fastapi.testclient import TestClient

from app.main import app
from app.services.lab_client import LabApiTimeout
from app.api.routers import local_ocr


def _setup_state_store(monkeypatch):
    store = {}
    version_cache = {}

    def _set_state(local_job_id, state):
        state = dict(state)
        state["updated_at"] = int(time.time())
        store[local_job_id] = state
        return state

    def _get_state(local_job_id):
        return store.get(local_job_id)

    def _update_state(local_job_id, updates):
        current = store.get(local_job_id)
        if current is None:
            return None
        current = dict(current)
        current.update(updates)
        current["updated_at"] = int(time.time())
        store[local_job_id] = current
        return current

    def _get_latest_doc_version(document_id):
        return version_cache.get(document_id)

    def _set_latest_doc_version(document_id, version_no):
        version_cache[document_id] = version_no

    def _ensure_document_exists(_document_id, _title, _file_path, _page_count, _status):
        return None

    def _get_latest_version(_document_id):
        return None

    def _insert_document_version(document_id, version_no, _label):
        version_cache[document_id] = version_no
        return version_no

    monkeypatch.setattr(local_ocr, "set_local_job_state", _set_state)
    monkeypatch.setattr(local_ocr, "get_local_job_state", _get_state)
    monkeypatch.setattr(local_ocr, "update_local_job_state", _update_state)
    monkeypatch.setattr(local_ocr, "get_latest_doc_version", _get_latest_doc_version)
    monkeypatch.setattr(local_ocr, "set_latest_doc_version", _set_latest_doc_version)
    monkeypatch.setattr(local_ocr, "ensure_document_exists", _ensure_document_exists)
    monkeypatch.setattr(local_ocr, "get_latest_version", _get_latest_version)
    monkeypatch.setattr(local_ocr, "insert_document_version", _insert_document_version)

    return store


def test_create_and_get_job(monkeypatch):
    _setup_state_store(monkeypatch)

    def _fake_create(**_kwargs):
        return {
            "job_id": "lab-123",
            "ocr_run_id": 8,
            "status": "queued",
            "output_dir": "/lab/path/D42260_v17",
        }

    def _fake_get(**_kwargs):
        return {
            "status": "running",
            "step": "parse_and_mapping",
            "progress": 0.52,
            "ocr_run_id": 8,
            "output_dir": "/lab/path/D42260_v17",
        }

    monkeypatch.setattr(local_ocr, "create_ocr_job", _fake_create)
    monkeypatch.setattr(local_ocr, "get_ocr_job", _fake_get)

    client = TestClient(app)
    files = {"file": ("doc.pdf", b"%PDF-1.4\n%EOF\n", "application/pdf")}
    response = client.post("/local/ocr/jobs", files=files)
    assert response.status_code == 200
    payload = response.json()
    assert payload["lab_job_id"] == "lab-123"
    assert "document_id" in payload
    assert payload["document_version_id"] == 1
    assert payload["document_version_no"] == 1

    local_job_id = payload["local_job_id"]
    response = client.get(f"/local/ocr/jobs/{local_job_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "lab"
    assert payload["status"] == "running"
    assert payload["step"] == "parse_and_mapping"


def test_lab_timeout_on_create(monkeypatch):
    _setup_state_store(monkeypatch)

    def _fake_create(**_kwargs):
        raise LabApiTimeout("timeout")

    monkeypatch.setattr(local_ocr, "create_ocr_job", _fake_create)

    client = TestClient(app)
    files = {"file": ("doc.pdf", b"%PDF-1.4\n%EOF\n", "application/pdf")}
    response = client.post("/local/ocr/jobs", files=files)
    assert response.status_code == 504


def test_cancel_job(monkeypatch):
    store = _setup_state_store(monkeypatch)

    def _fake_cancel(**_kwargs):
        return {"status": "cancel_requested"}

    monkeypatch.setattr(local_ocr, "cancel_ocr_job", _fake_cancel)

    local_job_id = "local-1"
    store[local_job_id] = {
        "local_job_id": local_job_id,
        "lab_job_id": "lab-1",
        "document_id": "D1",
        "document_version_id": 1,
        "ocr_run_id": 1,
        "status": "running",
        "step": "ocr",
        "progress": 0.2,
        "output_dir": "/lab/path/D1_v1",
        "cancel_requested": False,
        "error_code": None,
        "error_message": None,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }

    client = TestClient(app)
    response = client.post(f"/local/ocr/jobs/{local_job_id}/cancel")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cancel_requested"] is True
