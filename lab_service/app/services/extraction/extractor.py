# app/services/extraction/extractor.py
"""TechPack 結構化萃取服務"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.db.models import (
    ExtractionRun, ExtractionLLMCall, OCRRun, PageOCRArtifact, Image,
    VlmSession, VlmMessage, Page
)
from app.db.session import SessionLocal
from sqlalchemy.orm import Session


from app.redis.state import set_job_state
from .engine import extract_techpack, ExtractionContext, TokenTracker, LogWriter
from .llm import GeminiClient
from .prompts import IMAGE_CLASSIFICATION_PROMPT
from .schemas import LLMImageClassification


class TechPackExtractor:
    """TechPack 結構化萃取器 - 服務層包裝"""

    def __init__(
        self,
        ocr_run_id: int,
        document_id: str,
        mode: str = "auto",
        model: str = "gemini-2.5-flash",
    ):
        self.ocr_run_id = ocr_run_id
        self.document_id = document_id
        self.mode = mode
        self.model = model
        self.extraction_run_id: Optional[int] = None
        
        # 輸出目錄
        self.output_dir: Optional[Path] = None
        self.ocr_output_dir: Optional[Path] = None

    def _report_progress(self, progress: float, message: str) -> None:
        """回報進度到 Redis"""
        if not self.extraction_run_id:
            print("[Warning] _report_progress called but extraction_run_id is None")
            return
            
        try:
            # 必須使用與 api/extraction.py 相同的 key 格式
            key = f"extraction:{self.extraction_run_id}"
            
            # Debug log
            print(f"[Extractor] Report Progress: {progress}% - {message} (Key: {key})")

            # Use 0-1 range for progress to match frontend expectation
            # Assume engine always uses 0-100 scale based on logs.
            # If progress is 0-100, divide by 100.
            # But handle 0-1 case just in case engine sends 0.5 for 50%.
            # Given logs show 70 for 70%, we assume > 1 is percent.
            # IF progress is exactly 1.0, it's ambiguous, but usually engine starts > 0.
            if progress > 1.0:
                 normalized_progress = progress / 100.0
            else:
                 normalized_progress = progress

            set_job_state(key, {
                "status": "running",
                "extraction_run_id": self.extraction_run_id,
                "ocr_run_id": self.ocr_run_id,
                "progress": round(normalized_progress, 4),
                "message": message,
                "updated_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            print(f"[Warning] Failed to update progress: {e}")
            import traceback
            traceback.print_exc()

    def _get_ocr_run(self, db) -> Optional[OCRRun]:
        """取得 OCR Run 資訊"""
        return db.query(OCRRun).filter(OCRRun.id == self.ocr_run_id).first()

    def _get_page_context(self, db, image_id: int) -> str:
        """取得圖片所屬頁面的 OCR 文字內容"""
        image = db.query(Image).filter(Image.id == image_id).first()
        if not image or not image.page_id:
            return ""
        
        artifact = db.query(PageOCRArtifact).filter(
            PageOCRArtifact.page_id == image.page_id
        ).first()
        
        if artifact and artifact.result_md_path:
            try:
                md_path = Path(artifact.result_md_path)
                if md_path.exists():
                    return md_path.read_text(encoding="utf-8")[:3000]
            except Exception:
                pass
        return ""

    def _get_vlm_classifications(self, db) -> List[Dict[str, Any]]:
        """
        從 VLM Chat 取得已確認的圖片分類結果
        
        Returns:
            List of image classification results with:
            - image_id
            - image_path
            - img_type (分類類型)
            - description (分析描述)
            - is_finalized (是否已確認)
        """
        results = []
        
        # 取得 OCR Run 的所有圖片
        images = db.query(Image).filter(
            Image.ocr_run_id == self.ocr_run_id,
        ).all()
        
        for image in images:
            image_id_str = str(image.id)
            
            # 找出對應的 VLM Session
            session = db.query(VlmSession).filter(
                VlmSession.image_id == image_id_str
            ).first()
            
            if not session:
                # 用戶要求只使用 VLM Chat 的結果，若無 session 則跳過
                continue
            
            # 取得最後一個 assistant 回應
            last_response = db.query(VlmMessage).filter(
                VlmMessage.session_id == session.id,
                VlmMessage.role == "assistant"
            ).order_by(VlmMessage.id.desc()).first()
            
            if last_response and last_response.response_json:
                response_data = last_response.response_json
                results.append({
                    "image_id": image_id_str,
                    "image_path": image.image_path,
                    "img_type": response_data.get("img_type", "其他"),
                    "description": response_data.get("description", ""),
                    "is_finalized": session.finalized,
                })
            else:
                results.append({
                    "image_id": image_id_str,
                    "image_path": image.image_path,
                    "img_type": "其他",
                    "description": "",
                    "is_finalized": session.finalized,
                })
        
        return results

    def create_extraction_run(self) -> int:
        """建立萃取執行記錄"""
        db = SessionLocal()
        try:
            run = ExtractionRun(
                ocr_run_id=self.ocr_run_id,
                document_id=self.document_id,
                status="pending",
                model=self.model,
                mode=self.mode,
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            self.extraction_run_id = run.id
            return run.id
        finally:
            db.close()

    async def _classify_images_async(self, db, async_client=None, report_progress=True) -> List[Dict[str, Any]]:
        """
        非同步版圖片分類 — 用 AsyncGeminiClient + asyncio.gather 真正並行。
        比原本的 ThreadPoolExecutor(5) 更快，因為所有 API 呼叫都非同步並發。
        """
        import asyncio
        from .llm import AsyncGeminiClient

        print("[Extractor] Fetching images from DB (async mode)...")

        images = db.query(Image).filter(Image.ocr_run_id == self.ocr_run_id).all()
        print(f"[Extractor] Found {len(images)} OCR images")

        total = len(images)
        if total == 0:
            return []

        img_datas = [(str(img.id), str(img.image_path)) for img in images]
        completed_count = 0

        async def process_single_image(img_id: str, img_path_str: str) -> Dict[str, Any]:
            nonlocal completed_count
            description = ""
            img_type = "其他"
            feature_tags = []

            if async_client:
                try:
                    result, usage = await async_client.generate_structured(
                        IMAGE_CLASSIFICATION_PROMPT,
                        LLMImageClassification,
                        image_path=img_path_str,
                    )
                    description = result.description_zh if result.description_zh else result.description_original
                    img_type = result.image_type
                    feature_tags = result.feature_tags
                except Exception as e:
                    print(f"[Warning] Failed to classify image {img_id}: {e}")

            completed_count += 1
            if report_progress:
                current_prog = 5 + (completed_count / total) * 10
                self._report_progress(current_prog, f"正在分析圖片 ({completed_count}/{total})...")

            return {
                "image_id": img_id,
                "image_path": img_path_str,
                "img_type": img_type,
                "description": description,
                "feature_tags": feature_tags,
                "is_finalized": True,
            }

        # 全部並發，由 AsyncGeminiClient 的 semaphore 控制上限
        tasks = [process_single_image(img_id, img_path) for img_id, img_path in img_datas]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 過濾掉 exception
        valid = []
        for r in results:
            if isinstance(r, Exception):
                print(f"[Error] Image classify failed: {r}")
            else:
                valid.append(r)

        return valid

    def _classify_images_from_db(self, db, gemini_client=None, report_progress=True) -> List[Dict[str, Any]]:
        """同步版 fallback（保留向後相容）"""
        import concurrent.futures

        print("[Extractor] Fetching images from DB (sync fallback)...")
        images = db.query(Image).filter(Image.ocr_run_id == self.ocr_run_id).all()
        print(f"[Extractor] Found {len(images)} OCR images")

        total = len(images)
        if total == 0:
            return []

        img_datas = [(str(img.id), str(img.image_path)) for img in images]

        def process_single_image(data):
            img_id, img_path_str = data
            description = ""
            img_type = "其他"
            feature_tags = []
            if gemini_client:
                try:
                    result, usage = gemini_client.generate_structured(
                        IMAGE_CLASSIFICATION_PROMPT, LLMImageClassification,
                        image_path=img_path_str,
                    )
                    description = result.description_zh if result.description_zh else result.description_original
                    img_type = result.image_type
                    feature_tags = result.feature_tags
                except Exception as e:
                    print(f"[Warning] Failed to classify image {img_id}: {e}")
            return {
                "image_id": img_id, "image_path": img_path_str,
                "img_type": img_type, "description": description,
                "feature_tags": feature_tags, "is_finalized": True,
            }

        results = []
        completed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_data = {executor.submit(process_single_image, d): d for d in img_datas}
            for future in concurrent.futures.as_completed(future_to_data):
                completed_count += 1
                if report_progress:
                    self._report_progress(5 + (completed_count / total) * 10,
                                          f"正在分析圖片 ({completed_count}/{total})...")
                try:
                    results.append(future.result())
                except Exception as e:
                    print(f"[Error] Thread execution failed: {e}")
        return results

    def update_status(self, status: str, error_message: Optional[str] = None):
        """更新萃取狀態"""
        db = SessionLocal()
        try:
            run = db.query(ExtractionRun).filter(
                ExtractionRun.id == self.extraction_run_id
            ).first()
            if run:
                run.status = status
                if error_message:
                    run.error_message = error_message
                if status == "running":
                    run.started_at = datetime.utcnow()
                elif status in ("completed", "failed"):
                    run.finished_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()

    def log_llm_call(
        self,
        call_type: str,
        prompt: str,
        response: str,
        image_path: Optional[str] = None,
        prompt_tokens: int = 0,
        candidate_tokens: int = 0,
        total_tokens: int = 0,
        duration_ms: int = 0,
    ):
        """記錄 LLM 呼叫"""
        if not self.extraction_run_id:
            return
        
        db = SessionLocal()
        try:
            call = ExtractionLLMCall(
                extraction_run_id=self.extraction_run_id,
                call_type=call_type,
                prompt=prompt[:5000] if prompt else None,  # 限制長度
                response=response[:10000] if response else None,
                image_path=image_path,
                prompt_tokens=prompt_tokens,
                candidate_tokens=candidate_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
            )
            db.add(call)
            db.commit()
            
            # 更新總 token 統計
            run = db.query(ExtractionRun).filter(
                ExtractionRun.id == self.extraction_run_id
            ).first()
            if run:
                run.total_prompt_tokens = (run.total_prompt_tokens or 0) + prompt_tokens
                run.total_candidate_tokens = (run.total_candidate_tokens or 0) + candidate_tokens
                run.total_tokens = (run.total_tokens or 0) + total_tokens
                db.commit()
        finally:
            db.close()

    def update_result_paths(
        self,
        raw_result_path: Optional[str] = None,
        structured_result_path: Optional[str] = None,
        bbox_result_path: Optional[str] = None,
    ):
        """更新結果路徑"""
        db = SessionLocal()
        try:
            run = db.query(ExtractionRun).filter(
                ExtractionRun.id == self.extraction_run_id
            ).first()
            if run:
                if raw_result_path:
                    run.raw_result_path = raw_result_path
                if structured_result_path:
                    run.structured_result_path = structured_result_path
                if bbox_result_path:
                    run.bbox_result_path = bbox_result_path
                db.commit()
        finally:
            db.close()

    def run_extraction(self) -> Dict[str, Any]:
        """
        執行結構化萃取
        
        Returns:
            包含萃取結果和狀態的字典
        """
        db = SessionLocal()
        try:
            # 取得 OCR 輸出目錄
            ocr_run = self._get_ocr_run(db)
            if not ocr_run:
                raise ValueError(f"OCR Run {self.ocr_run_id} not found")
            
            self.ocr_output_dir = Path(ocr_run.output_dir_path)
            if not self.ocr_output_dir.exists():
                raise FileNotFoundError(f"OCR output dir not found: {self.ocr_output_dir}")
            
            # 設定輸出目錄
            # Modify: Store extraction INSIDE the OCR output folder to avoid overwriting global extraction folder
            # Old: self.output_dir = self.ocr_output_dir.parent / "extraction"
            self.output_dir = self.ocr_output_dir / "extraction"
            self.output_dir.mkdir(exist_ok=True)
            
            # 更新狀態為 running
            self.update_status("running")
            
            # 呼叫萃取引擎
            from .engine import extract_techpack, ExtractionContext, TokenTracker, LogWriter
            from .llm import GeminiClient, AsyncGeminiClient
            from .prompts import IMAGE_CLASSIFICATION_PROMPT
            from .schemas import LLMImageClassification
            
            api_key = settings.GEMINI_API_KEY
            use_vertex = settings.USE_VERTEX_AI
            if use_vertex and settings.VERTEX_API_KEY:
                api_key = settings.VERTEX_API_KEY
            log_path = self.output_dir / "extraction.log"
            
            # 建立 context
            gemini_client = None
            async_client = None
            use_llm = False
            if api_key:
                try:
                    gemini_client = GeminiClient(api_key, model=self.model, use_vertex=use_vertex)
                    async_client = AsyncGeminiClient(api_key, model=self.model, use_vertex=use_vertex)
                    use_llm = True
                except Exception as e:
                    print(f"[Warning] Gemini 初始化失敗: {e}")
            
            ctx = ExtractionContext(
                run_dir=self.ocr_output_dir,
                api_key=api_key,
                gemini_client=gemini_client,
                async_gemini_client=async_client,
                use_llm=use_llm,
                config=None,
                token_tracker=TokenTracker(),
                log_writer=LogWriter(log_path),
                progress_callback=self._report_progress,
            )
            
            print(f"[Extraction] Starting run_extraction logic. Mode: {self.mode}")

            # 1. 嘗試從 VLM Session (Developer Mode) 獲取
            vlm_classifications = self._get_vlm_classifications(db)
            
            image_provider = None
            
            # 2. 如果沒有 VLM 結果 (User Mode 或 Auto Mode 跳過 Chat)，設定並行 callback
            if not vlm_classifications:
                 print(f"[Extraction] No VLM results (User Mode). Setting up Async Image Provider...")

                 async def image_provider_callback():
                        """Async callback — 用 AsyncGeminiClient 真正並行分類所有圖片"""
                        print("[Extractor] Async Image Provider Callback triggered.")
                        inner_db = SessionLocal()
                        try:
                            return await self._classify_images_async(
                                inner_db, async_client, report_progress=False
                            )
                        except Exception as e:
                            print(f"[Error] Async Image Provider Callback Failed: {e}")
                            import traceback
                            traceback.print_exc()
                            return []
                        finally:
                            inner_db.close()

                 image_provider = image_provider_callback
            
            print(f"[Extraction] Ready to extract. Image parallelism enabled: {image_provider is not None}")
            
            import time as _time
            _ext_start = _time.time()
            
            # 執行萃取 - 傳入已分類的圖片 OR Provider Callback
            result = extract_techpack(
                run_dir=str(self.ocr_output_dir),
                api_key=api_key,
                clustered_results=None,
                config=None,
                ctx=ctx,
                pre_classified_images=vlm_classifications,
                image_provider_callback=image_provider,
                use_vertex=use_vertex,
            )
            
            _ext_elapsed = _time.time() - _ext_start
            print(f"[Timing] extract_techpack 完成: {_ext_elapsed:.2f}s")
            print(f"[DEBUG] 開始儲存結果...")
            
            # 儲存原始結果
            raw_path = self.output_dir / "result_raw.json"
            print(f"[DEBUG] 正在序列化結果 (model_dump)...")
            raw_data = result.model_dump()
            print(f"[DEBUG] 序列化完成，寫入 {raw_path}...")
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, ensure_ascii=False, indent=2)
            print(f"[DEBUG] result_raw.json 寫入完成")
            
            # 執行 bbox 附加
            from .bbox_attacher import main as attach_bboxes_main
            bbox_path = self.output_dir / "result_final_bbox.json"
            
            # 呼叫 attach_bboxes
            from .bbox_attacher import (
                _load_json, _write_json, _build_page_blocks, 
                _attach_bbox_to_sections, _attach_bbox_to_notes, _build_page_images
            )
            
            print(f"[DEBUG] 開始 _build_page_blocks...")
            data = result.model_dump()
            blocks_by_page = _build_page_blocks(self.ocr_output_dir)
            print(f"[DEBUG] _build_page_blocks 完成，共 {len(blocks_by_page)} 頁")
            
            print(f"[DEBUG] 開始 _attach_bbox_to_sections...")
            _attach_bbox_to_sections(data, blocks_by_page)
            print(f"[DEBUG] _attach_bbox_to_sections 完成")
            
            print(f"[DEBUG] 開始 _attach_bbox_to_notes...")
            _attach_bbox_to_notes(data, blocks_by_page)
            print(f"[DEBUG] _attach_bbox_to_notes 完成")
            
            print(f"[DEBUG] 開始 _build_page_images...")
            page_images_dict = _build_page_images(self.ocr_output_dir, self.ocr_output_dir.parent)
            
            # 轉換為前端期望的陣列格式 [{page_id, page_index, ...}]
            # 並從資料庫取得真正的 page_id (使用 document_id 查詢)
            pages = db.query(Page).filter(Page.document_id == self.document_id).order_by(Page.page_no).all()
            page_images_list = []
            for page in pages:
                page_idx = str(page.page_no - 1)  # page_no 是 1-indexed
                img_info = page_images_dict.get(page_idx, {})
                page_images_list.append({
                    "page_id": page.id,
                    "page_index": page.page_no - 1,
                    "page_no": page.page_no,
                    "layout_det": img_info.get("layout_det"),
                    "layout_order": img_info.get("layout_order"),
                })
            data["page_images"] = page_images_list
            print(f"[DEBUG] _build_page_images 完成, 共 {len(page_images_list)} 頁")
            _save_elapsed = _time.time() - _ext_start - _ext_elapsed
            print(f"[Timing] 結果儲存+BBox: {_save_elapsed:.2f}s")
            print(f"[Timing] 總耗時: {_time.time() - _ext_start:.2f}s")
            
            print(f"[DEBUG] 寫入 {bbox_path}...")
            _write_json(bbox_path, data)
            print(f"[DEBUG] result_final_bbox.json 寫入完成")
            
            # 更新結果路徑
            self.update_result_paths(
                raw_result_path=str(raw_path),
                structured_result_path=str(raw_path),
                bbox_result_path=str(bbox_path),
            )
            
            # 記錄 token 統計
            if ctx.token_tracker:
                summary = ctx.token_tracker.summary()
                for step, totals in summary.items():
                    self.log_llm_call(
                        call_type=step,
                        prompt="[aggregated]",
                        response="[aggregated]",
                        prompt_tokens=totals.get("prompt_tokens", 0),
                        candidate_tokens=totals.get("candidate_tokens", 0),
                        total_tokens=totals.get("total_tokens", 0),
                    )
            
            # 關閉 log
            if ctx.log_writer:
                ctx.log_writer.close()
            
            # 更新狀態
            self.update_status("completed")
            
            # 儲存 Token 用量到資料庫
            try:
                summary = result.extraction_summary or {}
                db_token = SessionLocal()
                run_record = db_token.query(ExtractionRun).filter(
                    ExtractionRun.id == self.extraction_run_id
                ).first()
                if run_record:
                    run_record.total_tokens = summary.get("llm_tokens_used", 0)
                    run_record.total_prompt_tokens = summary.get("llm_input_tokens", 0)
                    run_record.total_candidate_tokens = summary.get("llm_output_tokens", 0)
                    db_token.commit()
                    print(f"[Extraction] Saved token usage: {run_record.total_tokens} total tokens")
                db_token.close()
            except Exception as token_err:
                print(f"[Warning] Failed to save token usage: {token_err}")
            
            return {
                "success": True,
                "extraction_run_id": self.extraction_run_id,
                "raw_result_path": str(raw_path),
                "bbox_result_path": str(bbox_path),
                "summary": result.extraction_summary,
            }
            
        except Exception as e:
            import traceback
            print(f"[Extraction Error] {str(e)}")
            print(traceback.format_exc())
            self.update_status("failed", str(e))
            return {
                "success": False,
                "extraction_run_id": self.extraction_run_id,
                "error": str(e),
            }
        finally:
            db.close()


def run_extraction_task(
    ocr_run_id: int,
    document_id: str,
    mode: str = "auto",
    model: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """
    執行結構化萃取任務 (可用於背景任務)
    
    Args:
        ocr_run_id: OCR Run ID
        document_id: Document ID
        mode: 萃取模式 (auto/developer)
        model: LLM 模型名稱
    
    Returns:
        萃取結果字典
    """
    extractor = TechPackExtractor(
        ocr_run_id=ocr_run_id,
        document_id=document_id,
        mode=mode,
        model=model,
    )
    
    # 建立執行記錄
    extraction_run_id = extractor.create_extraction_run()
    
    # 執行萃取
    result = extractor.run_extraction()
    
    return result
