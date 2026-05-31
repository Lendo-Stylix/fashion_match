from scripts.data.scrape.gender_map import infer_gender

from outfitmatch.vocab import GENDER_SET


def test_explicit_vietnamese_tokens():
    assert infer_gender("Áo Sơ Mi Nam Dài Tay") == "men"
    assert infer_gender("Quần Jeans Nữ Lưng Cao") == "women"
    assert infer_gender("Áo Thun Unisex Cotton") == "unisex"


def test_kid_beats_everything():
    assert infer_gender("Áo Thun Bé Trai In Hình") == "kid"
    assert infer_gender("Đầm Bé Gái Công Chúa") == "kid"
    assert infer_gender("T-shirt Kid Lớn Sport") == "kid"
    assert infer_gender("Bộ Đồ Thể Thao Trẻ Em") == "kid"


def test_english_tokens():
    assert infer_gender("Classic Shirt for Men") == "men"
    assert infer_gender("Summer Dress Women") == "women"


def test_store_default_when_no_title_signal():
    # aristino = menswear, rubies/huelleyrose = womenswear, dirtycoins = unisex.
    assert infer_gender("ITALY Premium Shirt", store_id="aristino_vn") == "men"
    assert infer_gender("Nami Top RR26AK53", store_id="rubies") == "women"
    assert infer_gender("BLOOD MINIDRESS", store_id="huelleyrose") == "women"
    assert infer_gender("Oversized Tee", store_id="dirtycoins") == "unisex"


def test_title_token_overrides_store_default():
    # A women's item listed under a menswear-default store still wins via title.
    assert infer_gender("Áo Nữ", store_id="aristino_vn") == "women"


def test_dress_category_prior_is_women():
    assert infer_gender("Đầm Xòe Hoa Nhí", category="dress") == "women"
    # but a kid dress is kid, not women
    assert infer_gender("Đầm Bé Gái", category="dress") == "kid"
    # and a men's "Áo Dài Nam" (category dress) stays men via token
    assert infer_gender("Áo Dài Nam Truyền Thống", category="dress") == "men"


def test_ambiguous_both_tokens_is_unisex():
    assert infer_gender("Dép Đôi Nam Nữ") == "unisex"


def test_women_leaning_garments_without_token():
    # Skirts, heels and dresses are women's even when the title has no "nữ".
    assert infer_gender("Chân Váy Bút Chì Dáng Dài") == "women"
    assert infer_gender("Dép Cao Gót Vuông Quai Chéo 4cm") == "women"
    assert infer_gender("Đầm Xòe Hoa") == "women"
    # but a kids' skirt is still kid
    assert infer_gender("Chân Váy Bé Gái") == "kid"


def test_unknown_falls_back_to_unisex():
    assert infer_gender("Basic Cotton Item") == "unisex"


def test_output_always_valid_enum():
    for title in ["Áo Nam", "Váy Nữ", "Bé Trai", "Random", "Unisex Hoodie"]:
        assert infer_gender(title) in GENDER_SET
