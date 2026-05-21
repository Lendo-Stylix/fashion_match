from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict

class CatalogItem(BaseModel):
    model_config = ConfigDict(strict=True)

    # Identifiers
    item_ID: str
    image_path: str
    brand: Optional[str] = "unbranded"
    
    # Taxonomy chuẩn theo CATALOG_ENCODER.md
    gender: Literal["male", "female", "unisex", "kids"]
    category1: Literal["tops", "bottoms", "outerwear", "dresses", "shoes", "bags", "accessories"]
    category2: str
    category3: Optional[str] = None
    
    # Textual Data
    short_text: str = Field(min_length=5, max_length=150)
    detailed_text: Optional[str] = None
    
    # Visual & Physical Attributes
    dominant_color: str
    pattern: Literal["solid", "striped", "plaid", "graphic", "floral", "polka_dot", "abstract", "other"] = "solid"
    # Mở rộng material cho giày/túi: leather, canvas, suede, rubber, metal...
    material: Optional[str] = None 
    fit_type: Literal["oversized", "relaxed", "regular", "slim", "skinny", "compression", "not_applicable"] = "not_applicable"
    
    # Garment specifics (Tops/Bottoms/Dresses)
    neckline: Optional[Literal["crew", "v_neck", "collared", "turtleneck", "off_shoulder", "square", "hooded"]] = None
    sleeve_length: Optional[Literal["sleeveless", "short", "half", "long"]] = None
    bottom_length: Optional[Literal["mini", "knee", "midi", "maxi", "cropped", "full_length", "ankle"]] = None
    
    # Context
    season: List[Literal["spring", "summer", "autumn", "winter", "all_season"]] = Field(default_factory=lambda: ["all_season"])
    style_tags: List[str] = Field(default_factory=list)
    
    # Metadata
    source: str
    split: Literal["train", "val", "test"] = "train"
    is_manually_labeled: bool = Field(default=False)