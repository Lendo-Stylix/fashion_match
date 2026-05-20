# tests/test_data_retrieval.py
from outfitmatch.data.retrieval import RetrievalDataset


class _FakeHF:
    def __init__(self, n: int):
        self._rows = [
            {"image": f"img{i}", "text": f"a red dress {i}",
             "category1": "tops", "item_ID": f"id{i}"}
            for i in range(n)
        ]

    def __len__(self):
        return len(self._rows)

    def select(self, idxs):
        f = _FakeHF(0)
        f._rows = [self._rows[i] for i in idxs]
        return f

    def __getitem__(self, i):
        return self._rows[i]


def test_max_rows_caps_length(monkeypatch):
    monkeypatch.setattr(
        "outfitmatch.data.retrieval._load_hf",
        lambda hf_id, config, split: _FakeHF(100),
    )
    ds = RetrievalDataset("Marqo/deepfashion-inshop", config="default",
                           split="data", max_rows=10)
    assert len(ds) == 10
    sample = ds[0]
    assert sample["text"] == "a red dress 0"
    assert sample["image"] == "img0"


def test_no_cap_keeps_all(monkeypatch):
    monkeypatch.setattr(
        "outfitmatch.data.retrieval._load_hf",
        lambda hf_id, config, split: _FakeHF(42),
    )
    ds = RetrievalDataset("x", config=None, split="data", max_rows=None)
    assert len(ds) == 42
