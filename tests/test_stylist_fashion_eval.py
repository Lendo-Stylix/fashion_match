"""Tests for fashion-knowledge & fashion-logic benchmark (rule-based, reproducible).

These benchmarks evaluate the *stylist core capability* — tri thức thời trang
(fashion knowledge) and logic thời trang (fashion reasoning) — using objective,
deterministic scorers grounded in ``outfitmatch.vocab``. No LLM judge is required.
"""

from __future__ import annotations

import pytest

from outfitmatch.stylist.fashion_eval import (
    ASK_BACK_ITEMS,
    BODY_SHAPE_ADVICE_ITEMS,
    COHERENCE_ITEMS,
    OCCASION_FORMALITY_ITEMS,
    SEASON_ADVICE_ITEMS,
    TOOL_CALL_DERIVATION_ITEMS,
    detect_verdict,
    evaluate_fashion_dataset,
    extract_enum_values,
    score_ask_back,
    score_body_shape_advice,
    score_coherence_judgment,
    score_occasion_formality,
    score_season_advice,
    score_tool_call_derivation,
)
from outfitmatch.stylist.tools import (
    TOOL_CALL_CLOSE,
    TOOL_CALL_OPEN,
    render_search_outfits_tool_call,
)
from outfitmatch.vocab import (
    BODY_SHAPE,
    FORMALITY,
    FORMALITY_LABELS_VI,
    OCCASION,
    SEASON,
    formalities_for_occasion,
)


# ---------------------------------------------------------------------------
# extract_enum_values
# ---------------------------------------------------------------------------
def test_extract_enum_values_english_token() -> None:
    text = "Dịp phỏng vấn nên chọn trang phục formal hoặc smart_casual."
    found = extract_enum_values(text, FORMALITY, FORMALITY_LABELS_VI)
    assert found == {"formal", "smart_casual"}


def test_extract_enum_values_vietnamese_label() -> None:
    text = "Đám cưới cần ăn mặc trang trọng, không nên thường ngày."
    found = extract_enum_values(text, FORMALITY, FORMALITY_LABELS_VI)
    assert "formal" in found  # "trang trọng" -> formal
    assert "casual" in found  # "thường ngày" -> casual


def test_extract_enum_values_case_insensitive_and_none() -> None:
    assert extract_enum_values("nothing relevant here", FORMALITY, FORMALITY_LABELS_VI) == set()
    found = extract_enum_values("FORMAL and Formal", FORMALITY, FORMALITY_LABELS_VI)
    assert found == {"formal"}


# ---------------------------------------------------------------------------
# score_occasion_formality (knowledge)
# ---------------------------------------------------------------------------
def test_occasion_formality_correct_mention_positive() -> None:
    # interview: appropriate = formal & smart_casual
    appropriate = formalities_for_occasion("interview")
    item = {"occasion": "interview", "appropriate_formalities": appropriate}
    gen = "Phỏng vấn nên mặc trang trọng (formal) hoặc lịch sự nhẹ (smart_casual)."
    res = score_occasion_formality(gen, item)
    assert res["correct"] is not None and res["correct"]
    assert res["f1"] == pytest.approx(1.0, rel=1e-3)
    assert res["wrong_formalities"] == []


def test_occasion_formality_only_wrong_mention_zero() -> None:
    appropriate = formalities_for_occasion("interview")  # {formal, smart_casual}
    item = {"occasion": "interview", "appropriate_formalities": appropriate}
    # mentioning only athletic/casual — both inappropriate for interview
    gen = "Đi phỏng vấn cứ mặc thể thao (athletic), thoải mái (casual)."
    res = score_occasion_formality(gen, item)
    assert res["f1"] == pytest.approx(0.0, abs=1e-6)
    assert set(res["wrong_formalities"]) == {"athletic", "casual"}


def test_occasion_formality_no_mention_zero() -> None:
    item = {
        "occasion": "interview",
        "appropriate_formalities": formalities_for_occasion("interview"),
    }
    res = score_occasion_formality("Mặc đồ đẹp là được.", item)
    assert res["f1"] == 0.0
    assert res["correct"] is False
    assert res["recall"] == 0.0


def test_occasion_formality_partial_recalls_only() -> None:
    appropriate = formalities_for_occasion("interview")  # 2 values
    item = {"occasion": "interview", "appropriate_formalities": appropriate}
    gen = "Nên mặc trang trọng (formal)."  # only 1 of 2 appropriate, none wrong
    res = score_occasion_formality(gen, item)
    assert res["recall"] == pytest.approx(0.5, rel=1e-3)
    assert res["precision"] == pytest.approx(1.0, rel=1e-3)
    assert 0 < res["f1"] < 1


