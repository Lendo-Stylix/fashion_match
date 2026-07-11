"""Verifiable-reward functions for GRPO RL on the stylist model.

Bridges the 6 deterministic scorers in :mod:`outfitmatch.stylist.fashion_eval`
to the ``reward_fn(completions, **kwargs) -> list[float]`` contract expected by
``trl.GRPOTrainer``. This is the **reward module** for the RL strategy in
``docs/reports/stylist_benchmark_expansion/RL_STRATEGY.md`` (GRPO +
verifiable rewards, no reward model, no human pairwise preferences).
"""

from __future__ import annotations

import itertools

from outfitmatch.stylist.fashion_eval import (
    _BODY_SHAPE_ADVICE,
    _SEASON_ADVICE,
    ASK_BACK_ITEMS,
    BODY_SHAPE_ADVICE_ITEMS,
    COHERENCE_ITEMS,
    OCCASION_FORMALITY_ITEMS,
    SEASON_ADVICE_ITEMS,
    TOOL_CALL_DERIVATION_ITEMS,
    score_ask_back,
    score_body_shape_advice,
    score_coherence_judgment,
    score_occasion_formality,
    score_season_advice,
    score_tool_call_derivation,
)
from outfitmatch.stylist.tools import render_search_outfits_tool_call
from outfitmatch.vocab import (
    BODY_SHAPE,
    BODY_SHAPE_LABELS_VI,
    OCCASION,
    OCCASION_LABELS_VI,
    SEASON,
    SEASON_LABELS_VI,
    STYLE,
    formalities_for_occasion,
)

SCORERS = {
    "occasion_formality": score_occasion_formality,
    "body_shape_advice": score_body_shape_advice,
    "season_advice": score_season_advice,
    "coherence": score_coherence_judgment,
    "ask_back": score_ask_back,
    "tool_call_derivation": score_tool_call_derivation,
}

ITEM_TYPES = tuple(SCORERS.keys())


def _completion_text(completion):
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list) and completion:
        first = completion[0]
        if isinstance(first, dict):
            return str(first.get("content", ""))
        return str(first)
    if isinstance(completion, dict):
        return str(completion.get("content", ""))
    return str(completion)


def _extract_score(detail):
    if "score" in detail:
        return float(detail["score"])
    if "f1" in detail:
        return float(detail["f1"])
    if "correct" in detail:
        return 1.0 if detail["correct"] else 0.0
    return 0.0


def _make_task_reward(item_type, scorer):
    def reward_fn(completions, **kwargs):
        items = kwargs.get("items") or kwargs.get("item", [])
        if not isinstance(items, list):
            items = [items]
        if not isinstance(items, list):
            items = [items]
        rewards = []
        for idx, completion in enumerate(completions):
            text = _completion_text(completion)
            item = items[idx] if idx < len(items) else {}
            if item.get("item_type") != item_type:
                rewards.append(0.0)
                continue
            detail = scorer(text, dict(item))
            rewards.append(max(0.0, min(1.0, _extract_score(detail))))
        return rewards

    reward_fn.__name__ = item_type + "_reward"
    return reward_fn


occasion_formality_reward = _make_task_reward("occasion_formality", score_occasion_formality)
body_shape_advice_reward = _make_task_reward("body_shape_advice", score_body_shape_advice)
season_advice_reward = _make_task_reward("season_advice", score_season_advice)
coherence_reward = _make_task_reward("coherence", score_coherence_judgment)
ask_back_reward = _make_task_reward("ask_back", score_ask_back)
tool_call_reward = _make_task_reward("tool_call_derivation", score_tool_call_derivation)

FASHION_REWARD_FUNCS = (
    occasion_formality_reward,
    body_shape_advice_reward,
    season_advice_reward,
    coherence_reward,
    ask_back_reward,
    tool_call_reward,
)


def fashion_reward(completions, **kwargs):
    items = kwargs.get("items") or ([kwargs["item"]] if "item" in kwargs else [])
    if not isinstance(items, list):
        items = [items]
    rewards = []
    for idx, completion in enumerate(completions):
        text = _completion_text(completion)
        item = items[idx] if idx < len(items) else {}
        item_type = item.get("item_type")
        scorer = SCORERS.get(item_type) if isinstance(item_type, str) else None
        if scorer is None:
            rewards.append(0.0)
            continue
        detail = scorer(text, dict(item))
        rewards.append(max(0.0, min(1.0, _extract_score(detail))))
    return rewards


