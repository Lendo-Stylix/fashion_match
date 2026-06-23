# Grounded stylist dataset generation — file-by-file implementation plan

Date: 2026-06-23

## Goal
Build a reproducible pipeline that generates retrieval-grounded stylist SFT data from the real OutfitMatch catalog/retrieval runtime, while locking the tool-call wire format so fine-tune data and inference-time parsing never drift.

## Canonical tool-call contract

Exact wire format to train and parse everywhere:

```text
<tool_call>{"name":"search_outfits","arguments":{...}}</tool_call>
```

Optional multi-turn tool result format:

```text
<tool_response>{"name":"search_outfits","result":{...}}</tool_response>
```

Rules:
- no markdown fences
- exactly one JSON object inside each tag
- `name` must equal `search_outfits`
- `arguments` keys must be a subset of the schema in `src/outfitmatch/stylist/tools.py`
- `occasion` required
- enum values must come from `vocab.py` only
- omit unknown optional keys instead of inventing placeholders
- `price_max` is integer VND only
- `exclude_colors` is array of strings only

## File-by-file changes

### `src/outfitmatch/stylist/tools.py`
- keep `SEARCH_OUTFITS_TOOL` as the schema source of truth
- add constants for `<tool_call>` / `</tool_call>` / `<tool_response>` / `</tool_response>`
- add canonical arg lists derived from the schema
- add helpers:
  - `render_search_outfits_tool_call(arguments)`
  - `parse_tool_call_text(text)`
  - `validate_tool_call_payload(payload)`

### `src/outfitmatch/stylist/validation.py`
- keep outfit-id and size validation
- extend with tool validation helpers:
  - `extract_tool_calls(text)`
  - `validate_tool_calls(text)`
- use the canonical parser/validator from `tools.py`

### `scripts/stylist/build_grounded_scenario_bank.py`
- deterministic scenario bank from real catalog + retrieval runtime
- no LLM calls
- output `scenario_bank.jsonl` + `scenario_manifest.json`

### `scripts/stylist/generate_grounded_dialogues.py`
- turn scenario rows into grounded ChatML drafts
- support local llama-cpp draft mode
- support GPT-OSS / Nemotron teacher mode
- always import canonical tool rendering from `tools.py`

### `scripts/stylist/judge_grounded_dialogues.py`
- deterministic checks first
- GLM flash bulk judge second
- output accepted/rejected rows + summary

### `scripts/stylist/package_grounded_bundle.py`
- stratify accepted rows into final `train.jsonl` / `eval.jsonl`
- merge with knowledge core if needed
- keep `collect_examples()` compatibility

### `scripts/stylist/prepare_stylist_qlora_kaggle.py`
- add `dataset.source_mode: grounded_bundle`
- prefer `train.jsonl` in the grounded run dir

### `configs/stylist_finetune_kaggle_grounded.yaml`
- new config pointing at the final grounded bundle

### Tests
- `tests/test_stylist_tool_format.py`
- `tests/test_grounded_scenario_bank.py`
- `tests/test_grounded_dialogue_generation.py`
- `tests/test_prepare_stylist_qlora_grounded.py`

### Docs
- `docs/reports/stylist_grounded_generation.md`
- update `docs/feature.md`

## Phase order

### Phase A — lock contracts first
1. freeze canonical tool-call contract in `tools.py`
2. add tool-call validation in `validation.py`
3. add tests for exact text render/parse/validate behavior

### Phase B — deterministic runtime grounding
1. build scenario bank from real retrieval runtime
2. verify coverage and zero hallucination in scenario metadata

### Phase C — draft + teacher generation
1. local draft generation
2. teacher rewrite/upgrade via GPT-OSS / Nemotron

### Phase D — judge/filter/package
1. deterministic checks + GLM flash judge
2. final grounded bundle packaging under 10k rows

## Initial grounded target
- 900 `tool_calling_grounded`
- 700 `recommend_explain_grounded`
- 350 `ask_missing_info_grounded`
- 250 `no_result_or_relax_constraints`
- 150 `polite_decline_anti_hallucination`
- 150 `multi_turn_grounded`
- 300 `body_fit_grounded`

## Acceptance criteria for Phase A
- 100% of tool-call rows parse with canonical parser
- 100% use `search_outfits`
- 100% valid enum arguments
- 0 unsupported keys
- exact text renderer available for all future generation scripts
