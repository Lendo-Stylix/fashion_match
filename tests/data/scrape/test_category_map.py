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


def test_title_wins_over_polluted_keywords_in_description_words():
    # Substring matching used to grab "bag" out of "Baggy" and "cap" out of "Capri".
    assert categorize("Quần Baggy Nữ Lưng Cao Nano Gấu Lơ Vê") == "bottom"
    assert categorize("Flynn Capri Pants") == "bottom"
    assert categorize("Caprice Top") == "top"


def test_feature_word_does_not_override_primary_noun():
    # VN store titles always lead with the category noun. Feature words
    # like "thêu túi", "phối túi", "in giày" must not override it.
    assert categorize("Quần Jeans Nam Slim Fit Thêu Túi") == "bottom"
    assert categorize("Áo Sơ Mi Nam Phối Túi") == "top"
    assert categorize("Áo Polo Nam Mắt Chim In Túi") == "top"
    assert categorize("T-shirt Kid Lớn In Giày Sport") == "top"
    assert categorize("Áo thun in hình mũ bóng chày") == "top"


def test_tag_or_product_type_does_not_override_title_category():
    # Even if upstream sends a wrong product_type / tag, the title must win.
    assert categorize("VUCANI TOP", product_type="Dresses", tags=["dress", "new arrivals"]) == "top"
    assert categorize("Quần âu nam cạp cao", product_type="Accessory", tags=["belt"]) == "bottom"


def test_compound_outerwear_and_skirt():
    assert categorize("Áo Len Trẻ Em Form Rộng") == "outerwear"
    assert categorize("Áo Vest Nữ dáng dài") == "outerwear"
    assert categorize("Chân Váy Bút Chì") == "bottom"
    assert categorize("Váy liền hoa nhí") == "dress"


def test_bikini_top_still_top():
    assert categorize("Yuli Bikini Top") == "top"


def test_underwear_is_not_shoes():
    # "Quần lót" / "underwear" are intentionally NOT shoes; they should
    # either map to bottom (quần lót) or return None (pure "underwear").
    assert categorize("Quần lót nam cotton") == "bottom"
    assert categorize("Underwear basic set") is None


def test_socks_are_accessory_not_shoes():
    assert categorize("Combo 2 Đôi Tất Nữ Cao Cổ Phối Kẻ To") == "accessory"
    assert categorize("Vớ cotton nam") == "accessory"


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
