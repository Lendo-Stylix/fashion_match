from __future__ import annotations

import json
from pathlib import Path

from torch.utils.data import Dataset


class PreferenceTripletDataset(Dataset):
    """JSONL of conditional preference triplets.

    Each line:
      {"instruction": str, "body_shape": str,
       "pos_items": list[str], "neg_items": list[str]}
    """

    def __init__(self, jsonl_path: str | Path) -> None:
        self.rows = [
            json.loads(ln)
            for ln in Path(jsonl_path).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, i: int) -> dict:
        r = self.rows[i]
        return {
            "instruction": r["instruction"],
            "body_shape": r.get("body_shape", "rectangle"),
            "pos_items": r["pos_items"],
            "neg_items": r["neg_items"],
        }