def build_fashion_prompt_pool(max_per_type=None):
    def _cap(rows):
        return rows[:max_per_type] if max_per_type is not None else rows

    pool = []
    for occ in OCCASION:
        appropriate = sorted(formalities_for_occasion(occ))
        if not appropriate:
            continue
        occ_vi = OCCASION_LABELS_VI[occ]
        pool.append(
            {
                "id": "fk_occ_" + occ,
                "item_type": "occasion_formality",
                "occasion": occ,
                "occasion_label_vi": occ_vi,
                "appropriate_formalities": appropriate,
                "prompt": "Cho dịp "
                + occ_vi
                + " ("
                + occ
                + "), mức độ trang trọng (formality) nào là phù hợp? "
                "Hãy nêu các formality nên chọn và giải thích ngắn.",
            }
        )
    for shape in BODY_SHAPE:
        cues = _BODY_SHAPE_ADVICE[shape]
        label_vi = BODY_SHAPE_LABELS_VI[shape]
        pool.append(
            {
                "id": "fk_body_shape_" + shape,
                "item_type": "body_shape_advice",
                "body_shape": shape,
                "body_shape_label_vi": label_vi,
                "positive_keywords": cues["positive"],
                "negative_keywords": cues["negative"],
                "prompt": "Tôn dáng cho "
                + label_vi
                + " ("
                + shape
                + "). Hãy nêu 2-3 gợi ý nên mặc và 1 điều nên tránh.",
            }
        )
    for season in SEASON:
        cues = _SEASON_ADVICE[season]
        label_vi = SEASON_LABELS_VI[season]
        pool.append(
            {
                "id": "fk_season_" + season,
                "item_type": "season_advice",
                "season": season,
                "season_label_vi": label_vi,
                "positive_keywords": cues["positive"],
                "negative_keywords": cues["negative"],
                "prompt": "Chọn vải / lớp mặc cho "
                + label_vi
                + " ("
                + season
                + "). Hãy nêu 2-3 gợi ý nên mặc và 1 điều nên tránh.",
            }
        )
    for item in COHERENCE_ITEMS:
        pool.append({**item, "item_type": "coherence"})
    for item in ASK_BACK_ITEMS:
        pool.append({**item, "item_type": "ask_back"})
    adversarial_stems = [
        "Mình thích phong cách {style}, ngân sách {budget}. Gợi ý outfit nhé.",
        "Tìm outfit phong cách {style} cho dáng {shape}, tầm {budget}. Được không?",
        "Gợi ý outfit {style} cho nam, ngân sách {budget}.",
    ]
    style_cycle = itertools.cycle(STYLE)
    shape_cycle = itertools.cycle(BODY_SHAPE)
    budget_cycle = itertools.cycle(("300K", "500K", "800K", "1 triệu"))
    adv_cap = 12 if (max_per_type is None or max_per_type >= 12) else max_per_type
    for i in range(adv_cap):
        stem = adversarial_stems[i % len(adversarial_stems)]
        pool.append(
            {
                "id": "ab_adv_" + str(i),
                "item_type": "ask_back",
                "missing_required": ["occasion"],
                "prompt": stem.format(
                    style=next(style_cycle), shape=next(shape_cycle), budget=next(budget_cycle)
                ),
            }
        )
    td_rows = []
    for occ, style, shape in itertools.product(OCCASION, STYLE, BODY_SHAPE):
        spec = {"occasion": occ, "style": style, "body_shape": shape}
        reference = render_search_outfits_tool_call(spec)
        td_rows.append(
            {
                "id": "td_" + occ + "_" + style + "_" + shape,
                "item_type": "tool_call_derivation",
                "expected_arguments": spec,
                "reference_tool_call": reference,
                "prompt": "Tìm outfit cho profile: "
                + ", ".join(k + "=" + str(v) for k, v in spec.items())
                + ". Hãy gọi công cụ search_outfits.",
            }
        )
    pool.extend(_cap(td_rows))
    if max_per_type is not None:
        capped = []
        counts = {t: 0 for t in ITEM_TYPES}
        for row in pool:
            t = row.get("item_type", "")
            if counts.get(t, 0) >= max_per_type:
                continue
            counts[t] = counts.get(t, 0) + 1
            capped.append(row)
        pool = capped
    return pool


CANONICAL_ITEMS = (
    OCCASION_FORMALITY_ITEMS,
    BODY_SHAPE_ADVICE_ITEMS,
    SEASON_ADVICE_ITEMS,
    COHERENCE_ITEMS,
    ASK_BACK_ITEMS,
    TOOL_CALL_DERIVATION_ITEMS,
)


def canonical_prompt_pool():
    pool = []
    for items, type_name in zip(CANONICAL_ITEMS, ITEM_TYPES, strict=True):
        for item in items:
            pool.append({**item, "item_type": type_name})
    return pool


__all__ = [
    "ASK_BACK_ITEMS",
    "BODY_SHAPE_ADVICE_ITEMS",
    "CANONICAL_ITEMS",
    "COHERENCE_ITEMS",
    "FASHION_REWARD_FUNCS",
    "ITEM_TYPES",
    "OCCASION_FORMALITY_ITEMS",
    "SCORERS",
    "SEASON_ADVICE_ITEMS",
    "TOOL_CALL_DERIVATION_ITEMS",
    "ask_back_reward",
    "body_shape_advice_reward",
    "build_fashion_prompt_pool",
    "canonical_prompt_pool",
    "coherence_reward",
    "fashion_reward",
    "occasion_formality_reward",
    "season_advice_reward",
    "tool_call_reward",
]
