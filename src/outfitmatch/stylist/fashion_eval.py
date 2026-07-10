"""Fashion-knowledge & fashion-logic benchmark for the stylist core capability.

These benchmarks measure the **tri thức thời trang** (fashion knowledge) and
**logic thời trang** (fashion reasoning) of a fine-tuned stylist model, using
objective, deterministic scorers grounded in :mod:`outfitmatch.vocab`.

No LLM judge is required — every score is computed by parsing the model's
free-text / tool-call output and comparing it against rule-based ground truth
derived from the controlled vocabulary. This keeps the benchmark reproducible,
cheap, and aligned with the v3.1-lite philosophy ("không black-box, giải thích
được").

Two families:

* **Knowledge items** — closed fashion facts the stylist should express:
  occasion → appropriate formality band.
* **Logic items** — multi-step reasoning the stylist should perform:
  outfit-coherence judgment, ask-back when a required slot (``occasion``) is
  missing, and tool-call derivation from a complete user profile.

The scorer interface mirrors :func:`outfitmatch.stylist.benchmark.evaluate_dataset`
— a ``generate_fn`` receives the conversation and returns the model's string.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any

from outfitmatch.stylist.benchmark import compute_tool_call_f1
from outfitmatch.stylist.tools import render_search_outfits_tool_call
from outfitmatch.stylist.validation import extract_tool_calls, validate_tool_calls
from outfitmatch.vocab import (
    BODY_SHAPE,
    BODY_SHAPE_LABELS_VI,
    FORMALITY,
    FORMALITY_LABELS_VI,
    OCCASION,
    OCCASION_LABELS_VI,
    SEASON,
    SEASON_LABELS_VI,
    formalities_for_occasion,
)

# ---------------------------------------------------------------------------
# Verdict keywords for outfit-coherence judgment
# ---------------------------------------------------------------------------
# Check incoherent FIRST because "không phù hợp" contains "phù hợp".
_INCOHERENT_KW: tuple[str, ...] = (
    "không phù hợp",
    "không hợp",
    "lệch",
    "kém",
    "mâu thuẫn",
    "không nên",
)
_COHERENT_KW: tuple[str, ...] = (
    "phù hợp",
    "hài hòa",
    "hài hoàn",
    "gọn gàng",
    "tốt",
    "đẹp",
    "hợp lý",
)

# Ask-back cue phrases (a lone question mark also counts).
_ASKBACK_RE = re.compile(
    r"bạn muốn|cho mình hỏi|dịp nào|muốn mặc|phù hợp với|dịp gì",
    re.IGNORECASE,
)


def _count_keywords(text: str, keywords: Sequence[str]) -> list[str]:
    """Return keywords (in order) whose lower-cased form is a substring of *text*."""
    lower = text.lower()
    return [kw for kw in keywords if kw.lower() in lower]


# ---------------------------------------------------------------------------
# Generic enum extraction from free text (English snake_case *or* VI label)
# ---------------------------------------------------------------------------
def extract_enum_values(
    text: str,
    values: Sequence[str],
    labels_vi: dict[str, str],
) -> set[str]:
    """Return canonical enum values mentioned in *text*.

    A value is considered mentioned if either:
      * its English ``snake_case`` token appears as a whole word
        (case-insensitive), or
      * its Vietnamese display label appears as a substring (case-insensitive).

    This dual matching lets the scorer credit a model that answers in either
    language while always normalising to the canonical internal value.
    """
    text_lower = text.lower()
    found: set[str] = set()
    for value in values:
        if re.search(r"\b" + re.escape(value) + r"\b", text, re.IGNORECASE):
            found.add(value)
            continue
        label = labels_vi.get(value, "")
        if label and label.lower() in text_lower:
            found.add(value)
    return found


# ---------------------------------------------------------------------------
# Knowledge scorer: occasion → formality
# ---------------------------------------------------------------------------
def score_occasion_formality(generated: str, item: dict[str, Any]) -> dict[str, Any]:
    """Score whether *generated* names appropriate formality band(s) for an occasion.

    The item carries ``appropriate_formalities`` (a subset of ``FORMALITY``).
    Mentioning an inappropriate formality is penalised via precision; omitting
    an appropriate one lowers recall.
    """
    appropriate: set[str] = set(item["appropriate_formalities"])
    mentioned = extract_enum_values(generated, FORMALITY, FORMALITY_LABELS_VI)
    correct = mentioned & appropriate
    wrong = mentioned - appropriate

    precision = len(correct) / max(len(correct) + len(wrong), 1)
    recall = len(correct) / max(len(appropriate), 1)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "occasion": item.get("occasion"),
        "correct": len(correct) > 0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "wrong_formalities": sorted(wrong),
    }


def _score_advice_bank(
    generated: str,
    positive_keywords: Sequence[str],
    negative_keywords: Sequence[str],
) -> dict[str, Any]:
    """Shared scorer for curated fashion-advice item banks.

    A model is rewarded for mentioning canonical positive advice cues (recall)
    and penalised for stating clearly-wrong advice (each negative mention halves
    the score, floored at 0). ``correct`` requires at least one positive and no
    negative — i.e. the model gave the right kind of advice without a wrong one.
    """
    positives = _count_keywords(generated, positive_keywords)
    negatives = _count_keywords(generated, negative_keywords)
    recall = len(positives) / max(len(positive_keywords), 1)
    score = max(0.0, recall - 0.5 * len(negatives))
    return {
        "positives_mentioned": positives,
        "negatives_mentioned": negatives,
        "correct": len(positives) > 0 and len(negatives) == 0,
        "score": round(score, 4),
    }


def score_body_shape_advice(generated: str, item: dict[str, Any]) -> dict[str, Any]:
    """Score body-shape styling advice against a curated canonical cue bank."""
    result = _score_advice_bank(generated, item["positive_keywords"], item["negative_keywords"])
    return {"body_shape": item.get("body_shape"), **result}


def score_season_advice(generated: str, item: dict[str, Any]) -> dict[str, Any]:
    """Score season fabric / layering advice against a curated canonical cue bank."""
    result = _score_advice_bank(generated, item["positive_keywords"], item["negative_keywords"])
    return {"season": item.get("season"), **result}


# ---------------------------------------------------------------------------
# Logic scorer: outfit-coherence judgment
# ---------------------------------------------------------------------------
def detect_verdict(text: str) -> bool | None:
    """Classify *text* as a coherence verdict.

    Returns ``True`` (coherent), ``False`` (incoherent), or ``None``
    (undetermined). Negation is handled by checking incoherent cues first.
    """
    lower = text.lower()
    for kw in _INCOHERENT_KW:
        if kw in lower:
            return False
    for kw in _COHERENT_KW:
        if kw in lower:
            return True
    return None


def score_coherence_judgment(generated: str, item: dict[str, Any]) -> dict[str, Any]:
    """Score whether *generated* judges outfit coherence correctly.

    The item carries the ground-truth ``is_coherent`` flag plus the outfit's
    items (for downstream error analysis).
    """
    expected = bool(item["is_coherent"])
    verdict = detect_verdict(generated)
    correct = verdict is not None and verdict == expected
    verdict_label = (
        "coherent" if verdict is True else "incoherent" if verdict is False else "undetermined"
    )
    return {
        "verdict": verdict_label,
        "expected": expected,
        "correct": correct,
        "score": 1.0 if correct else 0.0,
    }


# ---------------------------------------------------------------------------
# Logic scorer: ask-back when required info is missing
# ---------------------------------------------------------------------------
def score_ask_back(generated: str, item: dict[str, Any]) -> dict[str, Any]:
    """Score whether the model abstains / asks back instead of hallucinating.

    Rule (when ``occasion`` is among the missing required fields): the model
    passes iff it shows an ask-back signal (a question mark or an ask-back cue)
    **and** does not emit a tool call that fills in (hallucinates) ``occasion``.
    Saying nothing or inventing an occasion both fail.
    """
    tool_calls = extract_tool_calls(generated)
    hallucinated = False
    for call in tool_calls:
        args = call.get("arguments", {})
        if isinstance(args, dict) and args.get("occasion"):
            hallucinated = True
    asked_back = ("?" in generated) or bool(_ASKBACK_RE.search(generated))
    correct = asked_back and not hallucinated
    return {
        "asked_back": asked_back,
        "hallucinated_occasion": hallucinated,
        "correct": correct,
        "score": 1.0 if correct else 0.0,
    }


# ---------------------------------------------------------------------------
# Logic scorer: tool-call derivation from a complete user profile
# ---------------------------------------------------------------------------
def score_tool_call_derivation(generated: str, item: dict[str, Any]) -> dict[str, Any]:
    """Score the derived ``search_outfits`` call against an expected reference.

    Combines token-overlap tool-call F1 (reused from the generic benchmark)
    with an enum-validity gate: a hallucinated enum value zeroes the score even
    if the rest of the call overlaps, so the model is rewarded only for a call
    that is both complete *and* schema-conformant.
    """
    reference = item["reference_tool_call"]
    f1 = compute_tool_call_f1(generated, reference)
    if f1 is None:
        f1 = 0.0

    calls = extract_tool_calls(generated)
    enum_valid = False
    if calls:
        ok, _ = validate_tool_calls(generated)
        enum_valid = ok

    score = f1 if enum_valid else 0.0
    return {
        "tool_call_f1": round(f1, 4),
        "enum_valid": enum_valid,
        "score": round(score, 4),
    }


# ---------------------------------------------------------------------------
# Curated item banks — derived from vocab.py (reproducible, single source)
# ---------------------------------------------------------------------------
def _build_occasion_formality_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for occ in OCCASION:
        appropriate = sorted(formalities_for_occasion(occ))
        if not appropriate:
            continue
        appr_vi = ", ".join(FORMALITY_LABELS_VI[f] for f in appropriate)
        occ_vi = OCCASION_LABELS_VI[occ]
        prompt = (
            f"Cho dịp {occ_vi} ({occ}), mức độ trang trọng (formality) nào là phù hợp? "
            "Hãy nêu các formality nên chọn và giải thích ngắn."
        )
        reference = f"Dịp {occ_vi} nên chọn formality: {appr_vi}."
        items.append(
            {
                "id": f"fk_occ_{occ}",
                "occasion": occ,
                "occasion_label_vi": occ_vi,
                "appropriate_formalities": appropriate,
                "prompt": prompt,
                "reference": reference,
            }
        )
    return items


OCCASION_FORMALITY_ITEMS: list[dict[str, Any]] = _build_occasion_formality_items()


# Curated canonical styling advice for body shapes (tri thức thời trang).
# Each entry: fashion-do cues (positive) and fashion-dont cues (negative).
_BODY_SHAPE_ADVICE: dict[str, dict[str, tuple[str, ...]]] = {
    "pear": {
        "positive": ("nhấn eo", "chân váy a", "a-line", "high waist", "áo phồng tay"),
        "negative": ("quần bó sát hông", "nhiều chi tiết hông"),
    },
    "apple": {
        "positive": ("che eo", "chân váy chữ a", "v cổ", "khoác ngoài dài", "kẻ sọc dọc"),
        "negative": ("bó eo", "crop top", "nhấn eo"),
    },
    "hourglass": {
        "positive": ("nhấn eo", "bó sát", "đường cong", "thắt lưng"),
        "negative": ("boxy", "suông rộng", "kín cổ kín cổ"),
    },
    "rectangle": {
        "positive": ("tạo cong", "peplum", "layer", "nhấn eo", "chân váy xòe"),
        "negative": ("thẳng suông một khối", "boxy"),
    },
    "inverted_triangle": {
        "positive": ("chân váy xòe", "volume phần dưới", "đẩy chú ý xuống", "né vai rộng"),
        "negative": ("pad vai", "shoulder pad", "vai phồng"),
    },
}

# Curated canonical fabric / layering advice per season.
_SEASON_ADVICE: dict[str, dict[str, tuple[str, ...]]] = {
    "summer": {
        "positive": ("cotton", "linen", "thoáng", "nhẹ", "sáng màu"),
        "negative": ("len", "dạ", "áo ấm dày", "hoodie", "lót lông"),
    },
    "transitional": {
        "positive": ("layer nhẹ", "khoác nhẹ", "cardigan", "sơ mi", "áo khoác nhẹ"),
        "negative": ("áo rét dày", "đồ quá mỏng", "áo phông mỏng"),
    },
    "winter": {
        "positive": ("len", "dạ", "ấm", "layer", "khoác ngoài", "lót lông"),
        "negative": ("cotton mỏng", "sandal", "quần short", "vải voan"),
    },
    "rainy": {
        "positive": ("áo mưa", "chống trượt", "nhiều lớp nhẹ", "giày bọc", "vải chống nước"),
        "negative": ("suede", "da thật", "giày vải", "mỏng dễ thấm"),
    },
}


def _build_advice_items(
    advice_map: dict[str, dict[str, tuple[str, ...]]],
    enum_values: Sequence[str],
    labels_vi: dict[str, str],
    key: str,
    question: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for value in enum_values:
        cues = advice_map[value]
        label_vi = labels_vi[value]
        prompt = (
            f"{question} cho {label_vi} ({value}). Hãy nêu 2-3 gợi ý nên mặc và 1 điều nên tránh."
        )
        reference = (
            f"{label_vi}: ưu tiên {', '.join(cues['positive'])}; né {', '.join(cues['negative'])}."
        )
        items.append(
            {
                "id": f"fk_{key}_{value}",
                key: value,
                f"{key}_label_vi": label_vi,
                "positive_keywords": cues["positive"],
                "negative_keywords": cues["negative"],
                "prompt": prompt,
                "reference": reference,
            }
        )
    return items


BODY_SHAPE_ADVICE_ITEMS: list[dict[str, Any]] = _build_advice_items(
    _BODY_SHAPE_ADVICE, BODY_SHAPE, BODY_SHAPE_LABELS_VI, "body_shape", "Tôn dáng"
)
SEASON_ADVICE_ITEMS: list[dict[str, Any]] = _build_advice_items(
    _SEASON_ADVICE, SEASON, SEASON_LABELS_VI, "season", "Chọn vải / lớp mặc"
)

COHERENCE_ITEMS: list[dict[str, Any]] = [
    {
        "id": "fc_coh_casual",
        "items": [
            {"category": "top", "formality": "casual"},
            {"category": "bottom", "formality": "casual"},
            {"category": "shoes", "formality": "casual"},
        ],
        "is_coherent": True,
        "prompt": (
            "Đánh giá outfit: áo thun casual + quần jeans casual + giày sneaker casual. "
            "Combo này phù hợp không?"
        ),
        "reference": "Phù hợp, mọi item cùng ở band casual.",
    },
    {
        "id": "fc_inc_blazer_gym",
        "items": [
            {"category": "outerwear", "formality": "formal"},
            {"category": "bottom", "formality": "athletic"},
        ],
        "is_coherent": False,
        "prompt": "Đánh giá outfit: blazer formal + quần short gym athletic. Phù hợp không?",
        "reference": "Không phù hợp, blazer formal và quần gym athletic lệch 3 cấp formality.",
    },
    {
        "id": "fc_inc_smartcasual_athletic",
        "items": [
            {"category": "top", "formality": "smart_casual"},
            {"category": "shoes", "formality": "athletic"},
        ],
        "is_coherent": False,
        "prompt": "Đánh giá outfit: sơ mi smart_casual + giày chạy bộ athletic. Phù hợp không?",
        "reference": "Không phù hợp, lệch 2 cấp formality, vượt tolerance=1.",
    },
    {
        "id": "fc_coh_smartcasual",
        "items": [
            {"category": "top", "formality": "smart_casual"},
            {"category": "shoes", "formality": "smart_casual"},
        ],
        "is_coherent": True,
        "prompt": "Đánh giá outfit: sơ mi smart_casual + giày loafers smart_casual. Phù hợp không?",
        "reference": "Phù hợp, cùng band smart_casual.",
    },
]

ASK_BACK_ITEMS: list[dict[str, Any]] = [
    {
        "id": "ab_missing_occasion_1",
        "missing_required": ["occasion"],
        "prompt": (
            "Mình thích phong cách Hàn, dáng quả lê, ngân sách khoảng 500k. Gợi ý outfit nhé."
        ),
        "reference": "Bạn muốn mặc cho dịp nào ạ? (đi làm, hẹn hò, đám cưới, ...)",
    },
    {
        "id": "ab_missing_occasion_2",
        "missing_required": ["occasion"],
        "prompt": "Tìm outfit nữ tính, tone da ấm, không cần dùng ảnh.",
        "reference": "Bạn dự định mặc cho dịp gì để mình tìm outfit phù hợp?",
    },
    {
        "id": "ab_missing_occasion_3",
        "missing_required": ["occasion"],
        "prompt": "Gợi ý outfit streetwear cho nam, ngân sách 300K.",
        "reference": "Dịp mặc là gì ạ? streetwear đi học, đi cafe, hay đi tiệc?",
    },
]


def _build_tool_call_derivation_items() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        {"occasion": "wedding", "style": "elegant", "body_shape": "hourglass"},
        {"occasion": "office", "style": "minimalist", "price_max": 500000},
        {"occasion": "school", "style": "korean", "body_shape": "rectangle", "price_max": 300000},
    ]
    items: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        reference = render_search_outfits_tool_call(spec)
        prompt = (
            "Tìm outfit cho profile: "
            + ", ".join(f"{k}={v}" for k, v in spec.items())
            + ". Hãy gọi công cụ search_outfits."
        )
        items.append(
            {
                "id": f"td_{index}",
                "expected_arguments": spec,
                "reference_tool_call": reference,
                "prompt": prompt,
            }
        )
    return items


TOOL_CALL_DERIVATION_ITEMS: list[dict[str, Any]] = _build_tool_call_derivation_items()


# ---------------------------------------------------------------------------
# Aggregator (same shape as benchmark.evaluate_dataset)
# ---------------------------------------------------------------------------
_SCORERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "occasion_formality": score_occasion_formality,
    "body_shape_advice": score_body_shape_advice,
    "season_advice": score_season_advice,
    "coherence": score_coherence_judgment,
    "ask_back": score_ask_back,
    "tool_call_derivation": score_tool_call_derivation,
}


def evaluate_fashion_dataset(
    dataset: Sequence[dict[str, Any]],
    generate_fn: Callable[[list[dict[str, str]]], str],
    max_samples: int | None = None,
) -> dict[str, Any]:
    """Run *generate_fn* over the fashion benchmark dataset and aggregate scores.

    Each record must carry an ``item_type`` key (one of ``occasion_formality``,
    ``body_shape_advice``, ``season_advice``, ``coherence``, ``ask_back``,
    ``tool_call_derivation``) and the fields its scorer needs. The prompt is
    taken from record ``"prompt"``; this keeps the dataset a list of *items*
    rather than full conversations.

    Returns overall + per-task aggregate plus per-sample details.
    """
    records = list(dataset)
    if max_samples is not None:
        records = records[:max_samples]

    results: list[dict[str, Any]] = []
    for record in records:
        item_type = record.get("item_type")
        item_type = item_type if isinstance(item_type, str) else ""
        prompt = record.get("prompt", "")
        messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
        generated = generate_fn(messages)
        scorer = _SCORERS.get(item_type)
        detail = scorer(generated, dict(record)) if scorer else {"score": 0.0}

        row = dict(record)
        row["item_type"] = item_type
        row["generated"] = generated
        row["score"] = detail.get("score", 0.0)
        row["detail"] = detail
        results.append(row)

    per_task: dict[str, dict[str, Any]] = {}
    all_scores: list[float] = []
    for row in results:
        task = row["item_type"] if isinstance(row.get("item_type"), str) else "unknown"
        if task not in per_task:
            per_task[task] = {"count": 0, "scores": []}
        per_task[task]["count"] += 1
        per_task[task]["scores"].append(row["score"])
        all_scores.append(row["score"])

    def _mean(values: list[float]) -> float:
        return round(sum(values) / max(len(values), 1), 4)

    per_task_summary = {
        task: {"count": vals["count"], "mean_score": _mean(vals["scores"])}
        for task, vals in per_task.items()
    }

    return {
        "overall": {"count": len(results), "mean_score": _mean(all_scores)},
        "per_task": per_task_summary,
        "samples": results,
    }
