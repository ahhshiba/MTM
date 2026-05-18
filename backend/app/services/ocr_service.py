import subprocess
from pathlib import Path
from app.core.config import settings

def run_paddleocr_doc_parser(
    pdf_path: str,
    output_dir: str,
):
    """
    在實驗室電腦執行 PaddleOCR-VL doc_parser
    注意：這是「本機透過 SSH / RPC / 任務派送」的抽象層
    目前假設你本機可以直接呼叫該指令（例如透過 shared FS / SSH）
    """

    cmd = [
        "paddleocr",
        "doc_parser",
        "-i", pdf_path,
        "--vl_rec_backend", "vllm-server",
        "--vl_rec_server_url", settings.paddle_ocr_vllm_url,
        "--device", "gpu",
        "--save_path", output_dir,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"PaddleOCR failed:\n{result.stderr}"
        )

    return result.stdout
