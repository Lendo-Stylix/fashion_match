from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

import diskcache

from outfitmatch.preference.schema import StructuredPreference, apply_body_fallback

EXTRACTOR_VERSION = "v1"

STRUCT_PROMPT = """You convert a user's fashion style instruction into JSON.
Schema: {{"hard": {{"colors_avoid": [], "categories_exclude": [],
"materials_require": []}}, "soft": {{"style": "", "color": "", "fit": ""}}}}
- hard = constraints the user explicitly demands (avoid / exclude / require).
  Use empty lists when the user states none.
- soft = short phrases (<= 6 words) for preferred style / color / fit.
  Use "" when unspecified.
User instruction: {instruction}
Reply with ONLY the JSON, no prose."""


def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1].rsplit("```", 1)[0]
    return s.strip()


class PromptStructurer:
    """Free-text global prompt -> StructuredPreference (Gemini-backed, cached).

    `complete_fn` takes a prompt string and returns the model's text reply;
    inject a Gemini client at the call site and a fake in tests.
    """

    def __init__(
        self,
        complete_fn: Callable[[str], str],
        cache_dir: str = "data/raw/occasion_cache/pref_cache",
    ) -> None:
        self._complete = complete_fn
        self._cache = diskcache.Cache(cache_dir)

    def structure(self, instruction: str, body_shape: str) -> StructuredPreference:
        key = hashlib.sha256(
            f"{EXTRACTOR_VERSION}|{instruction}".encode()).hexdigest()
        if key in self._cache:
            raw = self._cache[key]
        else:
            raw = self._complete(STRUCT_PROMPT.format(instruction=instruction))
            self._cache[key] = raw
        data = json.loads(_strip_fence(raw))
        pref = StructuredPreference.model_validate(data)
        return apply_body_fallback(pref, body_shape)
