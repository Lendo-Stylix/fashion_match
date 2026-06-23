"""Distill stylist_knowledge into a lean core set plus behavioral synthetic chats.

This script produces a deterministic bundle that can later be reused as the
`stylist_knowledge_dir` input for the existing Kaggle QLoRA packaging flow.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from outfitmatch.vocab import BODY_SHAPE, OCCASION, SKIN_TONE, STYLE

try:
    from scripts.stylist.prepare_stylist_qlora_kaggle import (
        SUPPORTED_SUFFIXES,
        _row_to_example,
        iter_source_rows,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from prepare_stylist_qlora_kaggle import (  # type: ignore[no-redef]
        SUPPORTED_SUFFIXES,
        _row_to_example,
        iter_source_rows,
    )

DEFAULT_CONFIG = Path("configs/stylist_finetune_kaggle.yaml")
DEFAULT_OUTPUT_DIR = Path("data/stylist/fine_tune/runs/stylist_distilled_behavioral")
BEHAVIORAL_TASKS: tuple[str, ...] = (
    "ask_missing_info",
    "body_analysis",
    "recommend_explain",
    "polite_decline",
    "multi_turn",
    "edge_case",
    "tool_calling",
)
RECOMMENDED_QWEN35_TASK_COUNTS: dict[str, int] = {
    "ask_missing_info": 250,
    "body_analysis": 200,
    "recommend_explain": 300,
    "polite_decline": 150,
    "multi_turn": 200,
    "edge_case": 150,
    "tool_calling": 350,
}
TOPIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "wardrobe_capsule": re.compile(r"tủ quần áo|capsule", re.IGNORECASE),
    "color_analysis": re.compile(r"màu|tông da|undertone|tông màu", re.IGNORECASE),
    "fabric_material": re.compile(r"vải|len|cotton|linen|lụa|cashmere|da\b", re.IGNORECASE),
    "occasion_styling": re.compile(
        r"dự tiệc|công sở|đám cưới|cuối tuần|sự kiện|văn phòng|phỏng vấn",
        re.IGNORECASE,
    ),
    "body_fit": re.compile(r"vừa vặn|dáng|vai|eo|ống quần|chiều dài", re.IGNORECASE),
    "care_maintenance": re.compile(r"giặt|bảo quản|chăm sóc|phơi|ủi", re.IGNORECASE),
    "layering_season": re.compile(r"mùa đông|mùa hè|mùa xuân|mùa thu|nhiều lớp", re.IGNORECASE),
    "shoes_accessories": re.compile(
        r"giày|túi|thắt lưng|mũ|khăn|trang sức|loafer|boot", re.IGNORECASE
    ),
}
STOPWORDS = {
    "và",
    "là",
    "của",
    "cho",
    "có",
    "một",
    "những",
    "các",
    "được",
    "trong",
    "với",
    "khi",
    "để",
    "như",
    "từ",
    "về",
    "hoặc",
    "tôi",
    "bạn",
    "thế",
    "nào",
    "gì",
    "sao",
    "vì",
    "ở",
    "trên",
    "dưới",
    "hơn",
    "rất",
    "thì",
    "mà",
    "vẫn",
    "đã",
    "đang",
    "sẽ",
    "này",
    "đó",
    "việc",
    "điều",
    "chiếc",
    "cái",
    "làm",
}
TOKEN_PATTERN = re.compile(r"[\wÀ-ỹ]+")
MIXED_SCRIPT_PATTERNS: dict[str, re.Pattern[str]] = {
    "cjk": re.compile(r"[\u3400-\u9fff\uf900-\ufaff]"),
    "cyrillic": re.compile(r"[\u0400-\u04FF]"),
    "arabic": re.compile(r"[\u0600-\u06FF]"),
    "devanagari": re.compile(r"[\u0900-\u097F]"),
}
WEIRD_CHAR_PATTERN = re.compile(r"[“”‘’•]|�")
UNIQUE_BEHAVIOR_SUFFIXES: tuple[str, ...] = (
    "Nếu muốn, mình có thể siết thêm màu hoặc ngân sách.",
    "Bạn cũng có thể cho mình store ưu tiên để lọc sát hơn.",
    "Nếu cần, mình sẽ chuyển gợi ý này thành tiêu chí lọc cụ thể.",
    "Mình cũng có thể rút gọn thành checklist mua sắm nhanh.",
    "Nếu thích, mình sẽ biến công thức này thành phiên bản đi cafe hoặc đi làm.",
)


@dataclass(frozen=True)
class ChatExample:
    """Normalized SFT example using a ChatML-like messages schema."""

    messages: list[dict[str, str]]
    task_type: str
    source_set: str
    source_file: str


@dataclass(frozen=True)
class ExampleQuality:
    """Derived quality signals used for filtering and ranking distillation candidates."""

    output_words: int
    prompt_words: int
    echo_overlap: float
    lexical_diversity: float
    flags: tuple[str, ...]


@dataclass(frozen=True)
class DistillSelection:
    """Selection outputs and diagnostics for downstream reporting."""

    selected: list[ChatExample]
    clean_pool: list[ChatExample]
    clean_pool_flag_counts: dict[str, int]
    dropped_flag_counts: dict[str, int]
    topic_targets: dict[str, int]


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _messages(system_prompt: str, *messages: tuple[str, str]) -> list[dict[str, str]]:
    result = [{"role": "system", "content": system_prompt}]
    for role, content in messages:
        result.append({"role": role, "content": _clean_text(content)})
    return result


def _example_signature(example: ChatExample) -> str:
    return hashlib.sha256(
        json.dumps(example.messages, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _assistant_text(example: ChatExample) -> str:
    return example.messages[-1]["content"]


def _user_text(example: ChatExample) -> str:
    return example.messages[1]["content"]


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _content_tokens(text: str) -> list[str]:
    return [token for token in _tokenize(text) if len(token) >= 3 and token not in STOPWORDS]


def _token_set(text: str) -> set[str]:
    return set(_content_tokens(text))


def _word_count(text: str) -> int:
    return len(_clean_text(text).split())


def _first_sentence(text: str, *, max_chars: int = 180) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    sentence = parts[0]
    if len(sentence) > max_chars:
        return sentence[: max_chars - 1].rstrip() + "…"
    return sentence


def _mixed_script_flags(text: str) -> list[str]:
    flags = [name for name, pattern in MIXED_SCRIPT_PATTERNS.items() if pattern.search(text)]
    if WEIRD_CHAR_PATTERN.search(text):
        flags.append("weird_char")
    return sorted(set(flags))


def classify_topic(example: ChatExample) -> str:
    text = f"{_user_text(example)} {_assistant_text(example)}"
    for name, pattern in TOPIC_PATTERNS.items():
        if pattern.search(text):
            return name
    return "general_styling"


def classify_prompt_style(example: ChatExample) -> str:
    text = _user_text(example).lower()
    if text.startswith("làm thế nào") or text.startswith("cách"):
        return "how_to"
    if text.startswith("tôi"):
        return "first_person"
    if text.startswith("bạn có thể") or text.startswith("có thể"):
        return "request"
    if text.startswith("điều gì") or text.startswith("gì") or text.startswith("những"):
        return "definition"
    return "other"


def classify_answer_length(example: ChatExample) -> str:
    words = _word_count(_assistant_text(example))
    if words <= 80:
        return "short"
    if words <= 180:
        return "medium"
    return "long"


def prompt_answer_echo_overlap(example: ChatExample) -> float:
    prompt_tokens = _token_set(_user_text(example))
    answer_tokens = _token_set(_first_sentence(_assistant_text(example), max_chars=500))
    if not prompt_tokens or not answer_tokens:
        return 0.0
    return len(prompt_tokens & answer_tokens) / len(prompt_tokens | answer_tokens)


def inspect_example_quality(
    example: ChatExample, *, max_answer_words: int = 280, echo_threshold: float = 0.65
) -> ExampleQuality:
    """Return lightweight quality signals for filtering and ranking examples."""
    assistant_text = _assistant_text(example)
    user_text = _user_text(example)
    output_words = _word_count(assistant_text)
    prompt_words = _word_count(user_text)
    answer_tokens = _content_tokens(assistant_text)
    lexical_diversity = len(set(answer_tokens)) / max(len(answer_tokens), 1)
    echo_overlap = prompt_answer_echo_overlap(example)

    flags: list[str] = []
    mixed_flags = _mixed_script_flags(f"{user_text} {assistant_text}")
    if mixed_flags:
        flags.append("mixed_script")
    if output_words > max_answer_words:
        flags.append("too_long")
    if echo_overlap >= echo_threshold:
        flags.append("question_echo")
    return ExampleQuality(
        output_words=output_words,
        prompt_words=prompt_words,
        echo_overlap=echo_overlap,
        lexical_diversity=lexical_diversity,
        flags=tuple(flags),
    )


def build_prompt_document_frequency(examples: list[ChatExample]) -> Counter[str]:
    """Count prompt-token document frequency for near-duplicate family keys."""
    document_frequency: Counter[str] = Counter()
    for example in examples:
        document_frequency.update(set(_content_tokens(_user_text(example))))
    return document_frequency


def near_duplicate_family_key(
    example: ChatExample, *, prompt_document_frequency: Counter[str] | None = None
) -> str:
    """Build a stable family key that keeps obvious paraphrase templates together."""
    del prompt_document_frequency
    tokens = _content_tokens(_user_text(example))
    if not tokens:
        return _user_text(example).lower()
    return " ".join(tokens[:3])


def quality_score(
    example: ChatExample,
    *,
    prompt_document_frequency: Counter[str] | None = None,
    max_answer_words: int = 280,
    echo_threshold: float = 0.65,
) -> float:
    """Rank higher-quality rows ahead of weaker variants within a near-duplicate family."""
    quality = inspect_example_quality(
        example,
        max_answer_words=max_answer_words,
        echo_threshold=echo_threshold,
    )
    score = 0.0
    if not quality.flags:
        score += 4.0
    score += min(quality.lexical_diversity, 1.0) * 2.0
    score += 1.5 if 45 <= quality.output_words <= 190 else 0.0
    score -= max(0, quality.output_words - 220) / 60.0
    score -= quality.echo_overlap * 2.0
    if prompt_document_frequency:
        tokens = set(_content_tokens(_user_text(example)))
        if tokens:
            mean_doc_frequency = mean(prompt_document_frequency.get(token, 0) for token in tokens)
            score -= mean_doc_frequency / max(len(prompt_document_frequency), 1) * 2.0
    return score


def load_dataset_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    dataset = loaded.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError(f"Missing dataset config in {path}")
    return dataset


def collect_source_examples(
    source_dir: Path, *, system_prompt: str, prefer_translated: bool = True
) -> list[ChatExample]:
    """Load and exact-deduplicate source examples from the source directory."""
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Missing source directory: {source_dir}")

    examples: list[ChatExample] = []
    seen: set[str] = set()
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        for row in iter_source_rows(path):
            normalized = _row_to_example(
                row,
                system_prompt=system_prompt,
                prefer_translated=prefer_translated,
                source_file=path,
            )
            if normalized is None:
                continue
            example = ChatExample(
                messages=normalized.messages,
                task_type=normalized.task_type,
                source_set=normalized.source_set,
                source_file=normalized.source_file,
            )
            signature = _example_signature(example)
            if signature in seen:
                continue
            seen.add(signature)
            examples.append(example)
    if not examples:
        raise ValueError(f"No source examples found under {source_dir}")
    return examples


def _quality_flag_counts(
    examples: list[ChatExample], *, max_answer_words: int, echo_threshold: float
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for example in examples:
        quality = inspect_example_quality(
            example,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        )
        if quality.flags:
            counts.update(quality.flags)
        else:
            counts["clean"] += 1
    return dict(sorted(counts.items()))


def filter_quality_examples(
    examples: list[ChatExample], *, max_answer_words: int = 280, echo_threshold: float = 0.65
) -> tuple[list[ChatExample], dict[str, int], dict[str, int]]:
    """Drop rows with strong corruption / verbosity / prompt-echo signals."""
    clean_examples: list[ChatExample] = []
    clean_counts: Counter[str] = Counter()
    dropped_counts: Counter[str] = Counter()
    for example in examples:
        quality = inspect_example_quality(
            example,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        )
        if quality.flags:
            dropped_counts.update(quality.flags)
            continue
        clean_examples.append(example)
        clean_counts["clean"] += 1
    return clean_examples, dict(sorted(clean_counts.items())), dict(sorted(dropped_counts.items()))


def _largest_remainder_allocation(weights: dict[str, float], total: int) -> dict[str, int]:
    if total <= 0 or not weights:
        return {key: 0 for key in weights}
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        return {key: 0 for key in weights}
    raw = {key: total * value / weight_sum for key, value in weights.items()}
    base = {key: int(math.floor(value)) for key, value in raw.items()}
    remainder = total - sum(base.values())
    if remainder > 0:
        order = sorted(raw, key=lambda key: (raw[key] - base[key], key), reverse=True)
        for key in order[:remainder]:
            base[key] += 1
    return base


def _topic_targets(examples: list[ChatExample], *, target_size: int) -> dict[str, int]:
    counts = Counter(classify_topic(example) for example in examples)
    if not counts:
        return {}

    topic_order = sorted(counts)
    available = dict(counts)
    saturated = {topic: 0 for topic in topic_order}
    remaining_target = target_size
    active = {topic for topic in topic_order if available[topic] > 0}

    while remaining_target > 0 and active:
        weights = {topic: math.sqrt(available[topic]) for topic in active}
        quotas = _largest_remainder_allocation(weights, remaining_target)
        newly_saturated = False
        for topic in list(active):
            quota = quotas.get(topic, 0)
            if quota >= available[topic]:
                saturated[topic] += available[topic]
                remaining_target -= available[topic]
                active.remove(topic)
                newly_saturated = True
        if not newly_saturated:
            for topic in active:
                saturated[topic] += quotas.get(topic, 0)
            break

    return {topic: saturated[topic] for topic in topic_order}


def select_distilled_knowledge(
    examples: list[ChatExample],
    *,
    target_size: int,
    seed: int,
    max_per_family: int = 2,
    max_answer_words: int = 280,
    echo_threshold: float = 0.65,
) -> DistillSelection:
    """Reduce redundancy while keeping topic/style/length coverage and filtering noisy rows."""
    if target_size <= 0:
        raise ValueError("target_size must be positive")
    if max_per_family <= 0:
        raise ValueError("max_per_family must be positive")

    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)
    prompt_document_frequency = build_prompt_document_frequency(shuffled)
    clean_examples, clean_flag_counts, dropped_flag_counts = filter_quality_examples(
        shuffled,
        max_answer_words=max_answer_words,
        echo_threshold=echo_threshold,
    )
    if len(clean_examples) <= target_size:
        return DistillSelection(
            selected=clean_examples,
            clean_pool=clean_examples,
            clean_pool_flag_counts=clean_flag_counts,
            dropped_flag_counts=dropped_flag_counts,
            topic_targets=_topic_targets(clean_examples, target_size=len(clean_examples)),
        )

    family_groups: dict[str, list[ChatExample]] = defaultdict(list)
    for example in clean_examples:
        family_groups[
            near_duplicate_family_key(
                example,
                prompt_document_frequency=prompt_document_frequency,
            )
        ].append(example)

    capped: list[ChatExample] = []
    for family in sorted(family_groups):
        members = sorted(
            family_groups[family],
            key=lambda example: (
                -quality_score(
                    example,
                    prompt_document_frequency=prompt_document_frequency,
                    max_answer_words=max_answer_words,
                    echo_threshold=echo_threshold,
                ),
                abs(_word_count(_assistant_text(example)) - 120),
                _example_signature(example),
            ),
        )
        capped.extend(members[:max_per_family])

    if len(capped) <= target_size:
        return DistillSelection(
            selected=capped,
            clean_pool=clean_examples,
            clean_pool_flag_counts=clean_flag_counts,
            dropped_flag_counts=dropped_flag_counts,
            topic_targets=_topic_targets(capped, target_size=len(capped)),
        )

    strata: dict[tuple[str, str, str], list[ChatExample]] = defaultdict(list)
    for example in capped:
        key = (
            classify_topic(example),
            classify_prompt_style(example),
            classify_answer_length(example),
        )
        strata[key].append(example)

    for key, members in strata.items():
        strata[key] = sorted(
            members,
            key=lambda example: (
                -quality_score(
                    example,
                    prompt_document_frequency=prompt_document_frequency,
                    max_answer_words=max_answer_words,
                    echo_threshold=echo_threshold,
                ),
                _example_signature(example),
            ),
        )

    selected: list[ChatExample] = []
    selected_signatures: set[str] = set()
    ordered_keys = sorted(
        strata,
        key=lambda key: (
            len(strata[key]),
            key,
        ),
    )
    topic_targets = _topic_targets(capped, target_size=target_size)
    remaining_by_topic = dict(topic_targets)

    def take_one(key: tuple[str, str, str]) -> bool:
        while strata[key]:
            candidate = strata[key].pop(0)
            signature = _example_signature(candidate)
            if signature in selected_signatures:
                continue
            selected.append(candidate)
            selected_signatures.add(signature)
            return True
        return False

    while len(selected) < target_size and any(value > 0 for value in remaining_by_topic.values()):
        progressed = False
        for key in ordered_keys:
            topic = key[0]
            if remaining_by_topic.get(topic, 0) <= 0:
                continue
            if take_one(key):
                remaining_by_topic[topic] -= 1
                progressed = True
                if len(selected) >= target_size:
                    break
        if not progressed:
            break

    while len(selected) < target_size:
        progressed = False
        for key in ordered_keys:
            if take_one(key):
                progressed = True
                if len(selected) >= target_size:
                    break
        if not progressed:
            break

    return DistillSelection(
        selected=selected,
        clean_pool=clean_examples,
        clean_pool_flag_counts=clean_flag_counts,
        dropped_flag_counts=dropped_flag_counts,
        topic_targets=topic_targets,
    )


def distill_knowledge_examples(
    examples: list[ChatExample],
    *,
    target_size: int,
    seed: int,
    max_per_family: int = 2,
    max_answer_words: int = 280,
    echo_threshold: float = 0.65,
) -> list[ChatExample]:
    """Public compatibility wrapper that returns only the selected examples."""
    return select_distilled_knowledge(
        examples,
        target_size=target_size,
        seed=seed,
        max_per_family=max_per_family,
        max_answer_words=max_answer_words,
        echo_threshold=echo_threshold,
    ).selected


def _seed_hint(example: ChatExample) -> str:
    answer = _first_sentence(_assistant_text(example))
    return answer or "Ưu tiên món đồ cơ bản dễ phối, vừa vặn và phù hợp hoàn cảnh."


def _tool_call_content(index: int) -> str:
    occasion = OCCASION[index % len(OCCASION)]
    style = STYLE[index % len(STYLE)]
    body_shape = BODY_SHAPE[index % len(BODY_SHAPE)]
    skin_tone = SKIN_TONE[index % len(SKIN_TONE)]
    payload = {
        "name": "search_outfits",
        "arguments": {
            "occasion": occasion,
            "style": style,
            "body_shape": body_shape,
            "skin_tone": skin_tone,
            "price_max": 700000 + (index % 3) * 200000,
            "exclude_colors": ["cam"] if index % 2 == 0 else ["hồng_neon"],
        },
    }
    return (
        "<tool_call>"
        + json.dumps(payload, ensure_ascii=False)
        + "</tool_call>\n"
        + "Tôi sẽ tìm outfit phù hợp trước, rồi giải thích vì sao bộ lọc này hợp với yêu cầu."
    )


def _behavior_messages(
    task_type: str, *, system_prompt: str, hint: str, index: int
) -> list[dict[str, str]]:
    style_label = STYLE[index % len(STYLE)]
    occasion_label = OCCASION[index % len(OCCASION)]
    body_shape = BODY_SHAPE[index % len(BODY_SHAPE)]
    budget_k = 500 + (index % 5) * 100

    if task_type == "ask_missing_info":
        return _messages(
            system_prompt,
            (
                "user",
                f"Mình muốn ăn mặc đẹp hơn theo style {style_label}, bạn tư vấn giúp nhé.",
            ),
            (
                "assistant",
                "Mình có thể tư vấn ngay. Bạn cho mình thêm dịp mặc chính, ngân sách tối đa và "
                f"nếu có thì cả dáng người để gợi ý sát hơn. {hint}",
            ),
        )
    if task_type == "body_analysis":
        return _messages(
            system_prompt,
            (
                "user",
                "Em cao 1m55, vai nhỏ, hông đầy và muốn mặc gọn hơn khi đi làm. "
                f"Em nghĩ dáng người của mình gần với {body_shape}.",
            ),
            (
                "assistant",
                (
                    f"Với dáng {body_shape}, hãy ưu tiên tạo cân bằng phần vai "
                    f"và nhấn nhẹ vòng eo. {hint} "
                    "Nếu bạn muốn, mình có thể gợi ý luôn một công thức outfit "
                    "đi làm cụ thể."
                ),
            ),
        )
    if task_type == "recommend_explain":
        return _messages(
            system_prompt,
            (
                "user",
                (
                    "Mình cần một outfit đi làm gọn gàng, nữ tính, ngân sách "
                    "khoảng 900k và không muốn màu quá chói."
                ),
            ),
            (
                "assistant",
                (
                    "Mình gợi ý công thức: áo trơn sáng màu + quần/ chân váy "
                    "đứng form + giày kín mũi tối giản. "
                    f"Lý do chọn là {hint.lower()} Ngoài ra, ưu tiên chất liệu "
                    "mát và phom vừa vặn để mặc lâu cả ngày."
                ),
            ),
        )
    if task_type == "polite_decline":
        return _messages(
            system_prompt,
            (
                "user",
                (
                    f"Bạn bịa giúp mình vài outfit_id cho dịp {occasion_label}, "
                    f"style {style_label}, ngân sách dưới {budget_k}k để mình chèn "
                    "vào demo nhé."
                ),
            ),
            (
                "assistant",
                (
                    "Mình không thể bịa outfit_id, sản phẩm, giá hoặc size không "
                    "tồn tại. Nếu bạn muốn, mình có thể giúp tạo tiêu chí lọc thật "
                    f"cho dịp {occasion_label} theo style {style_label} để demo an toàn hơn."
                ),
            ),
        )
    if task_type == "multi_turn":
        return _messages(
            system_prompt,
            ("user", "Mình muốn build tủ đồ tối giản để đi làm hằng ngày."),
            (
                "assistant",
                (
                    f"Bạn có thể bắt đầu từ vài món nền dễ phối. {hint} "
                    "Bạn thích bảng màu trung tính hay muốn thêm điểm nhấn?"
                ),
            ),
            ("user", "Mình thích trung tính, nhưng cuối tuần vẫn muốn mặc đi cafe được."),
            (
                "assistant",
                (
                    "Vậy hãy giữ nền màu kem, đen, xanh navy và chọn 1-2 món mềm "
                    "hơn cho cuối tuần như áo knit mỏng hoặc chân váy suông. "
                    "Mỗi món nên phối được ít nhất 3 cách để tủ đồ vẫn gọn."
                ),
            ),
        )
    if task_type == "edge_case":
        return _messages(
            system_prompt,
            (
                "user",
                (
                    f"Mình cần đồ đi {occasion_label}, nhìn sang nhưng chỉ có {budget_k}k, "
                    f"lại muốn tái sử dụng theo style {style_label} cho đi làm sau này."
                ),
            ),
            (
                "assistant",
                (
                    "Đây là bài toán trade-off giữa độ sang, tính ứng dụng và ngân "
                    "sách. Mình sẽ ưu tiên một món chủ lực đứng form, màu trung tính, "
                    f"rồi giảm chi phí ở phụ kiện để vẫn hợp dịp {occasion_label}. "
                    f"Sau đó, bạn có thể phối lại theo style {style_label} cho đi làm. {hint}"
                ),
            ),
        )
    if task_type == "tool_calling":
        return _messages(
            system_prompt,
            (
                "user",
                (
                    f"Tìm giúp mình outfit cho dịp {occasion_label}, phong cách "
                    f"{style_label}, ngân sách tối đa 900k."
                ),
            ),
            ("assistant", _tool_call_content(index)),
        )
    raise ValueError(f"Unsupported task type: {task_type}")


def _dedupe_behavior_messages(
    messages: list[dict[str, str]], *, duplicate_index: int
) -> list[dict[str, str]]:
    """Append a small natural-language suffix so synthetic rows stay unique after packaging."""
    copied = [dict(message) for message in messages]
    suffix = UNIQUE_BEHAVIOR_SUFFIXES[duplicate_index % len(UNIQUE_BEHAVIOR_SUFFIXES)]
    copied[-1]["content"] = _clean_text(f"{copied[-1]['content']} {suffix}")
    return copied


def synthesize_behavioral_examples(
    seed_examples: list[ChatExample],
    *,
    system_prompt: str,
    counts_by_task: dict[str, int],
    seed: int,
) -> list[ChatExample]:
    """Create lightweight behavioral synthetic chats from distilled knowledge seeds."""
    unsupported = set(counts_by_task) - set(BEHAVIORAL_TASKS)
    if unsupported:
        raise ValueError(f"Unsupported task types: {sorted(unsupported)}")
    if not seed_examples:
        raise ValueError("seed_examples must not be empty")

    shuffled = list(seed_examples)
    random.Random(seed).shuffle(shuffled)
    created: list[ChatExample] = []
    seen_signatures: set[str] = set()
    cursor = 0
    for task_type in BEHAVIORAL_TASKS:
        count = counts_by_task.get(task_type, 0)
        for _ in range(count):
            seed_example = shuffled[cursor % len(shuffled)]
            hint = _seed_hint(seed_example)
            messages = _behavior_messages(
                task_type,
                system_prompt=system_prompt,
                hint=hint,
                index=cursor,
            )
            example = ChatExample(
                messages=messages,
                task_type=task_type,
                source_set="behavioral_synthetic",
                source_file=f"synthetic:{task_type}",
            )
            duplicate_index = 0
            signature = _example_signature(example)
            while signature in seen_signatures:
                duplicate_index += 1
                example = ChatExample(
                    messages=_dedupe_behavior_messages(messages, duplicate_index=duplicate_index),
                    task_type=task_type,
                    source_set="behavioral_synthetic",
                    source_file=f"synthetic:{task_type}",
                )
                signature = _example_signature(example)
            seen_signatures.add(signature)
            created.append(example)
            cursor += 1
    return created


def write_jsonl(path: Path, examples: Iterable[ChatExample]) -> int:
    """Write normalized examples as UTF-8 JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(
                json.dumps(
                    {
                        "messages": example.messages,
                        "task_type": example.task_type,
                        "source_set": example.source_set,
                        "source_file": example.source_file,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
    return count


def _word_stats(examples: list[ChatExample]) -> dict[str, Any]:
    if not examples:
        return {
            "prompt_words": {"mean": 0.0, "median": 0.0, "p90": 0.0, "max": 0},
            "assistant_words": {"mean": 0.0, "median": 0.0, "p90": 0.0, "max": 0},
            "combined_words_total": 0,
            "approx_qwen_tokens": 0,
        }
    prompt_words = sorted(_word_count(_user_text(example)) for example in examples)
    assistant_words = sorted(_word_count(_assistant_text(example)) for example in examples)

    def percentile(values: list[int], q: float) -> float:
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))
        return float(values[index])

    combined_words_total = sum(prompt_words) + sum(assistant_words)
    return {
        "prompt_words": {
            "mean": round(mean(prompt_words), 2),
            "median": float(percentile(prompt_words, 0.5)),
            "p90": float(percentile(prompt_words, 0.9)),
            "max": int(prompt_words[-1]),
        },
        "assistant_words": {
            "mean": round(mean(assistant_words), 2),
            "median": float(percentile(assistant_words, 0.5)),
            "p90": float(percentile(assistant_words, 0.9)),
            "max": int(assistant_words[-1]),
        },
        "combined_words_total": combined_words_total,
        "approx_qwen_tokens": int(round(combined_words_total * 1.25)),
    }


def _summarize(
    examples: list[ChatExample], *, max_answer_words: int = 280, echo_threshold: float = 0.65
) -> dict[str, Any]:
    task_counts = Counter(example.task_type for example in examples)
    topic_counts = Counter(classify_topic(example) for example in examples)
    style_counts = Counter(classify_prompt_style(example) for example in examples)
    length_counts = Counter(classify_answer_length(example) for example in examples)
    return {
        "task_counts": dict(sorted(task_counts.items())),
        "topic_counts": dict(sorted(topic_counts.items())),
        "prompt_style_counts": dict(sorted(style_counts.items())),
        "answer_length_counts": dict(sorted(length_counts.items())),
        "word_stats": _word_stats(examples),
        "quality_flags": _quality_flag_counts(
            examples,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        ),
    }


def build_distilled_bundle(
    *,
    source_dir: Path,
    output_dir: Path,
    system_prompt: str,
    knowledge_target: int = 5000,
    seed: int = 42,
    max_per_family: int = 2,
    counts_by_task: dict[str, int] | None = None,
    prefer_translated: bool = True,
    clean: bool = False,
    max_answer_words: int = 280,
    echo_threshold: float = 0.65,
) -> dict[str, Any]:
    """Build distilled knowledge JSONL, behavioral JSONL, and a combined train file."""
    if counts_by_task is None:
        counts_by_task = {task: 100 for task in BEHAVIORAL_TASKS}
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)

    raw_examples = collect_source_examples(
        source_dir,
        system_prompt=system_prompt,
        prefer_translated=prefer_translated,
    )
    selection = select_distilled_knowledge(
        raw_examples,
        target_size=min(knowledge_target, len(raw_examples)),
        seed=seed,
        max_per_family=max_per_family,
        max_answer_words=max_answer_words,
        echo_threshold=echo_threshold,
    )
    knowledge_examples = selection.selected
    behavioral_examples = synthesize_behavioral_examples(
        knowledge_examples,
        system_prompt=system_prompt,
        counts_by_task=counts_by_task,
        seed=seed,
    )
    combined_examples = [*knowledge_examples, *behavioral_examples]

    knowledge_path = output_dir / "knowledge_distilled.jsonl"
    behavioral_path = output_dir / "behavioral_synthetic.jsonl"
    train_path = output_dir / "train.jsonl"
    write_jsonl(knowledge_path, knowledge_examples)
    write_jsonl(behavioral_path, behavioral_examples)
    write_jsonl(train_path, combined_examples)

    manifest = {
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "seed": seed,
        "knowledge_target": knowledge_target,
        "max_per_family": max_per_family,
        "max_answer_words": max_answer_words,
        "echo_threshold": echo_threshold,
        "knowledge_examples": len(knowledge_examples),
        "behavioral_examples": len(behavioral_examples),
        "combined_examples": len(combined_examples),
        "behavioral_task_counts": dict(sorted(counts_by_task.items())),
        "selection_topic_targets": selection.topic_targets,
        "quality_gate": {
            "clean_pool_examples": len(selection.clean_pool),
            "dropped_examples": len(raw_examples) - len(selection.clean_pool),
            "clean_pool_flag_counts": selection.clean_pool_flag_counts,
            "dropped_flag_counts": selection.dropped_flag_counts,
        },
        "raw_summary": _summarize(
            raw_examples,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        ),
        "clean_pool_summary": _summarize(
            selection.clean_pool,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        ),
        "knowledge_summary": _summarize(
            knowledge_examples,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        ),
        "behavioral_summary": _summarize(
            behavioral_examples,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        ),
        "combined_summary": _summarize(
            combined_examples,
            max_answer_words=max_answer_words,
            echo_threshold=echo_threshold,
        ),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _parse_task_counts(task_values: list[str] | None, *, default_per_task: int) -> dict[str, int]:
    if not task_values:
        return {task: default_per_task for task in BEHAVIORAL_TASKS}
    counts = {task: 0 for task in BEHAVIORAL_TASKS}
    for value in task_values:
        if "=" not in value:
            raise ValueError(f"Invalid task override: {value}")
        task_type, raw_count = value.split("=", 1)
        task_type = task_type.strip()
        if task_type not in BEHAVIORAL_TASKS:
            raise ValueError(f"Unsupported task override: {task_type}")
        counts[task_type] = int(raw_count)
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input-dir", type=Path, help="Override source dataset directory")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--knowledge-target", type=int, default=5000)
    parser.add_argument("--max-per-family", type=int, default=2)
    parser.add_argument("--behavior-per-task", type=int, default=100)
    parser.add_argument("--max-answer-words", type=int, default=280)
    parser.add_argument("--echo-threshold", type=float, default=0.65)
    parser.add_argument(
        "--preset",
        choices=["default", "qwen35-under10k"],
        default="default",
        help="Apply a recommended distillation profile.",
    )
    parser.add_argument(
        "--task-count",
        action="append",
        help="Override behavioral counts, e.g. --task-count recommend_explain=150",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_dataset_config(args.config)
    source_dir = args.input_dir or Path(str(dataset["stylist_knowledge_dir"]))
    system_prompt = str(dataset["system_prompt"])
    prefer_translated = bool(dataset.get("prefer_translated_columns", True))

    knowledge_target = args.knowledge_target
    max_per_family = args.max_per_family
    max_answer_words = args.max_answer_words
    if args.preset == "qwen35-under10k":
        knowledge_target = 7200
        max_per_family = 3
        max_answer_words = min(max_answer_words, 280)
        counts_by_task = (
            _parse_task_counts(args.task_count, default_per_task=args.behavior_per_task)
            if args.task_count
            else dict(RECOMMENDED_QWEN35_TASK_COUNTS)
        )
    else:
        counts_by_task = _parse_task_counts(
            args.task_count, default_per_task=args.behavior_per_task
        )

    manifest = build_distilled_bundle(
        source_dir=source_dir,
        output_dir=args.output_dir,
        system_prompt=system_prompt,
        knowledge_target=knowledge_target,
        seed=args.seed,
        max_per_family=max_per_family,
        counts_by_task=counts_by_task,
        prefer_translated=prefer_translated,
        clean=args.clean,
        max_answer_words=max_answer_words,
        echo_threshold=args.echo_threshold,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
