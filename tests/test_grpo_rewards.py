"""Unit tests for the GRPO verifiable-reward module (scripts/stylist/grpo_rewards.py).

Tests cover:
  * 6 per-task reward functions (correct completion scores 1.0, wrong -> 0).
  * dispatching fashion_reward over a mixed pool.
  * prompt-pool builder (size, item_type tags, determinism).
  * TRL contract: reward_fn(completions, **kwargs) -> list[float].
  * completion normalisation (string / chat-dict / list forms).
"""

from __future__ import annotations

from scripts.stylist.grpo_rewards import (
    FASHION_REWARD_FUNCS,
    ITEM_TYPES,
    SCORERS,
    ask_back_reward,
    body_shape_advice_reward,
    build_fashion_prompt_pool,
    canonical_prompt_pool,
    coherence_reward,
    fashion_reward,
    occasion_formality_reward,
    season_advice_reward,
    tool_call_reward,
)


# ---------------------------------------------------------------------------
# Prompt-pool builder
# ---------------------------------------------------------------------------
class TestPromptPool:
    def test_pool_has_all_six_task_types(self):
        pool = build_fashion_prompt_pool()
        types = {row["item_type"] for row in pool}
        assert types == set(ITEM_TYPES)

    def test_pool_size_positive(self):
        pool = build_fashion_prompt_pool()
        assert len(pool) >= 28  # at least the canonical set expanded

    def test_every_row_has_prompt_and_item_type(self):
        pool = build_fashion_prompt_pool()
        for row in pool:
            assert "prompt" in row and isinstance(row["prompt"], str) and row["prompt"]
            assert row.get("item_type") in ITEM_TYPES

    def test_pool_is_deterministic(self):
        a = build_fashion_prompt_pool()
        b = build_fashion_prompt_pool()
        assert [r["id"] for r in a] == [r["id"] for r in b]

    def test_max_per_type_caps_each_task(self):
        pool = build_fashion_prompt_pool(max_per_type=3)
        counts: dict[str, int] = {}
        for row in pool:
            counts[row["item_type"]] = counts.get(row["item_type"], 0) + 1
        for t, n in counts.items():
            assert n <= 3, f"{t} has {n} > 3"

    def test_canonical_pool_has_28_items(self):
        pool = canonical_prompt_pool()
        assert len(pool) == 28
        assert {row["item_type"] for row in pool} == set(ITEM_TYPES)


# ---------------------------------------------------------------------------
# Per-task reward functions
# ---------------------------------------------------------------------------
class TestOccasionFormalityReward:
    def test_correct_completion_scores_positive(self):
        item = {
            "item_type": "occasion_formality",
            "occasion": "wedding",
            "appropriate_formalities": ["formal"],
        }
        completion = "Dùng trang trọng (formal) cho đám cưới."
        rewards = occasion_formality_reward([completion], items=[item])
        assert rewards == [1.0]

    def test_wrong_completion_scores_zero(self):
        item = {
            "item_type": "occasion_formality",
            "occasion": "wedding",
            "appropriate_formalities": ["formal"],
        }
        completion = "Mặc thể thao (athletic) cho đám cưới."
        rewards = occasion_formality_reward([completion], items=[item])
        assert rewards == [0.0]

    def test_non_matching_item_type_scores_zero(self):
        item = {"item_type": "coherence"}
        rewards = occasion_formality_reward(["anything"], items=[item])
        assert rewards == [0.0]


class TestBodyShapeAdviceReward:
    def test_correct_advice_positive(self):
        item = {
            "item_type": "body_shape_advice",
            "body_shape": "pear",
            "positive_keywords": ("nhấn eo", "chân váy a"),
            "negative_keywords": ("quần bó",),
        }
        completion = "Nên nhấn eo và mặc chân váy a."
        rewards = body_shape_advice_reward([completion], items=[item])
        assert rewards[0] > 0.0

    def test_negative_advice_penalised(self):
        item = {
            "item_type": "body_shape_advice",
            "body_shape": "pear",
            "positive_keywords": ("nhấn eo",),
            "negative_keywords": ("quần bó",),
        }
        completion = "Nên mặc quần bó."
        rewards = body_shape_advice_reward([completion], items=[item])
        assert rewards == [0.0]


class TestSeasonAdviceReward:
    def test_correct_season_advice(self):
        item = {
            "item_type": "season_advice",
            "season": "summer",
            "positive_keywords": ("cotton", "linen"),
            "negative_keywords": ("len",),
        }
        completion = "Mùa hè nên mặc cotton hoặc linen."
        rewards = season_advice_reward([completion], items=[item])
        assert rewards[0] > 0.0


class TestCoherenceReward:
    def test_coherent_judged_coherent(self):
        item = {"item_type": "coherence", "is_coherent": True}
        completion = "Combo này phù hợp vì cùng band casual."
        rewards = coherence_reward([completion], items=[item])
        assert rewards == [1.0]

    def test_incoherent_judged_incoherent(self):
        item = {"item_type": "coherence", "is_coherent": False}
        completion = "Không phù hợp, lệch formality."
        rewards = coherence_reward([completion], items=[item])
        assert rewards == [1.0]

    def test_wrong_verdict_zero(self):
        item = {"item_type": "coherence", "is_coherent": True}
        completion = "Không phù hợp."
        rewards = coherence_reward([completion], items=[item])
        assert rewards == [0.0]


