"""Gemini item semantic tagging for the graph Knowledge Base.

Graph path does not pre-materialize canonical outfits, so Gemini should enrich
item nodes rather than revive the legacy `tag_outfits(outfits)` flow. This module
fills per-item semantic tags that `assemble_record.py` can later derive into
outfit-level metadata.

Current item tags:
  - `body_shapes_fit` (BODY_SHAPE enum values)
  - `season` (SEASON enum values)
  - `stylist_notes_vi` (short Vietnamese note for future explanation use)

All enum outputs are validated against `vocab.py`; stray values are logged and
silently dropped before being written back to the catalog.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from diskcache import Cache

from outfitmatch.vocab import BODY_SHAPE, BODY_SHAPE_SET, SEASON, SEASON_SET, validate_enum_values

if TYPE_CHECKING:
    from collections.abc import Callable

    from outfitmatch.kb.schema import ItemRecord

    type ItemTransport = Callable[[ItemRecord], object]
    type BackendTransport = Callable[[ItemRecord, "TaggingBackend"], object]
    type ProgressLogPath = str | Path

logger = logging.getLogger(__name__)

type BackendStatus = Literal["ok", "rate_limited", "auth_error", "unsupported", "error"]

_PROMPT_VERSION = "graph-item-tag-v1"
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_QUOTA_LIMIT_RE = re.compile(r"limit:\s*(\d+)", re.IGNORECASE)
_RETRY_AFTER_RE = re.compile(r"Please retry in ([0-9.]+)s", re.IGNORECASE)


@dataclass(slots=True)
class ItemTagPayload:
    """Validated Gemini metadata for one item node."""

    body_shapes_fit: list[str] = field(default_factory=list)
    season: list[str] = field(default_factory=list)
    stylist_notes_vi: str = ""


@dataclass(frozen=True, slots=True)
class TaggingBackend:
    """One candidate tagging backend/provider."""

    provider: str
    model: str


@dataclass(frozen=True, slots=True)
class BackendProbeResult:
    """Preflight health result for one backend."""

    backend: TaggingBackend
    status: BackendStatus
    error: str = ""
    limit_rpm: int | None = None
    retry_after_s: float | None = None


def _coerce_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in raw.split(",") if part.strip()]
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if str(v).strip()]
        if isinstance(parsed, str) and parsed.strip():
            return [parsed.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _extract_json_payload(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, ItemTagPayload):
        return {
            "body_shapes_fit": raw.body_shapes_fit,
            "season": raw.season,
            "stylist_notes_vi": raw.stylist_notes_vi,
        }
    if not isinstance(raw, str):
        raise TypeError(f"Unsupported Gemini payload type: {type(raw)!r}")
    text = raw.strip()
    if not text:
        return {}
    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def sanitize_tag_payload(raw: object) -> ItemTagPayload:
    """Normalize Gemini output and drop invalid enum values."""
    payload = _extract_json_payload(raw)

    body_shapes, invalid_body = validate_enum_values(
        _dedupe(_coerce_list(payload.get("body_shapes_fit") or payload.get("body_shapes"))),
        BODY_SHAPE_SET,
    )
    if invalid_body:
        logger.warning("dropping invalid body_shapes_fit tags: %s", invalid_body)

    seasons, invalid_seasons = validate_enum_values(
        _dedupe(_coerce_list(payload.get("season"))),
        SEASON_SET,
    )
    if invalid_seasons:
        logger.warning("dropping invalid season tags: %s", invalid_seasons)

    notes = str(payload.get("stylist_notes_vi") or payload.get("explanation_vi") or "").strip()
    return ItemTagPayload(
        body_shapes_fit=body_shapes,
        season=seasons,
        stylist_notes_vi=notes,
    )


def apply_item_tags(item: ItemRecord, tagged: ItemTagPayload) -> ItemRecord:
    """Mutate one ItemRecord with validated semantic tags."""
    item.body_shapes_fit = list(tagged.body_shapes_fit)
    item.season = list(tagged.season)
    item.stylist_notes_vi = tagged.stylist_notes_vi
    return item


_FALLBACK_NOTES_VI_BY_CATEGORY = {
    "accessory": "Phụ kiện tạo điểm nhấn và hoàn thiện tổng thể outfit.",
    "bag": "Phụ kiện túi giúp hoàn thiện outfit và tăng tính ứng dụng.",
    "shoes": "Giày dép trung tính, dễ phối để hoàn thiện outfit.",
}


def _ensure_minimal_item_note(item: ItemRecord, tagged: ItemTagPayload) -> ItemTagPayload:
    """Add a conservative note when a backend returns no usable semantic signal."""
    if tagged.body_shapes_fit or tagged.season or tagged.stylist_notes_vi.strip():
        return tagged
    note = _FALLBACK_NOTES_VI_BY_CATEGORY.get(
        item.category,
        "Item cơ bản, có thể dùng linh hoạt khi phối outfit.",
    )
    return ItemTagPayload(
        body_shapes_fit=list(tagged.body_shapes_fit),
        season=list(tagged.season),
        stylist_notes_vi=note,
    )


def _cache_key(item: ItemRecord, gemini_model: str) -> str:
    payload = {
        "prompt_version": _PROMPT_VERSION,
        "model": gemini_model,
        "item_id": item.item_id,
        "category": item.category,
        "gender": item.gender,
        "formality": item.formality,
        "image_path": item.image_path,
        "title_vi": item.store.get("title_vi", ""),
        "desc_vi": item.store.get("desc_vi", ""),
        "colors": item.store.get("colors", []),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _build_prompt(item: ItemRecord) -> str:
    colors = ", ".join(str(c) for c in item.store.get("colors", []) if str(c)) or "unknown"
    title = str(item.store.get("title_vi") or "")
    desc = str(item.store.get("desc_vi") or "")
    return f"""
