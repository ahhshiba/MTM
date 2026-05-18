#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Attach bbox references from OCR *_res.json files to structured result JSON.

Usage:
  python scripts/attach_bboxes.py \
    --json /path/to/result_final.json \
    --run_dir /path/to/ocr_output \
    --output /path/to/result_final_bbox.json

"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    return text


def _normalize(text: str) -> str:
    text = _strip_html(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _get_text(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return obj.get("original") or obj.get("zh") or obj.get("text") or ""
    if isinstance(obj, str):
        return obj
    return str(obj)


def _page_index_from_name(path: Path) -> Optional[int]:
    parts = path.stem.split("_")
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return None


def _build_page_blocks(run_dir: Path) -> Dict[int, List[Dict[str, Any]]]:
    blocks_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for res_path in run_dir.glob("*_res.json"):
        data = _load_json(res_path)
        page = data.get("page_index")
        if page is None:
            page = _page_index_from_name(res_path)
        if page is None:
            continue
        page_blocks = []
        for blk in data.get("parsing_res_list", []) or []:
            text = blk.get("block_content") or ""
            bbox = blk.get("block_bbox")
            if not text or not bbox:
                continue
            page_blocks.append({
                "text": text,
                "norm": _normalize(text),
                "bbox": bbox,
                "label": blk.get("block_label"),
            })
        if page_blocks:
            blocks_by_page[int(page)] = page_blocks
    return blocks_by_page


def _match_blocks(page_blocks: List[Dict[str, Any]], target_text: str, max_hits: int = 6) -> List[Dict[str, Any]]:
    if not target_text or not page_blocks:
        return []
    target_norm = _normalize(target_text)
    if not target_norm:
        return []

    hits = []
    for blk in page_blocks:
        norm = blk.get("norm") or ""
        if len(norm) < 8:
            continue
        if norm in target_norm or target_norm in norm:
            score = min(len(norm), len(target_norm))
            hits.append((score, blk))
            continue
        # soft overlap: check any 3+ token overlap
        tokens = set(target_norm.split())
        blk_tokens = set(norm.split())
        overlap = len(tokens & blk_tokens)
        if overlap >= 3:
            score = overlap
            hits.append((score, blk))

    hits.sort(key=lambda x: x[0], reverse=True)
    out = []
    for _, blk in hits[:max_hits]:
        out.append({
            "bbox": blk.get("bbox"),
            "text": blk.get("text"),
            "label": blk.get("label"),
        })
    return out


def _attach_bbox(item: Dict[str, Any], blocks_by_page: Dict[int, List[Dict[str, Any]]]) -> None:
    page = item.get("source_page")
    if page is None:
        return
    page_blocks = blocks_by_page.get(int(page))
    if not page_blocks:
        return

    text = item.get("raw_text")
    if not text:
        # fallback to representative fields
        for key in ("content", "summary", "subject", "title"):
            text = _get_text(item.get(key))
            if text:
                break
    if not text:
        # fallback to items list
        items = item.get("items") or []
        if isinstance(items, list) and items:
            text = " ".join(_get_text(it.get("text") if isinstance(it, dict) else it) for it in items[:5])
    if not text:
        return

    matches = _match_blocks(page_blocks, text)
    if matches:
        item["bbox_refs"] = matches


def _attach_bbox_to_bom(section: Dict[str, Any], blocks_by_page: Dict[int, List[Dict[str, Any]]]) -> None:
    items = section.get("items") or []
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        page = item.get("source_page") or section.get("source_page")
        if page is None:
            continue
        parts = [
            _get_text(item.get("part")),
            _get_text(item.get("material_name")),
            _get_text(item.get("composition")),
            _get_text(item.get("color")),
            _get_text(item.get("supplier")),
            _get_text(item.get("comments")),
            _get_text(item.get("remarks")),
        ]
        text = " ".join(p for p in parts if p)
        if not text:
            continue
        temp = {"source_page": page, "raw_text": text}
        _attach_bbox(temp, blocks_by_page)
        if temp.get("bbox_refs"):
            item["bbox_refs"] = temp["bbox_refs"]


def _attach_bbox_to_measurement(section: Dict[str, Any], blocks_by_page: Dict[int, List[Dict[str, Any]]]) -> None:
    points = section.get("points") or []
    if not isinstance(points, list):
        return
    for pt in points:
        if not isinstance(pt, dict):
            continue
        page = pt.get("source_page") or section.get("source_page")
        if page is None:
            continue
        parts = [
            _get_text(pt.get("pom_code")),
            _get_text(pt.get("point_name")),
            _get_text(pt.get("how_to_measure")),
            _get_text(pt.get("variation")),
        ]
        text = " ".join(p for p in parts if p)
        if not text:
            continue
        temp = {"source_page": page, "raw_text": text}
        _attach_bbox(temp, blocks_by_page)
        if temp.get("bbox_refs"):
            pt["bbox_refs"] = temp["bbox_refs"]


def _attach_bbox_to_components(section: Dict[str, Any], blocks_by_page: Dict[int, List[Dict[str, Any]]]) -> None:
    items = section.get("items") or []
    if not isinstance(items, list):
        return
    for comp in items:
        if not isinstance(comp, dict):
            continue
        page = comp.get("source_page") or section.get("source_page")
        if page is None:
            continue
        parts = [
            _get_text(comp.get("component_name")),
            _get_text(comp.get("component_type")),
            _get_text(comp.get("specifications")),
        ]
        text = " ".join(p for p in parts if p)
        if not text:
            continue
        temp = {"source_page": page, "raw_text": text}
        _attach_bbox(temp, blocks_by_page)
        if temp.get("bbox_refs"):
            comp["bbox_refs"] = temp["bbox_refs"]


def _attach_bbox_to_sections(data: Dict[str, Any], blocks_by_page: Dict[int, List[Dict[str, Any]]]) -> None:
    for sec in data.get("sections", []) or []:
        if not isinstance(sec, dict):
            continue
        _attach_bbox(sec, blocks_by_page)
        if sec.get("section_type") == "BOM":
            _attach_bbox_to_bom(sec, blocks_by_page)
        elif sec.get("section_type") == "Measurement":
            _attach_bbox_to_measurement(sec, blocks_by_page)
        elif sec.get("section_type") == "Components":
            _attach_bbox_to_components(sec, blocks_by_page)


def _attach_bbox_to_notes(data: Dict[str, Any], blocks_by_page: Dict[int, List[Dict[str, Any]]]) -> None:
    for note in data.get("construction_notes", []) or []:
        if isinstance(note, dict):
            _attach_bbox(note, blocks_by_page)
    for opt in data.get("construction_options", []) or []:
        if isinstance(opt, dict):
            _attach_bbox(opt, blocks_by_page)
    for email in data.get("email_notes", []) or []:
        if isinstance(email, dict):
            _attach_bbox(email, blocks_by_page)


def _build_page_images(run_dir: Path, base_dir: Path) -> Dict[str, Dict[str, str]]:
    mapping: Dict[str, Dict[str, str]] = {}
    for img_path in run_dir.glob("*_layout_det_res.png"):
        page = _page_index_from_name(img_path)
        if page is None:
            continue
        rel = os.path.relpath(img_path, base_dir)
        mapping.setdefault(str(page), {})["layout_det"] = rel
    for img_path in run_dir.glob("*_layout_order_res.png"):
        page = _page_index_from_name(img_path)
        if page is None:
            continue
        rel = os.path.relpath(img_path, base_dir)
        mapping.setdefault(str(page), {})["layout_order"] = rel
    return mapping


def attach_bboxes_to_result(
    result_data: Dict[str, Any],
    ocr_output_dir: Path,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    將 OCR BBox 資訊附加到結構化萃取結果中

    Args:
        result_data: 結構化萃取結果 (Dict)
        ocr_output_dir: OCR 輸出目錄
        base_dir: 用於計算相對路徑的基準目錄 (預設為 ocr_output_dir 的父目錄)

    Returns:
        附加了 BBox 的結果字典
    """
    if base_dir is None:
        base_dir = ocr_output_dir.parent

    blocks_by_page = _build_page_blocks(ocr_output_dir)

    _attach_bbox_to_sections(result_data, blocks_by_page)
    _attach_bbox_to_notes(result_data, blocks_by_page)

    result_data["page_images"] = _build_page_images(ocr_output_dir, base_dir)

    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach bbox refs to structured JSON")
    parser.add_argument("--json", required=True, help="Path to result_final.json")
    parser.add_argument("--run_dir", required=True, help="OCR output dir containing *_res.json")
    parser.add_argument("--output", required=True, help="Output json path")
    parser.add_argument("--base_dir", default=".", help="Base dir for relative image paths")
    args = parser.parse_args()

    json_path = Path(args.json)
    run_dir = Path(args.run_dir)
    out_path = Path(args.output)
    base_dir = Path(args.base_dir).resolve()

    data = _load_json(json_path)
    blocks_by_page = _build_page_blocks(run_dir)

    _attach_bbox_to_sections(data, blocks_by_page)
    _attach_bbox_to_notes(data, blocks_by_page)

    data["page_images"] = _build_page_images(run_dir, base_dir)

    _write_json(out_path, data)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
