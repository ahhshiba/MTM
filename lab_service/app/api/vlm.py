from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import os
import threading
import time
import uuid
from pathlib import Path
from typing import List, Optional, Literal

from google import genai
from google.genai import types
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.db.models import Image, VlmMessage, VlmSession
from app.db.session import SessionLocal


router = APIRouter(prefix="/vlm", tags=["vlm"])
UPLOAD_ROOT = Path(__file__).resolve().parents[1] / "upload_file"
logger = logging.getLogger(__name__)

_client_cache: dict[tuple, genai.Client] = {}
_client_lock = threading.Lock()


class DesignAnalysis(BaseModel):
    img_type: Literal["平面線段設計圖", "成衣實體設計圖", "顏色圖", "其他"]
    description: str


class VlmSessionCreate(BaseModel):
    image_id: str
    aux_image_path: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    prompt: Optional[str] = None
    trace_id: Optional[str] = None


class VlmBatchSessionCreate(BaseModel):
    image_ids: List[str]
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    prompt: Optional[str] = None
    trace_id: Optional[str] = None


class VlmMessageCreate(BaseModel):
    role: str = "user"
    content: str
    trace_id: Optional[str] = None


class VlmMessageOut(BaseModel):
    id: int
    role: str
    content: str
    response_json: Optional[dict] = None
    prompt_tokens: Optional[int] = None
    candidate_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


DEFAULT_DESIGN_GUIDE = (
    "若此為非線段有關的設計圖請直接描述圖片可能的資訊以及若有文字也請連帶OCR後回傳相關文字資訊，若為線段有關的設計圖請按照以下指示進行回復:"
    "請僅依據設計圖中『實際可見的線段、線型與位置』，"
    "以成衣工藝判讀的角度進行說明，不得引入設計圖未顯示的結構或製程。\n\n"
    "請依下列結構分區，以列點方式回答：\n"
    "1. 依線段型態與位置，說明各區域『可判讀出的』縫法工序。\n"
    "2. 對應上述縫法，列出『可合理對應』的縫紉機器類型。\n"
    "3. 不需提及任何線材粗細、針距或尺寸相關資訊，僅聚焦於縫法與工藝特徵。\n"
    "4. 備註：請完整說明圖中所有可見線段區域各自代表的縫合或裝飾用途。\n\n"
    "說明原則：\n"
    "- 僅說明設計圖中線段在成衣工藝圖上的一般性代表意義。\n"
    "- 若某線段無法明確對應特定工序，可如實說明其用途不明或僅能判定為一般縫合線。\n"
    "- 請避免列舉過多替代工法，僅保留最常見、最直接的對應關係。\n"
    "- 不需討論未在圖中顯示的內部結構或加工步驟。\n"
    "- 請優先描述線段呈現的縫線效果或工藝用途，避免直接將其等同於特定機器型號。\n"
    "- 若線段僅顯示為雙線、虛線或壓線效果，請使用中性工藝描述（如：雙針壓線、表面壓線）。\n"
    "- 縫紉機器僅在可合理對應時列出，不得將單一機器描述為唯一或必然選項。"
)

DEFAULT_USER_PROMPT = "請分析此設計圖。"


def _get_image(db, image_id: str) -> Optional[Image]:
    image = db.query(Image).filter(Image.id == image_id).one_or_none()
    if image:
        return image
    try:
        image_id_int = int(image_id)
    except ValueError:
        return None
    return db.query(Image).filter(Image.id == image_id_int).one_or_none()


def _is_under(path: Path, root: Path) -> bool:
    try:
        return Path(os.path.commonpath([path.resolve(), root.resolve()])) == root.resolve()
    except ValueError:
        return False


def _ensure_file(path_str: Optional[str]) -> str:
    if not path_str:
        raise HTTPException(status_code=404, detail="image path missing")
    path = Path(path_str)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="image not found")

    ocr_root = Path(settings.OCR_DATA_ROOT)
    if not (_is_under(path, ocr_root) or _is_under(path, UPLOAD_ROOT)):
        raise HTTPException(status_code=403, detail="image out of allowed roots")
    return str(path)


def _load_image_data(path: str) -> tuple[bytes, str]:
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/jpeg"
    with open(path, "rb") as f:
        data = f.read()
    return data, mime