class TestAskBackReward:
    def test_asks_back_when_missing_occasion(self):
        item = {"item_type": "ask_back", "missing_required": ["occasion"]}
        completion = "Bạn muốn mặc cho dịp nào ạ?"
        rewards = ask_back_reward([completion], items=[item])
        assert rewards == [1.0]

    def test_hallucinated_occasion_fails(self):
        item = {"item_type": "ask_back", "missing_required": ["occasion"]}
        completion = (
            '<tool_call>{"name":"search_outfits","arguments":{"occasion":"wedding"}}</tool_call>'
        )
        rewards = ask_back_reward([completion], items=[item])
        assert rewards == [0.0]

    def test_no_askback_fails(self):
        item = {"item_type": "ask_back", "missing_required": ["occasion"]}
        completion = "Mình sẽ tìm outfit cho bạn."
        rewards = ask_back_reward([completion], items=[item])
        assert rewards == [0.0]


class TestToolCallReward:
    def test_correct_tool_call_positive(self):
        item = {
            "item_type": "tool_call_derivation",
            "expected_arguments": {"occasion": "wedding", "style": "elegant"},
            "reference_tool_call": (
                '<tool_call>{"name":"search_outfits","arguments":'
                '{"occasion":"wedding","style":"elegant"}}</tool_call>'
            ),
        }
        completion = (
            '<tool_call>{"name":"search_outfits","arguments":'
            '{"occasion":"wedding","style":"elegant"}}</tool_call>'
        )
        rewards = tool_call_reward([completion], items=[item])
        assert rewards[0] > 0.5

    def test_invalid_enum_zeroes_reward(self):
        item = {
            "item_type": "tool_call_derivation",
            "expected_arguments": {"occasion": "wedding"},
            "reference_tool_call": (
                '<tool_call>{"name":"search_outfits","arguments":{"occasion":"wedding"}}</tool_call>'
            ),
        }
        completion = (  # noqa: E501
            '<tool_call>{"name":"search_outfits","arguments":{"occasion":"not_a_real_occasion"}}</tool_call>'
        )
        rewards = tool_call_reward([completion], items=[item])
        assert rewards == [0.0]


# ---------------------------------------------------------------------------
# Dispatching reward + TRL contract
# ---------------------------------------------------------------------------
class TestFashionRewardDispatch:
    def test_dispatches_correctly_across_mixed_pool(self):
        pool = canonical_prompt_pool()[:6]
        # Mock: ask_back items pass (1.0), everything else 0 (mimics SFT collapse).
        completions = []
        for row in pool:
            if row["item_type"] == "ask_back":
                completions.append("Bạn muốn mặc cho dịp nào ạ?")
            else:
                completions.append("Không biết.")
        rewards = fashion_reward(completions, items=pool)
        assert len(rewards) == len(pool)
        for row, r in zip(pool, rewards, strict=False):
            if row["item_type"] == "ask_back":
                assert r == 1.0
            else:
                assert r == 0.0

    def test_returns_float_list_of_right_length(self):
        pool = canonical_prompt_pool()[:4]
        completions = ["x"] * 4
        rewards = fashion_reward(completions, items=pool)
        assert isinstance(rewards, list)
        assert len(rewards) == 4
        assert all(isinstance(r, float) for r in rewards)

    def test_reward_in_unit_interval(self):
        pool = build_fashion_prompt_pool(max_per_type=2)
        completions = ["test completion"] * len(pool)
        rewards = fashion_reward(completions, items=pool)
        assert all(0.0 <= r <= 1.0 for r in rewards)

    def test_single_item_kwarg_form(self):
        item = canonical_prompt_pool()[0]
        rewards = fashion_reward(["anything"], item=item)
        assert isinstance(rewards, list) and len(rewards) == 1


class TestCompletionNormalisation:
    def test_string_completion(self):
        item = {"item_type": "coherence", "is_coherent": True}
        assert coherence_reward(["phù hợp"], items=[item]) == [1.0]

    def test_chat_dict_completion(self):
        item = {"item_type": "coherence", "is_coherent": True}
        completion = [{"role": "assistant", "content": "phù hợp"}]
        assert coherence_reward([completion], items=[item]) == [1.0]

    def test_dict_completion(self):
        item = {"item_type": "coherence", "is_coherent": True}
        assert coherence_reward([{"content": "phù hợp"}], items=[item]) == [1.0]


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------
class TestModuleSurface:
    def test_six_reward_funcs(self):
        assert len(FASHION_REWARD_FUNCS) == 6

    def test_scorers_match_item_types(self):
        assert set(SCORERS.keys()) == set(ITEM_TYPES)

    def test_each_reward_func_named(self):
        names = [f.__name__ for f in FASHION_REWARD_FUNCS]
        assert names == [t + "_reward" for t in ITEM_TYPES]
