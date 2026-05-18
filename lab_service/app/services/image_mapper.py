# app/services/image_mapper.py
from __future__ import annotations

from pathlib import Path
from typing import List, Optional


def match_image_by_bbox(imgs_dir: Path, bbox: List[int]) -> Optional[Path]:
    """
    你的 imgs 檔名格式類似：
      img_in_image_box_32_160_312_571.jpg
      img_in_chart_box_502_56_992_214.jpg

    由於 res.json 的 image block 沒有 image_path，我們用 bbox suffix 反查：
      _x1_y1_x2_y2
    """
    if not imgs_dir.exists():
        return None

    x1, y1, x2, y2 = bbox
    suffix = f"_{x1}_{y1}_{x2}_{y2}"

    # 常見副檔名
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        for p in imgs_dir.glob(f"*{ext}"):
            if suffix in p.name:
                return p

    # 兜底：不限定副檔名
    for p in imgs_dir.iterdir():
        if p.is_file() and suffix in p.name:
            return p

    return None