def _load_image_for_gemini(path: str, trace_id: str) -> tuple[bytes, str, int]:
    data, mime = _load_image_data(path)
    original_size = len(data)
    max_side = max(0, int(settings.GEMINI_MAX_IMAGE_SIDE))
    if max_side <= 0:
        return data, mime, original_size

    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(data)) as img:
            width, height = img.size
            if max(width, height) <= max_side and mime == "image/jpeg":
                return data, mime, original_size

            img.thumbnail((max_side, max_side))
            if img.mode not in {"RGB", "L"}:
                bg = PILImage.new("RGB", img.size, (255, 255, 255))
                if "A" in img.getbands():
                    bg.paste(img, mask=img.getchannel("A"))
                else:
                    bg.paste(img)
                img = bg
            elif img.mode == "L":
                img = img.convert("RGB")

            buf = io.BytesIO()
            quality = min(95, max(50, int(settings.GEMINI_IMAGE_JPEG_QUALITY)))
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            optimized = buf.getvalue()
            if len(optimized) >= original_size:
                return data, mime, original_size

            logger.info(
                "[VLM][%s] image optimized path=%s original_bytes=%d sent_bytes=%d max_side=%d quality=%d",
                trace_id,
                path,
                original_size,
                len(optimized),
                max_side,
                quality,
            )
            return optimized, "image/jpeg", original_size
    except Exception as exc:
        logger.warning("[VLM][%s] image optimization skipped path=%s error=%s", trace_id, path, exc)
        return data, mime, original_size


def _normalize_prompt(user_prompt: Optional[str]) -> str:
    if user_prompt and user_prompt.strip():
        return user_prompt.strip()
    return DEFAULT_USER_PROMPT


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _trace_id(trace_id: Optional[str]) -> str:
    return trace_id or uuid.uuid4().hex[:12]


def _http_options(**kwargs):
    try:
        return types.HttpOptions(**kwargs)
    except TypeError:
        # Older google-genai versions may not support timeout; keep the service bootable.
        kwargs.pop("timeout", None)
        return types.HttpOptions(**kwargs)


def _generate_content_config(model_name: Optional[str] = None, **kwargs):
    thinking_budget = int(settings.GEMINI_THINKING_BUDGET)
    supports_budget = model_name is None or "2.5" in model_name
    if supports_budget and thinking_budget >= 0 and hasattr(types, "ThinkingConfig"):
        kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    try:
        return types.GenerateContentConfig(**kwargs)
    except TypeError:
        kwargs.pop("thinking_config", None)
        return types.GenerateContentConfig(**kwargs)


def _build_client():
    """根據 USE_VERTEX_AI 設定建立 genai.Client"""
    timeout_ms = max(1, int(settings.GEMINI_TIMEOUT_SECONDS)) * 1000
    if settings.USE_VERTEX_AI:
        api_key = settings.VERTEX_API_KEY
        if not api_key:
            raise HTTPException(status_code=500, detail="VERTEX_API_KEY is not configured")

        location = settings.VERTEX_LOCATION or "us-central1"
        base_url = f"https://{location}-aiplatform.googleapis.com/v1/publishers/google"
        cache_key = ("vertex", api_key, location, timeout_ms)
        with _client_lock:
            client = _client_cache.get(cache_key)
            if client is not None:
                return client
            client = genai.Client(
                api_key=api_key,
                http_options=_http_options(
                    timeout=timeout_ms,
                    api_version="",
                    base_url=base_url,
                ),
            )
            _client_cache[cache_key] = client
            return client
    else:
        if not settings.GEMINI_API_KEY:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured")
        cache_key = ("gemini", settings.GEMINI_API_KEY, timeout_ms)
        with _client_lock:
            client = _client_cache.get(cache_key)
            if client is not None:
                return client
            client = genai.Client(
                api_key=settings.GEMINI_API_KEY,
                http_options=_http_options(
                    timeout=timeout_ms,
                ),
            )
            _client_cache[cache_key] = client
            return client


def _generate_analysis(
    *,
    model_name: str,
    system_prompt: Optional[str],
    history: List[VlmMessage],
    prompt: str,
    image_path: str,
    aux_image_path: Optional[str],
) -> tuple[DesignAnalysis, dict, dict]:
    trace_id = _trace_id(None)
    return _generate_analysis_traced(
        model_name=model_name,
        system_prompt=system_prompt,
        history=history,
        prompt=prompt,
        image_path=image_path,
        aux_image_path=aux_image_path,
        trace_id=trace_id,
    )