# ---------------------------------------------------------------------------
# detect_verdict + score_coherence_judgment (logic)
# ---------------------------------------------------------------------------
def test_detect_verdict_coherent() -> None:
    assert detect_verdict("Outfit này rất phù hợp, hài hoàn.") is True


def test_detect_verdict_incoherent_negation_first() -> None:
    assert detect_verdict("Combo này không phù hợp, lệch tone.") is False


def test_detect_verdict_none_when_ambiguous() -> None:
    assert detect_verdict("Outfit nàyinteresing.") is None


def test_coherence_judgment_correct() -> None:
    item = {"items": [{"category": "top", "formality": "casual"}], "is_coherent": True}
    res = score_coherence_judgment("Phù hợp, outfit gọn gàng.", item)
    assert res["correct"] is True
    assert res["score"] == 1.0


def test_coherence_judgment_incoherent_correct() -> None:
    item = {"items": [], "is_coherent": False}
    res = score_coherence_judgment("Không phù hợp, blazer đi với quần gym.", item)
    assert res["correct"] is True
    assert res["score"] == 1.0


def test_coherence_judgment_wrong_call() -> None:
    item = {"items": [], "is_coherent": False}
    res = score_coherence_judgment("Outfit rất phù hợp.", item)
    assert res["correct"] is False
    assert res["score"] == 0.0


def test_coherence_judgment_undetermined_zero() -> None:
    item = {"items": [], "is_coherent": True}
    res = score_coherence_judgment("Hmm.", item)
    assert res["correct"] is False
    assert res["score"] == 0.0


# ---------------------------------------------------------------------------
# score_ask_back (logic: abstain when occasion missing)
# ---------------------------------------------------------------------------
def test_ask_back_pass_when_asks_question() -> None:
    item = {"missing_required": ["occasion"]}
    gen = "Bạn dự định mặc cho dịp nào? (đi làm, hẹn hò, ...)"
    res = score_ask_back(gen, item)
    assert res["correct"] is True
    assert res["hallucinated_occasion"] is False
    assert res["score"] == 1.0


def test_ask_back_fails_when_hallucinates_occasion_tool_call() -> None:
    item = {"missing_required": ["occasion"]}
    call = render_search_outfits_tool_call({"occasion": "office", "style": "korean"})
    gen = "Để mình tìm cho nhé. " + call
    res = score_ask_back(gen, item)
    assert res["hallucinated_occasion"] is True
    assert res["correct"] is False
    assert res["score"] == 0.0


def test_ask_back_fails_when_silent() -> None:
    item = {"missing_required": ["occasion"]}
    res = score_ask_back("oki", item)
    assert res["correct"] is False
    assert res["score"] == 0.0


def test_ask_back_tool_call_without_occasion_with_question_passes() -> None:
    item = {"missing_required": ["occasion"]}
    call = render_search_outfits_tool_call({"occasion": "office"})  # has occasion -> hallucinated
    # This gen DOES hallucinate occasion -> must fail
    res = score_ask_back(call, item)
    assert res["correct"] is False


# ---------------------------------------------------------------------------
# score_tool_call_derivation (logic: profile -> valid tool call)
# ---------------------------------------------------------------------------
def test_tool_call_derivation_perfect() -> None:
    expected = {"occasion": "wedding", "style": "elegant"}
    ref = render_search_outfits_tool_call(expected)
    item = {"expected_arguments": expected, "reference_tool_call": ref}
    res = score_tool_call_derivation(ref, item)
    assert res["tool_call_f1"] == 1.0
    assert res["enum_valid"] is True
    assert res["score"] == 1.0


def test_tool_call_derivation_hallucinated_enum_zero() -> None:
    expected = {"occasion": "wedding", "style": "elegant"}
    ref = render_search_outfits_tool_call(expected)
    item = {"expected_arguments": expected, "reference_tool_call": ref}
    # hallucinated style value -> enum invalid
    bad = (
        TOOL_CALL_OPEN
        + '{"name":"search_outfits","arguments":{"occasion":"wedding","style":"disco"}}'
        + TOOL_CALL_CLOSE
    )
    res = score_tool_call_derivation(bad, item)
    assert res["enum_valid"] is False
    assert res["score"] == 0.0


def test_tool_call_derivation_no_tool_call_zero() -> None:
    expected = {"occasion": "wedding"}
    ref = render_search_outfits_tool_call(expected)
    item = {"expected_arguments": expected, "reference_tool_call": ref}
    res = score_tool_call_derivation("Tôi chưa hiểu lắm.", item)
    assert res["tool_call_f1"] == 0.0
    assert res["enum_valid"] is False
    assert res["score"] == 0.0


