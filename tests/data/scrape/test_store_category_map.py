from scripts.data.scrape.store_category_map import (
    DROP,
    category_from_store_type,
    resolve_category,
)

from outfitmatch.vocab import ITEM_CATEGORY_SET


def test_rubies_codes_disambiguate_skirt_vs_dress():
    # The key win: store code separates váy (skirt → bottom) from đầm (dress).
    assert category_from_store_type("VQ", "rubies") == "bottom"  # Váy Quần / skort
    assert category_from_store_type("VD", "rubies") == "bottom"  # Váy Dài
    assert category_from_store_type("VN", "rubies") == "bottom"  # Váy Ngắn
    assert category_from_store_type("DD", "rubies") == "dress"  # Đầm Dài
    assert category_from_store_type("DN", "rubies") == "dress"  # Đầm Ngắn
    assert category_from_store_type("AK", "rubies") == "top"
    assert category_from_store_type("KB", "rubies") == "outerwear"
    assert category_from_store_type("PC", "rubies") == "accessory"


def test_rubies_set_code_is_dropped():
    assert category_from_store_type("SQ", "rubies") == DROP


def test_rubies_code_only_applies_to_rubies():
    # "AK" must not be treated as a code for another store.
    assert category_from_store_type("AK", "dirtycoins") != "top"


def test_generic_english_types():
    assert category_from_store_type("T-SHIRTS") == "top"
    assert category_from_store_type("JACKETS") == "outerwear"
    assert category_from_store_type("JEANS") == "bottom"
    assert category_from_store_type("SLIDES") == "shoes"
    assert category_from_store_type("BOWLER BAGS") == "bag"
    assert category_from_store_type("CAPS") == "accessory"
    assert category_from_store_type("SOCKS") == "accessory"


def test_generic_vietnamese_types():
    assert category_from_store_type("Áo Sơ mi dài tay") == "top"
    assert category_from_store_type("Quần Âu") == "bottom"
    assert category_from_store_type("Áo khoác") == "outerwear"
    assert category_from_store_type("Cà vạt") == "accessory"
    assert category_from_store_type("Dây lưng lẻ") == "accessory"
    assert category_from_store_type("Giày Loafer") == "shoes"
    assert category_from_store_type("Túi đeo chéo") == "bag"
    assert category_from_store_type("Áo Dài") == "dress"


def test_out_of_scope_dropped():
    for pt in [
        "PHONE CASES",
        "INNERWEAR",
        "bra",
        "swimwear",
        "clothing set",
        "Bộ Suits",
        "Quần Briefs",
        "Quần Boxer",
        "Đồ lót nam",
        "Nước hoa",
        "Quà tặng",
        "Gift Voucher Tiền Mặt",
        "Móc treo chìa khóa",
    ]:
        assert category_from_store_type(pt) == DROP, pt


def test_empty_product_type_returns_none():
    assert category_from_store_type("") is None
    assert category_from_store_type("   ") is None


def test_keyword_fallback_for_unseen_long_types():
    # Values not enumerated exactly still resolve via head-noun keyword.
    assert category_from_store_type("Giày Tây Cao Cấp") == "shoes"
    assert category_from_store_type("Quần Jogger Nam") == "bottom"
    assert category_from_store_type("Áo Khoác Dạ Lông Cừu") == "outerwear"


def test_resolve_prefers_store_then_title():
    # store product_type wins
    assert resolve_category("Đầm gì đó", product_type="VD", store_id="rubies") == "bottom"
    # store out-of-scope → dropped even if title looks valid
    assert resolve_category("Quần lót nam", product_type="INNERWEAR") is None
    # no store signal → fall back to title categoriser
    assert resolve_category("Áo sơ mi linen", product_type="") == "top"
    assert resolve_category("Quần Baggy Nữ Lưng Cao", product_type="") == "bottom"


def test_all_non_drop_outputs_are_valid_enum():
    for pt in ["dresses", "tops", "jeans", "slides", "túi tote", "cà vạt", "áo khoác"]:
        cat = category_from_store_type(pt)
        assert cat is not None and cat != DROP
        assert cat in ITEM_CATEGORY_SET
