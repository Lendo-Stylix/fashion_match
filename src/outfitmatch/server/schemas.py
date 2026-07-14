"""Pydantic schemas for FastAPI request/response validation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """POST /api/chat — conversational stylist."""

    message: str = Field(min_length=1, max_length=2000, description="User message in Vietnamese")
    conversation_id: str | None = Field(None, description="Optional session ID")
    quiz_answers: dict | None = Field(None, description="Onboarding quiz answers")


class ItemCardDTO(BaseModel):
    """One item within an outfit."""

    item_id: str
    category: str
    title_vi: str = ""
    price_vnd: int = 0
    store_name: str = ""
    product_url: str = ""
    image_path: str = ""


class OutfitCardDTO(BaseModel):
    """One complete outfit for the frontend."""

    outfit_id: str
    explanation_vi: str = ""
    price_total_vnd: int = 0
    price_tier: str = ""
    style: list[str] = []
    occasion: list[str] = []
    color_palette: list[str] = []
    items: list[ItemCardDTO] = []
    compatibility_score: float = 0.0


class RecommendRequestDTO(BaseModel):
    """POST /api/recommend — structured request."""

    occasion: str
    style: str | None = None
    body_shape: str | None = None
    skin_tone: str | None = None
    price_max: int | None = None
    exclude_colors: list[str] = Field(default_factory=list)
    height_cm: int | None = None
    weight_kg: int | None = None
    quiz_answers: dict | None = None


class ItemBriefDTO(BaseModel):
    """Minimal item info for display."""

    item_id: str
    category: str
    title_vi: str = ""
    price_vnd: int = 0
    store_name: str = ""
    product_url: str = ""
    image_path: str = ""
    in_stock: bool = False
    sizes: list[str] = []


class ItemDetailDTO(BaseModel):
    """Full item detail including outfit_ids."""

    item_id: str
    category: str
    title_vi: str = ""
    price_vnd: int = 0
    store_name: str = ""
    product_url: str = ""
    image_path: str = ""
    in_stock: bool = False
    sizes: list[str] = []
    gender: str = "unisex"
    formality: str = "casual"
    body_shapes_fit: list[str] = []
    season: list[str] = []
    outfit_ids: list[str] = []
