# app/services/ocr_parser.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class OCRParseError(RuntimeError):
    pass


def load_res_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise OCRParseError(f"Failed to load json: {path} - {e}") from e


def iter_res_json_files(output_dir: Path) -> List[Path]:
    return sorted(output_dir.glob("*_res.json"))


def extract_page_meta(res: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "page_index": res.get("page_index"),
        "page_count": res.get("page_count"),
        "width": res.get("width"),
        "height": res.get("height"),
        "input_path": res.get("input_path"),
    }


def extract_blocks(res: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks = res.get("parsing_res_list", [])
    if not isinstance(blocks, list):
        return []
    out: List[Dict[str, Any]] = []
    for b in blocks:
        if isinstance(b, dict):
            out.append(b)
    return out


def norm_bbox(bbox: Any) -> Optional[List[int]]:
    if bbox is None:
        return None
    if isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox):
        return [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
    return None


def pick_page_prefix(res_json_filename: str) -> str:
    # D42260_0_res.json -> D42260
    parts = res_json_filename.split("_")
    return parts[0] if parts else "doc"


def page_artifact_paths(output_dir: Path, prefix: str, page_index: int) -> Dict[str, Optional[str]]:
    base = f"{prefix}_{page_index}"
    res_json = output_dir / f"{base}_res.json"
    md = output_dir / f"{base}.md"
    det = output_dir / f"{base}_layout_det_res.png"

    return {
        "result_json_path": str(res_json) if res_json.exists() else None,
        "result_md_path": str(md) if md.exists() else None,
        "vis_image_path": str(det) if det.exists() else None,
    }
