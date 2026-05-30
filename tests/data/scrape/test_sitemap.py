from scripts.data.scrape.config import StoreConfig
from scripts.data.scrape.sitemap import _extract_price, _html_to_raw, _product_urls_from_xml


def _store() -> StoreConfig:
    return StoreConfig(
        store_id="unit_store",
        store_name="Unit Store",
        website="https://example.com",
        platform="sitemap_html",
        store_type="chain_brand",
        price_tier="mid",
        target_gender="unisex",
        style_tags=("casual",),
    )


def test_product_urls_from_xml_keeps_product_blocks_with_image_metadata():
    xml = """
    <urlset xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
      <url>
        <loc>https://example.com/product/ao-thun-nam-basic</loc>
        <image:image>
          <image:loc>https://cdn.example.com/a.webp</image:loc>
          <image:title>Áo thun nam basic</image:title>
        </image:image>
      </url>
      <url><loc>https://example.com/collections/ao-nam</loc></url>
      <url><loc>https://other.example.net/product/ao-khac</loc></url>
    </urlset>
    """

    rows = _product_urls_from_xml(xml, _store())

    assert rows == [
        (
            "https://example.com/product/ao-thun-nam-basic",
            "https://cdn.example.com/a.webp",
            "Áo thun nam basic",
        )
    ]


def test_extract_price_prefers_lowest_plausible_product_price():
    html = '{"original_price":399000,"sale_price":199000} freeship 30.000đ'

    assert _extract_price(html) == 199000


def test_html_to_raw_uses_sitemap_or_og_metadata_and_price():
    html = """
    <html><head>
      <meta property="og:title" content="Áo sơ mi nữ lụa" />
      <meta property="og:image" content="https://cdn.example.com/shirt.jpg" />
      <meta property="og:description" content="Mềm nhẹ" />
    </head><body>{"sale_price":249000}</body></html>
    """

    raw = _html_to_raw(
        html,
        _store(),
        "https://example.com/product/ao-so-mi-nu-lua",
        sitemap_img=None,
        sitemap_title=None,
    )

    assert raw is not None
    assert raw.title == "Áo sơ mi nữ lụa"
    assert raw.images == ["https://cdn.example.com/shirt.jpg"]
    assert raw.min_price_vnd == 249000
    assert raw.product_url == "https://example.com/product/ao-so-mi-nu-lua"
