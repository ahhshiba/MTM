from pathlib import Path
import json
from typing import List, Dict

def parse_res_json(res_json_path: Path) -> Dict:
    with res_json_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def extract_images_from_page(
    *,
    res_json_path: Path,
) -> List[Dict]:
    """
    回傳：
    [
      {
        "image_path": "imgs/xxx.jpg",
        "bbox": [...],
        "order": 0
      }
    ]
    """
    res = parse_res_json(res_json_path)

    blocks = res.get("layout") or res.get("blocks") or []
    images = []

    for idx, block in enumerate(blocks):
        if block.get("type") != "image":
            continue

        images.append({
            "image_path": block["image_path"],
            "bbox": block.get("bbox"),
            "order": idx,
        })

    return images
