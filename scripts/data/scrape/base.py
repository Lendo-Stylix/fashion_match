"""HTTP client utilities for catalog scraping.

Design goals:
  * Friendly to target sites — single concurrency, 1–3s jitter sleep.
  * Robust — exponential backoff on 429/5xx, capped retries.
  * Replayable — raw responses cached under data/cache/raw/<store_id>/.
    Re-running with the cache lets us iterate on normalize.py without
    re-hitting the network.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

def _find_repo_root(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start.parents[3]


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
RAW_CACHE_ROOT = REPO_ROOT / "data" / "cache" / "raw"
IMAGE_DIR = REPO_ROOT / "data" / "custom" / "catalog" / "images"
CATALOG_DIR = REPO_ROOT / "data" / "custom" / "catalog"
REGISTRY_DB = REPO_ROOT / "data" / "cache" / "store_registry.db"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass
class FetchResult:
    url: str
    status: int
    json_body: dict | list | None
    from_cache: bool


@dataclass
class TextFetchResult:
    url: str
    status: int
    text: str | None
    from_cache: bool


def _safe_cache_name(key: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in key)


def _cache_path(store_id: str, key: str) -> Path:
    return RAW_CACHE_ROOT / store_id / f"{_safe_cache_name(key)}.json"


def _text_cache_path(store_id: str, key: str) -> Path:
    return RAW_CACHE_ROOT / store_id / f"{_safe_cache_name(key)}.txt"


def _polite_sleep(min_s: float = 1.0, max_s: float = 3.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def fetch_json(
    client: httpx.Client,
    url: str,
    *,
    store_id: str,
    cache_key: str,
    use_cache: bool = True,
    max_retries: int = 4,
    offline: bool = False,
) -> FetchResult:
    """GET a JSON URL with caching + retries.

    Args:
        cache_key: stable filename stem (e.g. "products_page_01").
        offline: when True, return cache miss as an empty 404-like result and
            NEVER hit the network. Caller can stop pagination on the miss.
    """
    cache_file = _cache_path(store_id, cache_key)
    if use_cache and cache_file.exists():
        try:
            body = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.debug("cache hit %s :: %s", store_id, cache_key)
            return FetchResult(url=url, status=200, json_body=body, from_cache=True)
        except json.JSONDecodeError:
            logger.warning("corrupt cache %s, refetching", cache_file)
            cache_file.unlink(missing_ok=True)
    if offline:
        logger.debug("offline: cache miss for %s :: %s", store_id, cache_key)
        return FetchResult(url=url, status=404, json_body=None, from_cache=False)

    backoff = 2.0
    last_status = 0
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.get(url, headers=DEFAULT_HEADERS, follow_redirects=True, timeout=30.0)
            last_status = resp.status_code
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except json.JSONDecodeError:
                    logger.warning("non-JSON 200 from %s", url)
                    return FetchResult(url=url, status=200, json_body=None, from_cache=False)
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(
                    json.dumps(body, ensure_ascii=False), encoding="utf-8"
                )
                _polite_sleep()
                return FetchResult(url=url, status=200, json_body=body, from_cache=False)
            if resp.status_code in (404, 401, 403):
                # don't retry these — adapter decides what to do
                return FetchResult(
                    url=url, status=resp.status_code, json_body=None, from_cache=False
                )
            logger.warning(
                "retry %d/%d %s → %s", attempt, max_retries, url, resp.status_code
            )
        except (httpx.RequestError, httpx.HTTPError) as exc:
            logger.warning("retry %d/%d %s → %r", attempt, max_retries, url, exc)
        time.sleep(backoff + random.random())
        backoff *= 2
    return FetchResult(url=url, status=last_status, json_body=None, from_cache=False)


def fetch_text(
    client: httpx.Client,
    url: str,
    *,
    store_id: str,
    cache_key: str,
    use_cache: bool = True,
    max_retries: int = 3,
    offline: bool = False,
) -> TextFetchResult:
    """GET a text/HTML/XML URL with cache + retries."""
    cache_file = _text_cache_path(store_id, cache_key)
    if use_cache and cache_file.exists():
        return TextFetchResult(
            url=url, status=200, text=cache_file.read_text(encoding="utf-8", errors="ignore"),
            from_cache=True,
        )
    if offline:
        logger.debug("offline: text cache miss for %s :: %s", store_id, cache_key)
        return TextFetchResult(url=url, status=404, text=None, from_cache=False)

    backoff = 1.5
    last_status = 0
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.get(url, headers=DEFAULT_HEADERS, follow_redirects=True, timeout=30.0)
            last_status = resp.status_code
            if resp.status_code == 200 and resp.text:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(resp.text, encoding="utf-8")
                _polite_sleep()
                return TextFetchResult(url=url, status=200, text=resp.text, from_cache=False)
            if resp.status_code in (404, 401, 403):
                return TextFetchResult(
                    url=url, status=resp.status_code, text=None, from_cache=False
                )
            logger.warning(
                "text retry %d/%d %s → %s", attempt, max_retries, url, resp.status_code
            )
        except (httpx.RequestError, httpx.HTTPError) as exc:
            logger.warning("text retry %d/%d %s → %r", attempt, max_retries, url, exc)
        time.sleep(backoff + random.random())
        backoff *= 2
    return TextFetchResult(url=url, status=last_status, text=None, from_cache=False)


def new_client() -> httpx.Client:
    return httpx.Client(
        headers=DEFAULT_HEADERS,
        timeout=30.0,
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    )


def download_image(client: httpx.Client, url: str, dest: Path, max_retries: int = 3) -> bool:
    """Download a binary asset (image). Returns True on success.

    Skips when dest already exists with size > 0.
    """
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    backoff = 1.5
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.get(url, headers=DEFAULT_HEADERS, follow_redirects=True, timeout=60.0)
            if resp.status_code == 200 and resp.content:
                dest.write_bytes(resp.content)
                _polite_sleep(0.3, 0.8)
                return True
            logger.warning(
                "img retry %d/%d %s → %s", attempt, max_retries, url, resp.status_code
            )
        except (httpx.RequestError, httpx.HTTPError) as exc:
            logger.warning("img retry %d/%d %s → %r", attempt, max_retries, url, exc)
        time.sleep(backoff + random.random())
        backoff *= 2
    return False


def load_raw(store_id: str, cache_key: str) -> Any:
    """Read a cached raw response without making a network call (testing helper)."""
    p = _cache_path(store_id, cache_key)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def list_raw_keys(store_id: str) -> list[str]:
    folder = RAW_CACHE_ROOT / store_id
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.json"))
