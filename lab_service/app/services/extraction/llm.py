# app/services/extraction/llm.py
"""
LLM Client Integration
支援 AI Studio 和 Vertex AI，同步 + 非同步雙模式
"""
import asyncio
import io
import logging
import time
import mimetypes
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings


logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def load_image_data(path: str) -> Tuple[bytes, str]:
    """載入圖片資料"""
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/jpeg"
    with open(path, "rb") as f:
        data = f.read()
    max_side = max(0, int(settings.GEMINI_MAX_IMAGE_SIDE))
    if max_side <= 0:
        return data, mime

    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(data)) as img:
            if max(img.size) <= max_side and mime == "image/jpeg":
                return data, mime

            original_size = len(data)
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
            if len(optimized) < original_size:
                logger.info(
                    "[Gemini] image optimized path=%s original_bytes=%d sent_bytes=%d max_side=%d quality=%d",
                    path,
                    original_size,
                    len(optimized),
                    max_side,
                    quality,
                )
                return optimized, "image/jpeg"
    except Exception as exc:
        logger.warning("[Gemini] image optimization skipped path=%s error=%s", path, exc)

    return data, mime


# ---- Schema 快取，避免每次 API 呼叫都重複生成 ----
_schema_cache: Dict[type, dict] = {}


def _get_json_schema(schema: type) -> dict:
    """快取 pydantic model 的 JSON schema"""
    if schema not in _schema_cache:
        _schema_cache[schema] = schema.model_json_schema()
    return _schema_cache[schema]


# ---- Gemini Client 快取，避免每次 extraction 都重建 ----
_client_cache: Dict[str, "genai.Client"] = {}
_client_lock = threading.Lock()


def _duration_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _http_options(**kwargs):
    try:
        return types.HttpOptions(**kwargs)
    except TypeError:
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


def _build_client(
    api_key: str,
    use_vertex: bool = False,
) -> "genai.Client":
    """
    根據設定建立 genai.Client (含快取，相同 api_key+use_vertex 複用同一實例)
    - AI Studio:  genai.Client(api_key=...)
    - Vertex AI:  透過 base_url 指向 {location}-aiplatform.googleapis.com/...
    """
    timeout_ms = max(1, int(settings.GEMINI_TIMEOUT_SECONDS)) * 1000
    cache_key = f"{api_key}:{use_vertex}:{settings.VERTEX_LOCATION}:{timeout_ms}"
    with _client_lock:
        if cache_key in _client_cache:
            return _client_cache[cache_key]

    if use_vertex:
        location = settings.VERTEX_LOCATION or "us-central1"
        base_url = f"https://{location}-aiplatform.googleapis.com/v1/publishers/google"
        client = genai.Client(
            api_key=api_key,
            http_options=_http_options(
                timeout=timeout_ms,
                api_version="",
                base_url=base_url,
            ),
        )
    else:
        client = genai.Client(
            api_key=api_key,
            http_options=_http_options(timeout=timeout_ms),
        )

    with _client_lock:
        _client_cache[cache_key] = client
    return client


