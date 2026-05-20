#!/usr/bin/env python
"""Generate preference triplets for post-training the outfit composer.

Each triplet: {"instruction", "body_shape", "pos_items", "neg_items"}

Mandatory contrastive-flip generation: for >= flip_ratio of sampled pairs,
emit the same (A, B) under >= 2 opposing instructions so the composer
must attend to [PREF] tokens.

Usage:
    uv run python scripts/generate_preference_triplets.py \
        --n-pairs 4000 --flip-ratio 0.3 --limit 5000
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import typer

app = typer.Typer()

# Opposing instruction pairs for contrastive flips
FLIP_PAIRS = [
    ("minimalist Korean street style, muted earth tones, oversized fit",
     "bold statement pieces, bright colors, tailored fit"),
    ("formal business, navy and grey, slim fit, no patterns",
     "casual everyday, comfortable relaxed fit, neutral palette"),
    ("vintage feminine, pastel colors, fitted silhouette",
     "sporty athletic, bold logos, relaxed performance fit"),
]

BODY_SHAPES = ["pear", "apple", "hourglass", "rectangle", "inverted_triangle"]


def _load_outfits(outfits_path: str) -> list[dict]:
    rows = []
    for line in Path(outfits_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _sample_pairs(outfits: list[dict], n: int) -> list[tuple[dict, dict]]:
    """Random outfit pairs."""
    pairs = []
    for _ in range(n):
        a, b = random.sample(outfits, 2)
        pairs.append((a, b))
    return pairs


def _ask_gemini(complete_fn, instruction: str, outfit_a: dict,
                outfit_b: dict) -> str:
    """Ask which outfit better matches the instruction. Returns 'A' or 'B'."""
    items_a = ", ".join(i["item_ID"] for i in outfit_a.get("items", []))
    items_b = ", ".join(i["item_ID"] for i in outfit_b.get("items", []))
    prompt = (
        f"Given the style instruction: '{instruction}'\n"
        f"Outfit A: {items_a}\n"
        f"Outfit B: {items_b}\n"
        "Which outfit better matches the user's taste? Reply with only 'A' or 'B'."
    )
    result = complete_fn(prompt).strip().upper()
    return result if result in ("A", "B") else "A"


def _write_triplet(fp, instruction: str, body_shape: str,
                   pos_items: list[str], neg_items: list[str]) -> None:
    fp.write(json.dumps({
        "instruction": instruction,
        "body_shape": body_shape,
        "pos_items": pos_items,
        "neg_items": neg_items,
    }) + "\n")


@app.command()
def main(
    outfits: str = typer.Option(
        "data/raw/outfits/outfits.jsonl", "--outfits", help="Path to outfits JSONL"),
    output: str = typer.Option(
        "data/raw/preference/triplets.jsonl", "--output", help="Output path"),
    n_pairs: int = typer.Option(4000, "--n-pairs", help="Number of outfit pairs"),
    flip_ratio: float = typer.Option(0.3, "--flip-ratio",
                                      help="Fraction of pairs with contrastive flips"),
    limit: int = typer.Option(5000, "--limit", help="Max output triplets"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate only, no API calls"),
) -> None:
    """Generate preference triplets with mandatory contrastive instruction flips."""
    random.seed(42)

    # Load outfits
    if not Path(outfits).exists():
        print(f"[WARN] Outfits file not found: {outfits}. Using dummy data.")
        outfit_data = [
            {"outfit_id": f"o{i}", "compatible": True,
             "items": [{"item_ID": f"item_{i}{j}", "role": "top"}
                       for j in range(3)]}
            for i in range(20)
        ]
    else:
        outfit_data = _load_outfits(outfits)

    if len(outfit_data) < 2:
        print("[ERROR] Need at least 2 outfits")
        raise typer.Exit(1)

    n_flip = int(n_pairs * flip_ratio)
    n_normal = n_pairs - n_flip

    # Try to import Gemini; fall back to random labeling for dry runs
    try:
        import google.generativeai as genai
        model = genai.GenerativeModel("gemini-2.0-flash")
        def complete_fn(prompt: str) -> str:
            return model.generate_content(prompt).text
    except ImportError:
        def complete_fn(prompt: str) -> str:
            return random.choice(["A", "B"])
        if not dry_run:
            print("[WARN] google-generativeai not installed; using random labels.")

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    written = 0

    with open(output, "w", encoding="utf-8") as fp:
        # Normal pairs
        pairs = _sample_pairs(outfit_data, n_normal)
        instructions_pool = [p for pair in FLIP_PAIRS for p in pair]
        for a, b in pairs:
            if written >= limit:
                break
            instruction = random.choice(instructions_pool)
            body_shape = random.choice(BODY_SHAPES)
            choice = "A" if dry_run else _ask_gemini(complete_fn, instruction, a, b)
            pos_items = [i["item_ID"] for i in (a if choice == "A" else b).get("items", [])]
            neg_items = [i["item_ID"] for i in (b if choice == "A" else a).get("items", [])]
            if pos_items and neg_items:
                _write_triplet(fp, instruction, body_shape, pos_items, neg_items)
                written += 1

        # Contrastive flip pairs
        flip_pairs_sampled = _sample_pairs(outfit_data, n_flip)
        for a, b in flip_pairs_sampled:
            if written >= limit:
                break
            flip_instruction_pair = random.choice(FLIP_PAIRS)
            body_shape = random.choice(BODY_SHAPES)
            for instruction in flip_instruction_pair:
                if written >= limit:
                    break
                choice = "A" if dry_run else _ask_gemini(
                    complete_fn, instruction, a, b)
                pos_items = [i["item_ID"]
                             for i in (a if choice == "A" else b).get("items", [])]
                neg_items = [i["item_ID"]
                             for i in (b if choice == "A" else a).get("items", [])]
                if pos_items and neg_items:
                    _write_triplet(fp, instruction, body_shape, pos_items, neg_items)
                    written += 1

    print(f"[OK] Wrote {written} triplets to {output}")


if __name__ == "__main__":
    app()