Bạn là stylist thời trang cho thị trường Việt Nam. Hãy phân tích MỘT item thời trang
và trả về JSON HỢP LỆ, không thêm markdown, không thêm giải thích ngoài JSON.

Chỉ dùng đúng enum sau:
- body_shapes_fit: {list(BODY_SHAPE)}
- season: {list(SEASON)}

Nguyên tắc:
- Chỉ điền tag khi có tín hiệu khá rõ từ item + mô tả + ảnh.
- Nếu không chắc, trả [] thay vì đoán.
- `stylist_notes_vi` dài tối đa 1 câu ngắn, tiếng Việt tự nhiên.

Item metadata:
- item_id: {item.item_id}
- category: {item.category}
- gender: {item.gender}
- formality: {item.formality}
- title_vi: {title}
- desc_vi: {desc}
- colors: {colors}

Trả JSON đúng schema:
{{
  "body_shapes_fit": ["pear"],
  "season": ["summer"],
  "stylist_notes_vi": "Áo dáng suông, hợp mặc mùa nóng và dễ cân bằng phần hông."
}}
""".strip()


def _resolve_api_key(explicit: str | None) -> str:
    key = explicit or os.getenv("GEMINI_API") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Missing Gemini API key: set GEMINI_API or GEMINI_API_KEY")
    return key


def _resolve_hf_token(explicit: str | None) -> str:
    token = (
        explicit
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACEHUB_API_TOKEN")
        or os.getenv("HUGGINGFACE_TOKEN")
    )
    if token:
        return token

    from huggingface_hub import get_token

    token = get_token()
    if not token:
        raise RuntimeError(
            "Missing Hugging Face token: run `hf auth login` or set "
            "HF_TOKEN/HUGGINGFACEHUB_API_TOKEN/HUGGINGFACE_TOKEN"
        )
    return token


def _response_text(response: object) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    candidates = getattr(response, "candidates", None)
    if candidates:
        parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if content is None:
                continue
            for part in getattr(content, "parts", []) or []:
                maybe_text = getattr(part, "text", None)
                if isinstance(maybe_text, str) and maybe_text.strip():
                    parts.append(maybe_text)
        if parts:
            return "\n".join(parts)
    raise ValueError("Gemini returned no text payload")


def _chat_response_text(response: object) -> str:
    choices = getattr(response, "choices", None) or []
    for choice in choices:
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content
    raise ValueError("Chat completion returned no text payload")


def _call_gemini(item: ItemRecord, *, gemini_model: str, api_key: str) -> dict[str, object]:
    import google.generativeai as genai
    from PIL import Image

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        gemini_model,
        generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
    )

    prompt = _build_prompt(item)
    image_path = Path(item.image_path)
    if image_path.exists():
        with Image.open(image_path) as image:
            response = model.generate_content((prompt, image.copy()))
    else:
        logger.warning("image missing for item %s: %s", item.item_id, image_path)
        response = model.generate_content(prompt)
    return _extract_json_payload(_response_text(response))


def _normalize_gemma_model(gemma_model: str) -> str:
    return gemma_model if "/" in gemma_model else f"google/{gemma_model}"


def _call_gemma(item: ItemRecord, *, gemma_model: str, api_key: str) -> dict[str, object]:
    from huggingface_hub import InferenceClient

    client = InferenceClient(
        model=_normalize_gemma_model(gemma_model),
        token=api_key,
        timeout=120,
    )
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": _build_prompt(item)}],
        temperature=0.1,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return _extract_json_payload(_chat_response_text(response))


def _resolve_ollama_host() -> str:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host


def _resolve_ollama_timeout() -> float:
    return float(os.getenv("OLLAMA_TIMEOUT", "600"))


def _image_b64(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _image_data_url_jpeg(path: Path) -> str | None:
    """Return a JPEG data URL for OpenAI-compatible multimodal APIs.

    llama.cpp's multimodal server can reject WebP bytes, while the scraped catalog
    contains many `.webp` files. Convert through Pillow so local GGUF vision
    backends receive a stable JPEG payload regardless of the source extension.
    """
    if not path.exists():
        return None

    from PIL import Image

    buffer = io.BytesIO()
    with Image.open(path) as image:
        image.convert("RGB").save(buffer, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def _resolve_openai_base_url() -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8087/v1").strip().rstrip("/")
    if not base_url.startswith(("http://", "https://")):
        base_url = f"http://{base_url}"
    return base_url


def _resolve_openai_timeout() -> float:
    return float(os.getenv("OPENAI_TIMEOUT", "600"))


def _call_openai_compatible(item: ItemRecord, *, model: str) -> dict[str, object]:
    """Call an OpenAI-compatible chat completion API for item semantic tags.

    This targets local llama.cpp/TurboQuant servers at `/v1/chat/completions`, but
    also works with any compatible server that accepts image data URLs.
    """
    image_path = Path(item.image_path)
    content: list[dict[str, object]] = []
    image_url = _image_data_url_jpeg(image_path)
    if image_url is not None:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    else:
        logger.warning("image missing for item %s: %s", item.item_id, image_path)
    content.append({"type": "text", "text": _build_prompt(item)})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 180,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        f"{_resolve_openai_base_url()}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_resolve_openai_timeout()) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI-compatible HTTP {exc.code}: {detail}") from exc

    choices = response_payload.get("choices") or []
    if not choices:
        raise ValueError("OpenAI-compatible response had no choices")
    message = choices[0].get("message") or {}
    content_text = message.get("content")
    if not isinstance(content_text, str) or not content_text.strip():
        raise ValueError("OpenAI-compatible response returned no text payload")
    return _extract_json_payload(content_text)


def _call_ollama(item: ItemRecord, *, model: str) -> dict[str, object]:
    """Call a local Ollama chat model for item semantic tags."""
    image_path = Path(item.image_path)
    message: dict[str, object] = {"role": "user", "content": _build_prompt(item)}
    encoded_image = _image_b64(image_path)
    if encoded_image is not None:
        message["images"] = [encoded_image]
    else:
        logger.warning("image missing for item %s: %s", item.item_id, image_path)

    payload = {
        "model": model,
        "messages": [message],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 300},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{_resolve_ollama_host()}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_resolve_ollama_timeout()) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc

    message_payload = response_payload.get("message") or {}
    content = message_payload.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned no text payload")
    return _extract_json_payload(content)


def _call_backend(
    item: ItemRecord, *, backend: TaggingBackend, api_key: str | None
) -> dict[str, object]:
    if backend.provider == "gemini":
        return _call_gemini(item, gemini_model=backend.model, api_key=_resolve_api_key(api_key))
    if backend.provider == "gemma":
        return _call_gemma(item, gemma_model=backend.model, api_key=_resolve_hf_token(api_key))
    if backend.provider == "ollama":
        return _call_ollama(item, model=backend.model)
    if backend.provider == "openai":
        return _call_openai_compatible(item, model=backend.model)
    raise NotImplementedError(f"Unsupported tagging provider: {backend.provider}")


def _classify_backend_error(exc: Exception) -> tuple[BackendStatus, int | None, float | None]:
    message = str(exc)
    lower = message.lower()
    limit_match = _QUOTA_LIMIT_RE.search(message)
    retry_match = _RETRY_AFTER_RE.search(message)
    limit_rpm = int(limit_match.group(1)) if limit_match else None
    retry_after_s = float(retry_match.group(1)) if retry_match else None

    if "429" in message or "quota" in lower:
        return "rate_limited", limit_rpm, retry_after_s
    if "api key" in lower or "permission" in lower or "unauthorized" in lower:
        return "auth_error", limit_rpm, retry_after_s
    if isinstance(exc, NotImplementedError) or "not supported by provider" in lower:
        return "unsupported", limit_rpm, retry_after_s
    return "error", limit_rpm, retry_after_s


def _is_backend_outage_error(error: object) -> bool:
    """Return True for transport failures that mean the backend process is unavailable."""
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "connection refused",
            "actively refused",
            "winerror 10061",
            "winerror 10060",
            "could not connect",
            "failed to establish a new connection",
            "failed to respond",
            "timed out",
            "connection reset",
            "connection aborted",
            "remote end closed connection",
            "eof",
        )
    )


def probe_backends(
    item: ItemRecord,
    *,
    backends: list[TaggingBackend],
    transport: BackendTransport | None = None,
    api_key: str | None = None,
) -> list[BackendProbeResult]:
    """Probe candidate backends with one real item before a long tagging run."""
    results: list[BackendProbeResult] = []
    for backend in backends:
        try:
            raw = (
                transport(item, backend)
                if transport is not None
                else _call_backend(item, backend=backend, api_key=api_key)
            )
            sanitize_tag_payload(raw)
        except Exception as exc:
            status, limit_rpm, retry_after_s = _classify_backend_error(exc)
            results.append(
                BackendProbeResult(
                    backend=backend,
                    status=status,
                    error=str(exc),
                    limit_rpm=limit_rpm,
                    retry_after_s=retry_after_s,
                )
            )
            continue
        results.append(BackendProbeResult(backend=backend, status="ok"))
    return results


def _has_quota_error(errors: list[object]) -> bool:
    return any(
        "429" in str(getattr(err, "get", lambda *_: "")("error", ""))
        or "quota" in str(getattr(err, "get", lambda *_: "")("error", "")).lower()
        for err in errors
    )


def _history_gate_result(progress_path: Path, backend: TaggingBackend) -> BackendProbeResult | None:
    if not progress_path.exists():
        return None

    latest_failure: BackendProbeResult | None = None
    for line in progress_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        model = str(record.get("model") or "")
        if model not in {backend.model, f"{backend.provider}:{backend.model}"}:
            continue
        if record.get("ok"):
            latest_failure = None
            continue
        for err in record.get("errors") or []:
            message = str(err.get("error") or "")
            status, limit_rpm, retry_after_s = _classify_backend_error(RuntimeError(message))
            if status in {"rate_limited", "auth_error", "unsupported"}:
                latest_failure = BackendProbeResult(
                    backend=backend,
                    status=status,
                    error=message,
                    limit_rpm=limit_rpm,
                    retry_after_s=retry_after_s,
                )
                break
    return latest_failure


def gate_backends(
    item: ItemRecord,
    *,
    backends: list[TaggingBackend],
    progress_path: Path,
    transport: BackendTransport | None = None,
    api_key: str | None = None,
) -> list[BackendProbeResult]:
    """Combine historical 429 evidence with live probing for backend selection."""
    results: list[BackendProbeResult] = []
    for backend in backends:
        gated = _history_gate_result(progress_path, backend)
        if gated is not None:
            results.append(gated)
            continue
        results.extend(
            probe_backends(item, backends=[backend], transport=transport, api_key=api_key)
        )
    return results


def select_backend(results: list[BackendProbeResult]) -> TaggingBackend | None:
    """Pick the first healthy backend from probe results."""
    for result in results:
        if result.status == "ok":
            return result.backend
    return None


def _append_progress_record(progress_log: str | Path | None, record: dict[str, object]) -> None:
    if progress_log is None:
        return
    progress_path = Path(progress_log)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def clear_failed_429_tags(catalog_path: Path, progress_path: Path) -> int:
    """Reset semantic tag columns for rows that failed with 429/quota errors."""
    if not progress_path.exists():
        return 0

    failed_ids: set[str] = set()
    for line in progress_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        item_id = str(record.get("item_id") or "")
        if not item_id:
            continue
        if record.get("ok"):
            failed_ids.discard(item_id)
            continue
        errors = record.get("errors") or []
        if _has_quota_error(errors):
            failed_ids.add(item_id)

    if not failed_ids:
        return 0

    catalog = json.loads("null")
    import pandas as pd

    catalog = pd.read_parquet(catalog_path)
    for column in ("body_shapes_fit", "season", "stylist_notes_vi"):
        if column not in catalog.columns:
            catalog[column] = "[]" if column != "stylist_notes_vi" else ""

    updated = 0
    for idx, item_id in enumerate(catalog["item_id"].astype(str)):
        if item_id not in failed_ids:
            continue
        catalog.at[idx, "body_shapes_fit"] = "[]"
        catalog.at[idx, "season"] = "[]"
        catalog.at[idx, "stylist_notes_vi"] = ""
        updated += 1

    catalog.to_parquet(catalog_path, index=False)
    return updated


def tag_items(
    items: list[ItemRecord],
    gemini_model: str = "gemma-4-26b-a4b-it",
    cache_dir: str = "data/cache/gemini_tagging",
    *,
    api_key: str | None = None,
    force: bool = False,
    transport: ItemTransport | None = None,
    backends: list[TaggingBackend] | None = None,
    backend_transport: BackendTransport | None = None,
    progress_log: str | Path | None = None,
    max_consecutive_backend_failures: int = 5,
) -> list[ItemRecord]:
    """Tag graph item nodes and mutate them in place."""
    if backends is None:
        backends = [TaggingBackend(provider="gemini", model=gemini_model)]

    consecutive_backend_failures = 0
    with Cache(cache_dir) as cache:
        for item in items:
            errors: list[dict[str, object]] = []
            final_backend: TaggingBackend | None = None
            for backend in backends:
                final_backend = backend
                model_key = f"{backend.provider}:{backend.model}"
                key = _cache_key(item, model_key)
                cached = None if force else cache.get(key)
                raw = cached
                if raw is None:
                    try:
                        raw = (
                            transport(item)
                            if transport is not None and backend.provider == "gemini"
                            else backend_transport(item, backend)
                            if backend_transport is not None
                            else _call_backend(item, backend=backend, api_key=api_key)
                        )
                        cache.set(key, raw)
                    except Exception as exc:
                        logger.warning(
                            "Tagging failed for %s via %s/%s: %s",
                            item.item_id,
                            backend.provider,
                            backend.model,
                            exc,
                        )
                        errors.append(
                            {
                                "provider": backend.provider,
                                "model": backend.model,
                                "error": str(exc),
                            }
                        )
                        continue
                try:
                    tagged = _ensure_minimal_item_note(item, sanitize_tag_payload(raw))
                    apply_item_tags(item, tagged)
                    _append_progress_record(
                        progress_log,
                        {
                            "item_id": item.item_id,
                            "provider": backend.provider,
                            "model": backend.model,
                            "ok": True,
                            "body_shapes_fit": tagged.body_shapes_fit,
                            "season": tagged.season,
                            "stylist_notes_vi": tagged.stylist_notes_vi,
                            "errors": errors,
                        },
                    )
                    consecutive_backend_failures = 0
                    break
                except Exception as exc:
                    logger.warning(
                        "Invalid tagging payload for %s via %s/%s: %s",
                        item.item_id,
                        backend.provider,
                        backend.model,
                        exc,
                    )
                    errors.append(
                        {
                            "provider": backend.provider,
                            "model": backend.model,
                            "error": str(exc),
                        }
                    )
            else:
                logger.warning("All tagging backends failed for %s", item.item_id)
                _append_progress_record(
                    progress_log,
                    {
                        "item_id": item.item_id,
                        "provider": final_backend.provider if final_backend else "",
                        "model": final_backend.model if final_backend else "",
                        "ok": False,
                        "body_shapes_fit": [],
                        "season": [],
                        "stylist_notes_vi": "",
                        "errors": errors,
                    },
                )
                if any(_is_backend_outage_error(error.get("error", "")) for error in errors):
                    consecutive_backend_failures += 1
                else:
                    consecutive_backend_failures = 0
                if (
                    max_consecutive_backend_failures > 0
                    and consecutive_backend_failures >= max_consecutive_backend_failures
                ):
                    raise RuntimeError(
                        "Aborting tagging batch after "
                        f"{consecutive_backend_failures} consecutive backend connection failures; "
                        "restart or stabilize the local LLM server before resuming."
                    )
    return items