# ==============================================================================
# 同步版 Client (保留向後相容，vlm.py sync endpoints 可選用)
# ==============================================================================
class GeminiClient:
    """Gemini API 客戶端 (同步版)"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.2,
        use_vertex: bool = False,
    ):
        if not HAS_GENAI:
            raise RuntimeError("google-genai not installed")

        self.client = _build_client(api_key, use_vertex=use_vertex)
        self.model = model
        self.temperature = temperature
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.candidate_tokens = 0
        self.cached_tokens = 0
        self._lock = threading.Lock()

    def _update_tokens(self, usage: Dict[str, int]):
        with self._lock:
            self.total_tokens += usage.get("total_tokens", 0)
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.candidate_tokens += usage.get("candidate_tokens", 0)
            self.cached_tokens += usage.get("cached_tokens", 0)

    def generate_structured(
        self,
        prompt: str,
        schema: type,
        image_path: Optional[str] = None,
        max_retries: int = 3,
    ) -> Tuple[Any, Dict[str, int]]:
        """生成結構化輸出"""
        parts = [types.Part(text=prompt)]

        if image_path and Path(image_path).exists():
            img_data, img_mime = load_image_data(image_path)
            parts.append(types.Part(
                inline_data=types.Blob(mime_type=img_mime, data=img_data)
            ))

        contents = [types.Content(role="user", parts=parts)]

        config = _generate_content_config(
            model_name=self.model,
            response_mime_type="application/json",
            response_schema=_get_json_schema(schema),
            temperature=self.temperature,
        )

        last_exc = None
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            try:
                logger.info(
                    "[Gemini] structured request start model=%s attempt=%d prompt_chars=%d image=%s timeout_s=%s thinking_budget=%s",
                    self.model,
                    attempt + 1,
                    len(prompt),
                    bool(image_path),
                    settings.GEMINI_TIMEOUT_SECONDS,
                    settings.GEMINI_THINKING_BUDGET,
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                logger.info(
                    "[Gemini] structured request done model=%s attempt=%d elapsed_ms=%d",
                    self.model,
                    attempt + 1,
                    _duration_ms(t0),
                )
                break
            except Exception as e:
                last_exc = e
                msg = str(e)
                logger.warning(
                    "[Gemini] structured request failed model=%s attempt=%d elapsed_ms=%d error=%s",
                    self.model,
                    attempt + 1,
                    _duration_ms(t0),
                    e,
                )
                if "503" in msg or "429" in msg:
                    time.sleep(2 ** attempt)
                    continue
                raise
        else:
            raise RuntimeError(f"Gemini request failed after {max_retries} retries: {last_exc}")

        # Parse response
        response_text = getattr(response, "text", None)
        if not response_text:
            candidates = getattr(response, "candidates", None) or []
            if candidates and candidates[0].content and candidates[0].content.parts:
                response_text = getattr(candidates[0].content.parts[0], "text", None)

        result = schema.model_validate_json(response_text or "{}")

        # Token usage
        usage = getattr(response, "usage_metadata", None)
        prompt_to = getattr(usage, "prompt_token_count", 0) or 0
        cand_to = getattr(usage, "candidates_token_count", 0) or 0
        cache_to = getattr(usage, "cached_content_token_count", 0) or 0
        token_usage = {
            "prompt_tokens": prompt_to,
            "candidate_tokens": cand_to,
            "cached_tokens": cache_to,
            "total_tokens": prompt_to + cand_to + cache_to,
        }

        self._update_tokens(token_usage)

        return result, token_usage

    def generate_text(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        max_retries: int = 3,
    ) -> Tuple[str, Dict[str, int]]:
        """生成文字輸出"""
        parts = [types.Part(text=prompt)]

        if image_path and Path(image_path).exists():
            img_data, img_mime = load_image_data(image_path)
            parts.append(types.Part(
                inline_data=types.Blob(mime_type=img_mime, data=img_data)
            ))

        contents = [types.Content(role="user", parts=parts)]

        config = _generate_content_config(
            model_name=self.model,
            temperature=self.temperature,
        )

        last_exc = None
        for attempt in range(max_retries):
            t0 = time.perf_counter()
            try:
                logger.info(
                    "[Gemini] text request start model=%s attempt=%d prompt_chars=%d image=%s timeout_s=%s thinking_budget=%s",
                    self.model,
                    attempt + 1,
                    len(prompt),
                    bool(image_path),
                    settings.GEMINI_TIMEOUT_SECONDS,
                    settings.GEMINI_THINKING_BUDGET,
                )
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                logger.info(
                    "[Gemini] text request done model=%s attempt=%d elapsed_ms=%d",
                    self.model,
                    attempt + 1,
                    _duration_ms(t0),
                )
                break
            except Exception as e:
                last_exc = e
                msg = str(e)
                logger.warning(
                    "[Gemini] text request failed model=%s attempt=%d elapsed_ms=%d error=%s",
                    self.model,
                    attempt + 1,
                    _duration_ms(t0),
                    e,
                )
                if "503" in msg or "429" in msg:
                    time.sleep(2 ** attempt)
                    continue
                raise
        else:
            raise RuntimeError(f"Gemini request failed: {last_exc}")

        response_text = getattr(response, "text", "") or ""

        usage = getattr(response, "usage_metadata", None)
        prompt_to = getattr(usage, "prompt_token_count", 0) or 0
        cand_to = getattr(usage, "candidates_token_count", 0) or 0
        cache_to = getattr(usage, "cached_content_token_count", 0) or 0
        token_usage = {
            "prompt_tokens": prompt_to,
            "candidate_tokens": cand_to,
            "cached_tokens": cache_to,
            "total_tokens": prompt_to + cand_to + cache_to,
        }
        self._update_tokens(token_usage)

        return response_text, token_usage


# ==============================================================================
# 非同步版 Client (asyncio)
# ==============================================================================
class AsyncGeminiClient:
    """Gemini API 非同步客戶端 — 使用 client.aio.models.generate_content"""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.2,
        use_vertex: bool = False,
        max_concurrent: int = 10,
    ):
        if not HAS_GENAI:
            raise RuntimeError("google-genai not installed")

        self.client = _build_client(api_key, use_vertex=use_vertex)
        self.model = model
        self.temperature = temperature
        self.use_vertex = use_vertex

        # Token 統計 (asyncio safe)
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.candidate_tokens = 0
        self.cached_tokens = 0
        self._lock = asyncio.Lock()

        # 併發控制 — 限制同時 API 請求數
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _update_tokens(self, usage: Dict[str, int]):
        async with self._lock:
            self.total_tokens += usage.get("total_tokens", 0)
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.candidate_tokens += usage.get("candidate_tokens", 0)
            self.cached_tokens += usage.get("cached_tokens", 0)

    @staticmethod
    def _extract_token_usage(response) -> Dict[str, int]:
        """從 response 提取 token 用量"""
        usage = getattr(response, "usage_metadata", None)
        prompt_to = getattr(usage, "prompt_token_count", 0) or 0
        cand_to = getattr(usage, "candidates_token_count", 0) or 0
        cache_to = getattr(usage, "cached_content_token_count", 0) or 0
        return {
            "prompt_tokens": prompt_to,
            "candidate_tokens": cand_to,
            "cached_tokens": cache_to,
            "total_tokens": prompt_to + cand_to + cache_to,
        }

    @staticmethod
    def _extract_response_text(response) -> Optional[str]:
        """從 response 提取文字"""
        response_text = getattr(response, "text", None)
        if not response_text:
            candidates = getattr(response, "candidates", None) or []
            if candidates and candidates[0].content and candidates[0].content.parts:
                response_text = getattr(candidates[0].content.parts[0], "text", None)
        return response_text

    async def generate_structured(
        self,
        prompt: str,
        schema: type,
        image_path: Optional[str] = None,
        max_retries: int = 3,
    ) -> Tuple[Any, Dict[str, int]]:
        """非同步生成結構化輸出"""
        parts = [types.Part(text=prompt)]

        if image_path and Path(image_path).exists():
            img_data, img_mime = load_image_data(image_path)
            parts.append(types.Part(
                inline_data=types.Blob(mime_type=img_mime, data=img_data)
            ))

        contents = [types.Content(role="user", parts=parts)]

        config = _generate_content_config(
            model_name=self.model,
            response_mime_type="application/json",
            response_schema=_get_json_schema(schema),
            temperature=self.temperature,
        )

        last_exc = None
        async with self._semaphore:
            for attempt in range(max_retries):
                t0 = time.perf_counter()
                try:
                    logger.info(
                        "[Gemini] async structured request start model=%s attempt=%d prompt_chars=%d image=%s timeout_s=%s thinking_budget=%s",
                        self.model,
                        attempt + 1,
                        len(prompt),
                        bool(image_path),
                        settings.GEMINI_TIMEOUT_SECONDS,
                        settings.GEMINI_THINKING_BUDGET,
                    )
                    response = await self.client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                    logger.info(
                        "[Gemini] async structured request done model=%s attempt=%d elapsed_ms=%d",
                        self.model,
                        attempt + 1,
                        _duration_ms(t0),
                    )
                    break
                except Exception as e:
                    last_exc = e
                    msg = str(e)
                    logger.warning(
                        "[Gemini] async structured request failed model=%s attempt=%d elapsed_ms=%d error=%s",
                        self.model,
                        attempt + 1,
                        _duration_ms(t0),
                        e,
                    )
                    if "503" in msg or "429" in msg:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
            else:
                raise RuntimeError(
                    f"Gemini async request failed after {max_retries} retries: {last_exc}"
                )

        response_text = self._extract_response_text(response)
        result = schema.model_validate_json(response_text or "{}")
        token_usage = self._extract_token_usage(response)
        await self._update_tokens(token_usage)

        return result, token_usage

    async def generate_text(
        self,
        prompt: str,
        image_path: Optional[str] = None,
        max_retries: int = 3,
    ) -> Tuple[str, Dict[str, int]]:
        """非同步生成文字輸出"""
        parts = [types.Part(text=prompt)]

        if image_path and Path(image_path).exists():
            img_data, img_mime = load_image_data(image_path)
            parts.append(types.Part(
                inline_data=types.Blob(mime_type=img_mime, data=img_data)
            ))

        contents = [types.Content(role="user", parts=parts)]

        config = _generate_content_config(
            model_name=self.model,
            temperature=self.temperature,
        )

        last_exc = None
        async with self._semaphore:
            for attempt in range(max_retries):
                t0 = time.perf_counter()
                try:
                    logger.info(
                        "[Gemini] async text request start model=%s attempt=%d prompt_chars=%d image=%s timeout_s=%s thinking_budget=%s",
                        self.model,
                        attempt + 1,
                        len(prompt),
                        bool(image_path),
                        settings.GEMINI_TIMEOUT_SECONDS,
                        settings.GEMINI_THINKING_BUDGET,
                    )
                    response = await self.client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    )
                    logger.info(
                        "[Gemini] async text request done model=%s attempt=%d elapsed_ms=%d",
                        self.model,
                        attempt + 1,
                        _duration_ms(t0),
                    )
                    break
                except Exception as e:
                    last_exc = e
                    msg = str(e)
                    logger.warning(
                        "[Gemini] async text request failed model=%s attempt=%d elapsed_ms=%d error=%s",
                        self.model,
                        attempt + 1,
                        _duration_ms(t0),
                        e,
                    )
                    if "503" in msg or "429" in msg:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
            else:
                raise RuntimeError(f"Gemini async request failed: {last_exc}")

        response_text = getattr(response, "text", "") or ""
        token_usage = self._extract_token_usage(response)
        await self._update_tokens(token_usage)

        return response_text, token_usage
