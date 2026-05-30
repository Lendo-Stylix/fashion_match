from scripts.data.scrape.category_map import categorize, is_valid_category


def test_dress_before_top():
    # "đầm" must beat the generic "áo" rule
    assert categorize("Đầm xòe trắng dáng A") == "dress"
    assert categorize("Váy liền hoa nhí") == "dress"


def test_outerwear_before_top():
    assert categorize("Áo khoác blazer oversized") == "outerwear"
    assert categorize("Hoodie nỉ basic") == "outerwear"
    assert categorize("Cardigan len mỏng") == "outerwear"


def test_top_basic():
    assert categorize("Áo thun cotton trơn") == "top"
    assert categorize("Áo sơ mi linen") == "top"
    assert categorize("Crop top ribbed") == "top"


def test_bottom():
    assert categorize("Quần jean ống suông") == "bottom"
    assert categorize("Chân váy bút chì") == "bottom"
    assert categorize("Shorts kaki nam") == "bottom"


def test_shoes_bag_accessory():
    assert categorize("Giày sneaker trắng") == "shoes"
    assert categorize("Sandal quai mảnh") == "shoes"
    assert categorize("Túi tote canvas") == "bag"
    assert categorize("Balo da PU") == "bag"
    assert categorize("Mũ lưỡi trai cotton") == "accessory"
    assert categorize("Thắt lưng da nam") == "accessory"


def test_uses_tags_and_product_type():
    assert categorize("Item A", product_type="Jeans") == "bottom"
    assert categorize("Item B", tags=["shoes", "sneakers"]) == "shoes"


def test_unknown_returns_none():
    assert categorize("") is None
    assert categorize("Combo gift box") is None


def test_all_outputs_are_valid_enum():
    for query in [
        "Đầm xòe",
        "Áo khoác",
        "Áo thun",
        "Quần jean",
        "Giày",
        "Túi",
        "Mũ",
    ]:
        cat = categorize(query)
        assert cat is not None and is_valid_category(cat)
