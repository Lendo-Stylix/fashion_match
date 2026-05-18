from __future__ import annotations

from typing import Any

from datasets import load_dataset

from outfitmatch.data.base import BaseFashionDataset


def _load_hf(hf_id: str, config: str, split: str):
    return load_dataset(hf_id, name=config, split=split)


def _cap(ds, max_rows: int | None):
    if max_rows is not None and max_rows < len(ds):
        return ds.select(range(max_rows))
    return ds


class PolyvoreCompatDataset(BaseFashionDataset):
    """Outfit compatibility: items list + binary label.

    HF source: owj0421/polyvore-outfits, config={disjoint,nondisjoint}_compatibility
    Schema (see docs/ARCHITECTURE.md §5):
      __getitem__ → {"example_id": str, "items": list[str], "label": int}
    """

    def __init__(self, hf_id: str, config: str, split: str,
                 max_rows: int | None) -> None:
        self._ds = _cap(_load_hf(hf_id, config, split), max_rows)

    def __len__(self) -> int:
        return len(self._ds)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self._ds[idx]
        return {
            "example_id": row["example_id"],
            "items": list(row["items"]),
            "label": int(row["label"]),
        }


class PolyvoreFITBDataset(BaseFashionDataset):
    """Fill-in-the-blank: partial outfit + 4 candidates.

    HF source: owj0421/polyvore-outfits, config={disjoint,nondisjoint}_fill_in_the_blank
    Schema (see docs/ARCHITECTURE.md §5):
      __getitem__ → {"question": list[str], "answers": list[str], "label": int}
    """

    def __init__(self, hf_id: str, config: str, split: str,
                 max_rows: int | None) -> None:
        self._ds = _cap(_load_hf(hf_id, config, split), max_rows)

    def __len__(self) -> int:
        return len(self._ds)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self._ds[idx]
        return {
            "question": list(row["question"]),
            "answers": list(row["answers"]),
            "label": int(row["label"]),
        }
