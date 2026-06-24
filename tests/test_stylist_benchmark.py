"""Tests for stylist benchmark evaluation logic."""

from __future__ import annotations

import pytest

from outfitmatch.stylist.benchmark import (
    compute_format_compliance,
    compute_text_similarity,
    compute_tool_call_f1,
    evaluate_dataset,
    evaluate_sample,
)


# ---------------------------------------------------------------------------
# compute_text_similarity
# ---------------------------------------------------------------------------
def test_text_similarity_identical() -> None:
    assert compute_text_similarity("hello world", "hello world") == pytest.approx(1.0, rel=1e-4)


def test_text_similarity_completely_different() -> None:
    # Token sets are disjoint
    assert compute_text_similarity("abc", "def") == pytest.approx(0.0, abs=1e-6)


def test_text_similarity_partial_overlap() -> None:
    # "hello world" vs "hello universe"
    # shared tokens: hello (1) ; precision = 1/2 , recall = 1/2 ; f1 = 0.5
    assert compute_text_similarity("hello world", "hello universe") == pytest.approx(0.5, rel=1e-4)


# ---------------------------------------------------------------------------
# compute_tool_call_f1
# ---------------------------------------------------------------------------
def test_tool_call_f1_none_when_reference_has_no_tool_call() -> None:
    assert compute_tool_call_f1("some text", "no tool call here") is None


def test_tool_call_f1_zero_when_generated_lacks_tool_call() -> None:
    ref = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    assert compute_tool_call_f1("no tool call", ref) == 0.0


def test_tool_call_f1_perfect_match() -> None:
    ref = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    assert compute_tool_call_f1(ref, ref) == 1.0


def test_tool_call_f1_partial_match() -> None:
    ref = (
        '<tool_call>{"name":"search_outfits",'
        '"arguments":{"occasion":"office","style":"minimalist"}}</tool_call>'
    )
    gen = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    # shared pairs: name, arguments.occasion
    # ref has 3 pairs (name + arg.occasion + arg.style)
    # gen has 2 pairs (name + arg.occasion)
    # overlap=2, precision=1.0, recall=2/3, f1=2*1*2/3/(1+2/3)=0.8
    assert 0 < compute_tool_call_f1(gen, ref) < 1


# ---------------------------------------------------------------------------
# compute_format_compliance
# ---------------------------------------------------------------------------
def test_format_compliance_freetext_reference() -> None:
    assert compute_format_compliance("any text", "reference without tool") == 1


def test_format_compliance_reference_has_tool_generated_valid() -> None:
    ref = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    gen = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    assert compute_format_compliance(gen, ref) == 1


def test_format_compliance_reference_has_tool_generated_invalid() -> None:
    ref = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    gen = "<tool_call>not json</tool_call>"
    assert compute_format_compliance(gen, ref) == 0


# ---------------------------------------------------------------------------
# evaluate_sample
# ---------------------------------------------------------------------------
def test_evaluate_sample_tool_calling_grounded() -> None:
    gen = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    ref = '<tool_call>{"name":"search_outfits","arguments":{"occasion":"office"}}</tool_call>'
    result = evaluate_sample(gen, ref, task_type="tool_calling_grounded")
    assert result["task_type"] == "tool_calling_grounded"
    assert result["tool_call_f1"] == 1.0
    assert result["format_compliance"] == 1
    assert result["text_similarity"] == 1.0


def test_evaluate_sample_stylist_knowledge() -> None:
    gen = "Wear a cotton shirt."
    ref = "Wear a cotton shirt."
    result = evaluate_sample(gen, ref, task_type="stylist_knowledge")
    assert result["task_type"] == "stylist_knowledge"
    assert result["tool_call_f1"] is None
    assert result["format_compliance"] == 1
    assert result["text_similarity"] == 1.0


# ---------------------------------------------------------------------------
# evaluate_dataset with mocked generate_fn
# ---------------------------------------------------------------------------
def test_evaluate_dataset_aggregates_per_task() -> None:
    dataset = [
        {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            "task_type": "task_a",
        },
        {
            "messages": [
                {"role": "user", "content": "bye"},
                {"role": "assistant", "content": "goodbye"},
            ],
            "task_type": "task_b",
        },
    ]

    def generate_fn(messages: list[dict[str, str]]) -> str:
        # Echo the user content back as the generated response for determinism
        return messages[-1]["content"] if messages else ""

    report = evaluate_dataset(dataset, generate_fn)

    assert report["overall"]["count"] == 2
    assert "task_a" in report["per_task"]
    assert "task_b" in report["per_task"]

    # task_a expects "hi there" generated, but we echo "hello"
    # text_similarity of "hello" vs "hi there" is 0.0 (disjoint)
    assert report["per_task"]["task_a"]["mean_text_similarity"] == 0.0
    # task_b expects "goodbye", echo "bye" -> similarity 0.0
    assert report["per_task"]["task_b"]["mean_text_similarity"] == 0.0


def test_evaluate_dataset_max_samples() -> None:
    dataset = [
        {
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
            "etask_type": "task_a",
        },
        {
            "messages": [
                {"role": "user", "content": "bye"},
                {"role": "assistant", "content": "goodbye"},
            ],
            "task_type": "task_b",
        },
    ]

    def generate_fn(messages: list[dict[str, str]]) -> str:
        return messages[-1]["content"] if messages else ""

    report = evaluate_dataset(dataset, generate_fn, max_samples=1)
    assert report["overall"]["count"] == 1
