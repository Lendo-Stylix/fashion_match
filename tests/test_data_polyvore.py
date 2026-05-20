# tests/test_data_polyvore.py
from outfitmatch.data.polyvore import PolyvoreCompatDataset, PolyvoreFITBDataset


class _FakeHF:
    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def select(self, idxs):
        return _FakeHF([self._rows[i] for i in idxs])

    def __getitem__(self, i):
        return self._rows[i]


def test_compat_dataset_parses_label(monkeypatch):
    rows = [{"example_id": "1", "items": ["a", "b"], "label": "1"},
            {"example_id": "2", "items": ["c"], "label": "0"}]
    monkeypatch.setattr("outfitmatch.data.polyvore._load_hf",
                        lambda *a, **k: _FakeHF(rows))
    ds = PolyvoreCompatDataset("owj0421/polyvore-outfits",
                               config="disjoint_compatibility",
                               split="test", max_rows=None)
    assert len(ds) == 2
    assert ds[0]["items"] == ["a", "b"]
    assert ds[0]["label"] == 1
    assert ds[1]["label"] == 0


def test_fitb_dataset_exposes_question_and_answer(monkeypatch):
    rows = [{"example_id": "1", "question": ["a", "b"],
             "answers": ["x", "y", "z", "w"], "label": 2}]
    monkeypatch.setattr("outfitmatch.data.polyvore._load_hf",
                        lambda *a, **k: _FakeHF(rows))
    ds = PolyvoreFITBDataset("owj0421/polyvore-outfits",
                             config="disjoint_fill_in_the_blank",
                             split="test", max_rows=1)
    s = ds[0]
    assert s["question"] == ["a", "b"]
    assert s["answers"][s["label"]] == "z"