def _generate_analysis_traced(
    *,
    model_name: str,
    system_prompt: Optional[str],
    history: List[VlmMessage],
    prompt: str,
    image_path: str,
    aux_image_path: Optional[str],
    trace_id: str,
) -> tuple[DesignAnalysis, dict, dict]:
    total_t0 = time.perf_counter()
    prep_t0 = time.perf_counter()
    client = _build_client()
    image_bytes, image_mime, original_image_bytes = _load_image_for_gemini(image_path, trace_id)
    parts = [
        types.Part(text=prompt),
        types.Part(inline_data=types.Blob(mime_type=image_mime, data=image_bytes)),
    ]

    original_aux_bytes = None
    if aux_image_path:
        aux_bytes, aux_mime, original_aux_bytes = _load_image_for_gemini(aux_image_path, trace_id)
        parts.append(types.Part(inline_data=types.Blob(mime_type=aux_mime, data=aux_bytes)))

    max_history = max(0, int(settings.GEMINI_MAX_HISTORY_MESSAGES))
    trimmed_history = history[-max_history:] if max_history else []
    contents = []
    for msg in trimmed_history:
        role = "model" if msg.role == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))

    contents.append(types.Content(role="user", parts=parts))

    config = _generate_content_config(
        model_name=model_name,
        response_mime_type="application/json",
        response_schema=DesignAnalysis.model_json_schema(),
        temperature=settings.GEMINI_TEMPERATURE,
        system_instruction=system_prompt or None,
        max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
    )
    prompt_chars = len(prompt)
    system_chars = len(system_prompt or "")
    history_chars = sum(len(msg.content or "") for msg in trimmed_history)
    prep_ms = _duration_ms(prep_t0)
    logger.info(
        "[VLM][%s] gemini prepare done model=%s history=%d/%d prompt_chars=%d "
        "system_chars=%d history_chars=%d image_bytes=%d "
        "original_image_bytes=%d aux=%s original_aux_bytes=%s "
        "timeout_s=%s max_output_tokens=%s thinking_budget=%s elapsed_ms=%d",
        trace_id,
        model_name,
        len(trimmed_history),
        len(history),
        prompt_chars,
        system_chars,
        history_chars,
        len(image_bytes),
        original_image_bytes,
        bool(aux_image_path),
        original_aux_bytes,
        settings.GEMINI_TIMEOUT_SECONDS,
        settings.GEMINI_MAX_OUTPUT_TOKENS,
        settings.GEMINI_THINKING_BUDGET,
        prep_ms,
    )

    retry_attempts = 3
    retry_delay = 1.0
    last_exc: Optional[Exception] = None
    response = None
    api_ms = 0
    attempts_used = 0
    for attempt in range(retry_attempts + 1):
        attempts_used = attempt + 1
        api_t0 = time.perf_counter()
        try:
            logger.info(
                "[VLM][%s] gemini request start attempt=%d model=%s",
                trace_id,
                attempts_used,
                model_name,
            )
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            api_ms += _duration_ms(api_t0)
            logger.info(
                "[VLM][%s] gemini request done attempt=%d elapsed_ms=%d",
                trace_id,
                attempts_used,
                _duration_ms(api_t0),
            )
            break
        except Exception as exc:
            elapsed_ms = _duration_ms(api_t0)
            api_ms += elapsed_ms
            last_exc = exc
            msg = str(exc)
            is_retryable = ("503" in msg and "UNAVAILABLE" in msg) or "429" in msg
            logger.warning(
                "[VLM][%s] gemini request failed attempt=%d elapsed_ms=%d retryable=%s error=%s",
                trace_id,
                attempts_used,
                elapsed_ms,
                is_retryable,
                exc,
            )
            if is_retryable and attempt < retry_attempts:
                time.sleep(retry_delay * (2 ** attempt))
                continue
            raise HTTPException(status_code=502, detail=f"gemini request failed: {exc}") from exc
    else:
        raise HTTPException(status_code=502, detail=f"gemini request failed: {last_exc}") from last_exc

    parse_t0 = time.perf_counter()
    response_text = getattr(response, "text", None)
    if not response_text:
        candidates = getattr(response, "candidates", None) or []
        if candidates and candidates[0].content and candidates[0].content.parts:
            response_text = getattr(candidates[0].content.parts[0], "text", None)
    
    # Try to validate, if fails due to JSON error, try to repair
    try:
        analysis = DesignAnalysis.model_validate_json(response_text or "{}")
    except Exception as e:
        # Fallback for truncated JSON
        logger.warning(
            "[VLM][%s] JSON parse error: %s. Attempting repair on text length %d",
            trace_id,
            e,
            len(response_text) if response_text else 0,
        )
        try:
            # Simple repair: try closing the JSON string and object if it looks truncated.
            if response_text and "description" in response_text:
                s = response_text.strip()
                if not s.endswith("}"):
                    if not s.endswith('"'):
                        s += '"'
                    s += "}"
                analysis = DesignAnalysis.model_validate_json(s)
            else:
                raise e
        except Exception:
            logger.exception("[VLM][%s] JSON repair failed", trace_id)
            raise e

    usage = getattr(response, "usage_metadata", None)
    usage_payload = {
        "prompt_tokens": getattr(usage, "prompt_token_count", None),
        "candidate_tokens": getattr(usage, "candidates_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }
    timing_payload = {
        "prepare_ms": prep_ms,
        "gemini_api_ms": api_ms,
        "parse_ms": _duration_ms(parse_t0),
        "total_ms": _duration_ms(total_t0),
        "attempts": attempts_used,
    }
    logger.info(
        "[VLM][%s] gemini analysis complete total_ms=%d api_ms=%d parse_ms=%d "
        "tokens=%s",
        trace_id,
        timing_payload["total_ms"],
        timing_payload["gemini_api_ms"],
        timing_payload["parse_ms"],
        usage_payload,
    )
    return analysis, usage_payload, timing_payload


@router.post("/sessions")
def create_session(payload: VlmSessionCreate):
    trace_id = _trace_id(payload.trace_id)
    route_t0 = time.perf_counter()
    logger.info(
        "[VLM][%s] lab /vlm/sessions received image_id=%s model=%s",
        trace_id,
        payload.image_id,
        payload.model or settings.GEMINI_MODEL,
    )
    db = SessionLocal()
    try:
        image = _get_image(db, payload.image_id)
        if image is None or not image.image_path:
            raise HTTPException(status_code=404, detail="image not found")

        session_id = uuid.uuid4().hex
        session = VlmSession(
            id=session_id,
            image_id=str(payload.image_id),
            aux_image_path=payload.aux_image_path,
            model=payload.model or settings.GEMINI_MODEL,
            system_prompt=payload.system_prompt or DEFAULT_DESIGN_GUIDE,
        )
        db.add(session)
        db.commit()

        prompt = _normalize_prompt(payload.prompt)
        image_path = _ensure_file(image.image_path)
        aux_path = _ensure_file(payload.aux_image_path) if payload.aux_image_path else None

        analysis, usage, timing = _generate_analysis_traced(
            model_name=session.model or settings.GEMINI_MODEL,
            system_prompt=session.system_prompt,
            history=[],
            prompt=prompt,
            image_path=image_path,
            aux_image_path=aux_path,
            trace_id=trace_id,
        )

        user_msg = VlmMessage(
            session_id=session_id,
            role="user",
            content=prompt,
        )
        assistant_msg = VlmMessage(
            session_id=session_id,
            role="assistant",
            content=f"[{analysis.img_type}] {analysis.description}",
            response_json=analysis.model_dump(),
            prompt_tokens=usage.get("prompt_tokens"),
            candidate_tokens=usage.get("candidate_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()

        total_ms = _duration_ms(route_t0)
        logger.info(
            "[VLM][%s] lab /vlm/sessions complete session_id=%s total_ms=%d gemini_ms=%d",
            trace_id,
            session_id,
            total_ms,
            timing["gemini_api_ms"],
        )
        return {
            "session_id": session_id,
            "image_id": str(payload.image_id),
            "model": session.model,
            "system_prompt": session.system_prompt,
            "analysis": analysis.model_dump(),
            "token_usage": usage,
            "timing": {"route_ms": total_ms, **timing},
            "messages": [
                VlmMessageOut(
                    id=assistant_msg.id,
                    role=assistant_msg.role,
                    content=assistant_msg.content,
                    response_json=assistant_msg.response_json,
                    prompt_tokens=assistant_msg.prompt_tokens,
                    candidate_tokens=assistant_msg.candidate_tokens,
                    total_tokens=assistant_msg.total_tokens,
                ).model_dump()
            ],
        }
    finally:
        db.close()


def _create_single_session(
    image_id: str,
    model: Optional[str],
    system_prompt: Optional[str],
    prompt: Optional[str],
    trace_id: Optional[str],
) -> dict:
    """
    Internal helper to create a single VLM session.
    Used by batch endpoint for concurrent processing.
    """
    item_trace_id = _trace_id(trace_id)
    item_t0 = time.perf_counter()
    logger.info("[VLM][%s] batch item start image_id=%s", item_trace_id, image_id)
    db = SessionLocal()
    try:
        image = _get_image(db, image_id)
        if image is None or not image.image_path:
            return {"image_id": image_id, "error": "image not found"}

        session_id = uuid.uuid4().hex
        session = VlmSession(
            id=session_id,
            image_id=str(image_id),
            aux_image_path=None,
            model=model or settings.GEMINI_MODEL,
            system_prompt=system_prompt or DEFAULT_DESIGN_GUIDE,
        )
        db.add(session)
        db.commit()

        normalized_prompt = _normalize_prompt(prompt)
        try:
            image_path = _ensure_file(image.image_path)
        except HTTPException as e:
            return {"image_id": image_id, "session_id": session_id, "error": e.detail}

        try:
            analysis, usage, timing = _generate_analysis_traced(
                model_name=session.model or settings.GEMINI_MODEL,
                system_prompt=session.system_prompt,
                history=[],
                prompt=normalized_prompt,
                image_path=image_path,
                aux_image_path=None,
                trace_id=item_trace_id,
            )
        except HTTPException as e:
            return {"image_id": image_id, "session_id": session_id, "error": e.detail}

        user_msg = VlmMessage(
            session_id=session_id,
            role="user",
            content=normalized_prompt,
        )
        assistant_msg = VlmMessage(
            session_id=session_id,
            role="assistant",
            content=f"[{analysis.img_type}] {analysis.description}",
            response_json=analysis.model_dump(),
            prompt_tokens=usage.get("prompt_tokens"),
            candidate_tokens=usage.get("candidate_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()

        total_ms = _duration_ms(item_t0)
        logger.info(
            "[VLM][%s] batch item complete image_id=%s session_id=%s total_ms=%d gemini_ms=%d",
            item_trace_id,
            image_id,
            session_id,
            total_ms,
            timing["gemini_api_ms"],
        )
        return {
            "session_id": session_id,
            "image_id": str(image_id),
            "model": session.model,
            "analysis": analysis.model_dump(),
            "token_usage": usage,
            "timing": {"route_ms": total_ms, **timing},
        }
    except Exception as e:
        logger.exception("[VLM][%s] batch item failed image_id=%s", item_trace_id, image_id)
        return {"image_id": image_id, "error": str(e)}
    finally:
        db.close()


@router.post("/sessions/batch")
async def create_sessions_batch(payload: VlmBatchSessionCreate):
    """
    Create VLM sessions for multiple images concurrently.
    Uses asyncio.gather for parallel processing (Vertex AI 相容).
    """
    trace_id = _trace_id(payload.trace_id)
    batch_t0 = time.perf_counter()
    if not payload.image_ids:
        return {"sessions": [], "errors": []}

    max_concurrent = max(1, int(settings.GEMINI_MAX_CONCURRENCY))
    semaphore = asyncio.Semaphore(max_concurrent)
    logger.info(
        "[VLM][%s] lab /vlm/sessions/batch received total=%d concurrency=%d model=%s",
        trace_id,
        len(payload.image_ids),
        max_concurrent,
        payload.model or settings.GEMINI_MODEL,
    )

    async def _process_one(index: int, image_id: str) -> dict:
        async with semaphore:
            return await asyncio.to_thread(
                _create_single_session,
                image_id,
                payload.model,
                payload.system_prompt,
                payload.prompt,
                f"{trace_id}-{index + 1}",
            )

    tasks = [_process_one(index, img_id) for index, img_id in enumerate(payload.image_ids)]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    errors = []
    for i, res in enumerate(all_results):
        if isinstance(res, Exception):
            errors.append({"image_id": payload.image_ids[i], "error": str(res)})
        elif isinstance(res, dict) and "error" in res:
            errors.append(res)
        else:
            results.append(res)

    total_ms = _duration_ms(batch_t0)
    logger.info(
        "[VLM][%s] lab /vlm/sessions/batch complete total=%d success=%d errors=%d "
        "concurrency=%d total_ms=%d",
        trace_id,
        len(payload.image_ids),
        len(results),
        len(errors),
        max_concurrent,
        total_ms,
    )
    return {
        "sessions": results,
        "errors": errors,
        "timing": {
            "route_ms": total_ms,
            "total": len(payload.image_ids),
            "success": len(results),
            "errors": len(errors),
            "concurrency": max_concurrent,
        },
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    db = SessionLocal()
    try:
        session = db.query(VlmSession).filter(VlmSession.id == session_id).one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")

        messages = (
            db.query(VlmMessage)
            .filter(VlmMessage.session_id == session_id)
            .order_by(VlmMessage.id)
            .all()
        )
        return {
            "session_id": session.id,
            "image_id": session.image_id,
            "model": session.model,
            "system_prompt": session.system_prompt,
            "messages": [
                VlmMessageOut(
                    id=msg.id,
                    role=msg.role,
                    content=msg.content,
                    response_json=msg.response_json,
                    prompt_tokens=msg.prompt_tokens,
                    candidate_tokens=msg.candidate_tokens,
                    total_tokens=msg.total_tokens,
                ).model_dump()
                for msg in messages
            ],
        }
    finally:
        db.close()


@router.post("/sessions/{session_id}/messages")
def post_message(session_id: str, payload: VlmMessageCreate):
    trace_id = _trace_id(payload.trace_id)
    route_t0 = time.perf_counter()
    logger.info(
        "[VLM][%s] lab /vlm/sessions/%s/messages received role=%s",
        trace_id,
        session_id,
        payload.role,
    )
    if payload.role not in {"user", "assistant"}:
        raise HTTPException(status_code=400, detail="role must be user or assistant")

    db = SessionLocal()
    try:
        session = db.query(VlmSession).filter(VlmSession.id == session_id).one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")

        image = _get_image(db, session.image_id)
        if image is None or not image.image_path:
            raise HTTPException(status_code=404, detail="image not found")

        user_msg = VlmMessage(
            session_id=session_id,
            role=payload.role,
            content=payload.content,
        )
        db.add(user_msg)
        db.commit()
        db.refresh(user_msg)

        assistant_msg = None
        analysis_payload = None
        usage_payload = None
        timing_payload = None
        if payload.role == "user":
            history = (
                db.query(VlmMessage)
                .filter(VlmMessage.session_id == session_id)
                .order_by(VlmMessage.id)
                .all()
            )
            history = history[:-1] if history else []

            image_path = _ensure_file(image.image_path)
            aux_path = _ensure_file(session.aux_image_path) if session.aux_image_path else None

            analysis, usage, timing_payload = _generate_analysis_traced(
                model_name=session.model or settings.GEMINI_MODEL,
                system_prompt=session.system_prompt,
                history=history,
                prompt=payload.content,
                image_path=image_path,
                aux_image_path=aux_path,
                trace_id=trace_id,
            )
            analysis_payload = analysis.model_dump()
            usage_payload = usage

            assistant_msg = VlmMessage(
                session_id=session_id,
                role="assistant",
                content=f"[{analysis.img_type}] {analysis.description}",
                response_json=analysis_payload,
                prompt_tokens=usage.get("prompt_tokens"),
                candidate_tokens=usage.get("candidate_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
            db.add(assistant_msg)
            db.commit()

        messages = (
            db.query(VlmMessage)
            .filter(VlmMessage.session_id == session_id)
            .order_by(VlmMessage.id)
            .all()
        )
        total_ms = _duration_ms(route_t0)
        logger.info(
            "[VLM][%s] lab /vlm/sessions/%s/messages complete total_ms=%d gemini_ms=%s",
            trace_id,
            session_id,
            total_ms,
            timing_payload["gemini_api_ms"] if timing_payload else None,
        )
        return {
            "session_id": session_id,
            "analysis": analysis_payload,
            "token_usage": usage_payload,
            "timing": {"route_ms": total_ms, **timing_payload} if timing_payload else {"route_ms": total_ms},
            "messages": [
                VlmMessageOut(
                    id=msg.id,
                    role=msg.role,
                    content=msg.content,
                    response_json=msg.response_json,
                    prompt_tokens=msg.prompt_tokens,
                    candidate_tokens=msg.candidate_tokens,
                    total_tokens=msg.total_tokens,
                ).model_dump()
                for msg in messages
            ],
        }
    finally:
        db.close()
