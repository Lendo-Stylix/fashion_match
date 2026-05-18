from __future__ import annotations

from typing import Any

from datasets import load_dataset

from outfitmatch.data.base import BaseFashionDataset


def _load_hf(hf_id: str, config: str | None, split: str):
    return load_dataset(hf_id, name=config, split=split)


class RetrievalDataset(BaseFashionDataset):
    """Image+text pairs for contrastive retrieval (DeepFashion / Fashion200K).

    Schema contract (see docs/ARCHITECTURE.md §5):
      __getitem__ → {"image": PIL.Image, "text": str, "category": str, "item_ID": str}
    """

    def __init__(self, hf_id: str, config: str | None, split: str,
                 max_rows: int | None) -> None:
        ds = _load_hf(hf_id, config, split)
        if max_rows is not None and max_rows < len(ds):
            ds = ds.select(range(max_rows))
        self._ds = ds

    def __len__(self) -> int:
        return len(self._ds)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        row = self._ds[idx]
        return {
            "image": row["image"],
            "text": row["text"],
            "category": row.get("category1", ""),
            "item_ID": row["item_ID"],
        }
