from scripts.data.scrape.config import StoreConfig
from scripts.data.scrape.shopify import _to_raw_product


def _store() -> StoreConfig:
    return StoreConfig(
        store_id="dirtycoins",
        store_name="Dirty Coins",
        website="https://dirtycoins.vn",
        platform="shopify_like",
        store_type="local_brand",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("streetwear",),
    )


def test_to_raw_product_accepts_bizweb_sapo_field_names():
    raw = {
        "id": 78901289,
        "name": "Relaxed Boxy DC Wavy Logo White",
        "alias": "ao-thun-relaxed-boxy-dc-wavy-logo-white",
        "product_type": "T-SHIRTS",
        "content": "<p>Chi tiết sản phẩm</p>",
        "images": ["https://cdn.example.com/a.jpg"],
        "url": "/ao-thun-relaxed-boxy-dc-wavy-logo-white",
        "variants": [
            {
                "sku": "AT1405TRS",
                "price": 450000.0,
                "compare_at_price": None,
                "available": True,
                "option1": "S",
            }
        ],
    }

    product = _to_raw_product(raw, _store())

    assert product.title == "Relaxed Boxy DC Wavy Logo White"
    assert product.handle == "ao-thun-relaxed-boxy-dc-wavy-logo-white"
    assert product.description_html == "<p>Chi tiết sản phẩm</p>"
    assert product.images == ["https://cdn.example.com/a.jpg"]
    assert product.product_url == "https://dirtycoins.vn/ao-thun-relaxed-boxy-dc-wavy-logo-white"
    assert product.min_price_vnd == 450000
