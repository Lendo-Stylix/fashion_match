"""Outfit Knowledge Base data types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ItemRecord:
    """One clothing/accessory item from a VN store."""

    item_id: str
    category: str  # ITEM_CATEGORY enum value
    image_path: str  # local path under data/custom/catalog/images/
    item_embedding: list[float]  # dim = ITEM_EMBED_DIM (verify from checkpoint)
    store: dict  # {store_id, store_name, product_url, price_vnd, in_stock}
    gender: str = "unisex"  # GENDER enum value (men|women|unisex|kid)
    formality: str = "casual"  # FORMALITY enum value — used by outfit-coherence filter
    body_shapes_fit: list[str] = field(default_factory=list)  # BODY_SHAPE enum values
    season: list[str] = field(default_factory=list)  # SEASON enum values
    stylist_notes_vi: str = ""  # Short VN note from Gemini item semantic tagging


@dataclass
class OutfitRecord:
    """One complete outfit in the Knowledge Base (schema_version 3.1)."""

    outfit_id: str
    schema_version: str
    items: list[ItemRecord]
    outfit_embedding: list[float]  # aggregate embedding — same dim as item_embedding
    compatibility_score: float  # OT score in [0, 1] — always re-scored after generation

    # === 2 primary conditioning fields (OCCASION/STYLE enums) ===
    occasion: list[str]  # e.g. ["office", "cafe_hangout"]
    style: list[str]  # e.g. ["minimalist", "korean"]

    # === secondary metadata ===
    body_shapes_fit: list[str]  # BODY_SHAPE enum values
    season: list[str]  # SEASON enum values
    color_palette: list[str]  # free-form color names (not enum)
    price_total_vnd: int
    price_tier: str  # PRICE_TIER enum value
    has_vn_store: bool

    stylist_explanation_vi: str  # Vietnamese explanation — display only
    gen_method: str  # "fitb_beam" | "random_scored"
    gender: str = "unisex"  # GENDER enum value — every item in the outfit agrees

    def to_qdrant_payload(self) -> dict:
        """Serialize to Qdrant point payload.

        Items and embeddings are stored separately (as vectors/vector_name).
        Only filterable metadata goes into the payload.
        """
        return {
            "outfit_id": self.outfit_id,
            "schema_version": self.schema_version,
            "gender": self.gender,
            "occasion": self.occasion,
            "style": self.style,
            "body_shapes_fit": self.body_shapes_fit,
            "season": self.season,
            "color_palette": self.color_palette,
            "price_total_vnd": self.price_total_vnd,
            "price_tier": self.price_tier,
            "has_vn_store": self.has_vn_store,
            "compatibility_score": self.compatibility_score,
            "stylist_explanation_vi": self.stylist_explanation_vi,
            "gen_method": self.gen_method,
        }
