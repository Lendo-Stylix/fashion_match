from outfitmatch.vocab import FORMALITY_SET
from scripts.data.scrape.formality_map import infer_formality


def test_athletic():
    assert infer_formality("Quần Thể Thao Nam") == "athletic"
    assert infer_formality("Giày Sneaker Running") == "athletic"
    assert infer_formality("Áo Bra Tập Luyện") == "athletic"


def test_formal():
    assert infer_formality("Áo Vest Nam Công Sở") == "formal"
    assert infer_formality("Đầm Dạ Hội Sang Trọng") == "formal"
    assert infer_formality("Giày Tây Da Bò") == "formal"


def test_smart_casual():
    assert infer_formality("Áo Polo Nam") == "smart_casual"
    assert infer_formality("Áo Sơ Mi Trắng Basic") == "smart_casual"
    assert infer_formality("Giày Cao Gót 5cm") == "smart_casual"


def test_casual_default():
    assert infer_formality("Áo Thun Cotton Basic") == "casual"
    assert infer_formality("Quần Jeans Rách Gối") == "casual"
    assert infer_formality("Hoodie Nỉ Bông") == "casual"


def test_athletic_beats_formal_when_both_present():
    # priority guarantee: a sporty item wins over a formal-sounding token
    assert infer_formality("Áo Thể Thao In Blazer Print") == "athletic"


def test_always_valid_enum():
    for t in ["Áo Vest", "Quần Thể Thao", "Sơ Mi", "Random Thing"]:
        assert infer_formality(t) in FORMALITY_SET