# ---------------------------------------------------------------------------
# Item-bank integrity (derive items from vocab, reproducible)
# ---------------------------------------------------------------------------
def test_occasion_formality_items_nonempty_and_valid() -> None:
    assert len(OCCASION_FORMALITY_ITEMS) >= 5
    for item in OCCASION_FORMALITY_ITEMS:
        assert item["occasion"] in OCCASION
        assert item["appropriate_formalities"]  # non-empty
        assert set(item["appropriate_formalities"]) <= set(FORMALITY)
        assert "prompt" in item and "reference" in item


def test_coherence_items_have_both_labels() -> None:
    coherent = [i for i in COHERENCE_ITEMS if i["is_coherent"]]
    incoherent = [i for i in COHERENCE_ITEMS if not i["is_coherent"]]
    assert len(coherent) >= 1
    assert len(incoherent) >= 1
    for item in COHERENCE_ITEMS:
        assert "items" in item and "prompt" in item and "reference" in item


def test_ask_back_items_all_missing_occasion() -> None:
    assert len(ASK_BACK_ITEMS) >= 2
    for item in ASK_BACK_ITEMS:
        assert "occasion" in item["missing_required"]
        assert "prompt" in item


def test_tool_call_derivation_items_reference_renders() -> None:
    assert len(TOOL_CALL_DERIVATION_ITEMS) >= 2
    for item in TOOL_CALL_DERIVATION_ITEMS:
        # the reference tool call must be parseable & valid
        from outfitmatch.stylist.validation import extract_tool_calls, validate_tool_calls

        calls = extract_tool_calls(item["reference_tool_call"])
        assert calls, item
        ok, _ = validate_tool_calls(item["reference_tool_call"])
        assert ok, item
        assert set(item["expected_arguments"]) >= {"occasion"}


# ---------------------------------------------------------------------------
# evaluate_fashion_dataset aggregation
# ---------------------------------------------------------------------------
def test_evaluate_fashion_dataset_aggregates_by_type() -> None:
    # type tag required on each record for grouping
    typed = []
    for it in OCCASION_FORMALITY_ITEMS[:3]:
        typed.append(
            {
                **it,
                "item_type": "occasion_formality",
                "messages": [{"role": "user", "content": it["prompt"]}],
            }
        )
    for it in ASK_BACK_ITEMS[:2]:
        typed.append(
            {**it, "item_type": "ask_back", "messages": [{"role": "user", "content": it["prompt"]}]}
        )

    # a generate_fn that always asks back (should ace ask_back, fail formality)
    def generate_fn(messages):
        return "Bạn muốn mặc cho dịp nào ạ?"

    report = evaluate_fashion_dataset(typed, generate_fn)
    assert "overall" in report and "per_task" in report
    assert "occasion_formality" in report["per_task"]
    assert "ask_back" in report["per_task"]
    assert report["per_task"]["ask_back"]["mean_score"] == 1.0
    assert report["per_task"]["occasion_formality"]["mean_score"] == 0.0
    assert report["overall"]["count"] == len(typed)


# ---------------------------------------------------------------------------
# Knowledge scorer: body-shape advice
# ---------------------------------------------------------------------------
def _pear_item() -> dict:
    return next(i for i in BODY_SHAPE_ADVICE_ITEMS if i["body_shape"] == "pear")


def test_body_shape_advice_correct_partial() -> None:
    item = _pear_item()
    # matches positives "nhấn eo" and "a-line" (substring of "a-line"); no negative
    gen = "Dáng lê nên nhấn eo và mặc chân váy a-line."
    res = score_body_shape_advice(gen, item)
    assert res["correct"] is True
    assert res["score"] > 0.0
    assert any("nhấn eo" in k for k in res["positives_mentioned"])


def test_body_shape_advice_wrong_negative_fails() -> None:
    item = _pear_item()
    gen = "Dáng lê nên mặc quần bó sát hông."  # negative present, no positive
    res = score_body_shape_advice(gen, item)
    assert res["correct"] is False
    assert res["score"] >= 0.0
    assert res["negatives_mentioned"].count("quần bó sát hông") == 1


def test_body_shape_advice_empty_zero() -> None:
    res = score_body_shape_advice("oki", _pear_item())
    assert res["correct"] is False
    assert res["score"] == 0.0


def test_body_shape_advice_items_cover_all_shapes() -> None:
    assert len(BODY_SHAPE_ADVICE_ITEMS) == len(BODY_SHAPE)
    for it in BODY_SHAPE_ADVICE_ITEMS:
        assert it["body_shape"] in BODY_SHAPE
        assert it["positive_keywords"]
        assert it["negative_keywords"]
        assert "prompt" in it and "reference" in it


# ---------------------------------------------------------------------------
# Knowledge scorer: season fabric/layering advice
# ---------------------------------------------------------------------------
def _summer_item() -> dict:
    return next(i for i in SEASON_ADVICE_ITEMS if i["season"] == "summer")


def test_season_advice_correct() -> None:
    gen = "Mùa hè nên mặc vải cotton và linen thoáng mát, màu sáng."
    res = score_season_advice(gen, _summer_item())
    assert res["correct"] is True
    assert res["score"] > 0.0


def test_season_advice_wrong_negative() -> None:
    gen = "Mùa hè cứ mặc áo len dạ dày cho ấm."  # negatives; no positive
    res = score_season_advice(gen, _summer_item())
    assert res["correct"] is False
    assert res["score"] == 0.0


def test_season_advice_items_cover_all_seasons() -> None:
    assert len(SEASON_ADVICE_ITEMS) == len(SEASON)
    for it in SEASON_ADVICE_ITEMS:
        assert it["season"] in SEASON
        assert it["positive_keywords"]
        assert it["negative_keywords"]


def test_evaluate_fashion_dataset_includes_new_types() -> None:
    apple = next(i for i in BODY_SHAPE_ADVICE_ITEMS if i["body_shape"] == "apple")
    winter = next(i for i in SEASON_ADVICE_ITEMS if i["season"] == "winter")
    typed = [
        {
            **apple,
            "item_type": "body_shape_advice",
            "messages": [{"role": "user", "content": apple["prompt"]}],
        },
        {
            **winter,
            "item_type": "season_advice",
            "messages": [{"role": "user", "content": winter["prompt"]}],
        },
    ]

    def gen_fn(messages):
        return "ko biết"

    rep = evaluate_fashion_dataset(typed, gen_fn)
    assert "body_shape_advice" in rep["per_task"]
    assert "season_advice" in rep["per_task"]
    assert rep["per_task"]["body_shape_advice"]["mean_score"] == 0.0
    assert rep["overall"]["count"] == 2


# ---------------------------------------------------------------------------
# Regression tests — FORMALITY alias normalisation
# ---------------------------------------------------------------------------
def test_occasion_formality_smart_casual_space_variant() -> None:
    """Moi hinh viet smart casual (space) -> alias credit smart_casual band."""
    appropriate = formalities_for_occasion("interview")
    item = {"occasion": "interview", "appropriate_formalities": appropriate}
    gen = "Phong van nen mac smart casual."
    res = score_occasion_formality(gen, item)
    assert res["f1"] > 0.0


def test_occasion_formality_business_casual_not_credit_casual() -> None:
    """business casual khong duoc credit nhu casual (precision bug fix)."""
    appropriate = formalities_for_occasion("wedding")
    item = {"occasion": "wedding", "appropriate_formalities": appropriate}
    gen = "Dam cuoi nen mac business casual hoac semi-formal."
    res = score_occasion_formality(gen, item)
    assert "casual" not in res.get("wrong_formalities", [])
    assert res["recall"] > 0.0
    assert "smart_casual" in res["wrong_formalities"]


def test_occasion_formality_semi_formal_underscore() -> None:
    """semi_formal underscore variant -> formal canonical."""
    appropriate = formalities_for_occasion("wedding")
    item = {"occasion": "wedding", "appropriate_formalities": appropriate}
    gen = "Dam cuoi nen mac semi_formal."
    res = score_occasion_formality(gen, item)
    assert res["f1"] == pytest.approx(1.0, rel=1e-3)


def test_extract_enum_values_with_aliases_param() -> None:
    """extract_enum_values accepts aliases and normalises text before matching."""
    text = "smart casual hoac business casual"
    found = extract_enum_values(
        text,
        FORMALITY,
        FORMALITY_LABELS_VI,
        aliases=[
            ("business casual", "smart_casual"),
            ("smart casual", "smart_casual"),
        ],
    )
    assert found == {"smart_casual"}


def test_body_shape_advice_chu_a_variant() -> None:
    """va y chu A phai credit positive keyword chan va a cua pear."""
    item = {
        "body_shape": "pear",
        "positive_keywords": ("nhấn eo", "chân váy a", "a-line", "high waist", "áo phồng tay"),
        "negative_keywords": ("quần bó sát hông",),
    }
    gen = "Nên nhấn eo và mặc váy chữ A."
    res = score_body_shape_advice(gen, item)
    assert "chân váy a" in res["positives_mentioned"]
    assert res["score"] > 0.0


def test_season_advice_chong_nuoc_alias() -> None:
    """chong nuoc -> vai chong nuoc positive for rainy."""
    item = {
        "season": "rainy",
        "positive_keywords": (
            "áo mưa",
            "chống trượt",
            "nhiều lớp nhẹ",
            "giày bọc",
            "vải chống nước",
        ),
        "negative_keywords": ("suede", "da thật", "giày vải", "mỏng dễ thấm"),
    }
    gen = "Nên mặc áo có vải chống nước."
    res = score_season_advice(gen, item)
    assert "vải chống nước" in res["positives_mentioned"]
    assert res["correct"] is True
