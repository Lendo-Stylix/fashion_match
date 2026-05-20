from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SOFT_GROUPS = ("style", "color", "fit")

# body shape -> fallback hard constraint when the user specifies none
BODY_FALLBACK: dict[str, str] = {
    "pear": "structured_top",
    "apple": "defined_waist",
    "hourglass": "fitted",
    "rectangle": "add_curves",
    "inverted_triangle": "volume_bottom",
}


class HardConstraint(BaseModel):
    colors_avoid: list[str] = Field(default_factory=list)
    categories_exclude: list[str] = Field(default_factory=list)
    materials_require: list[str] = Field(default_factory=list)
    fit_bias: str | None = None
    source: Literal["user", "body_fallback"] = "user"

    def is_empty(self) -> bool:
        return not (self.colors_avoid or self.categories_exclude
                    or self.materials_require)


class SoftPreference(BaseModel):
    style: str = ""
    color: str = ""
    fit: str = ""


class StructuredPreference(BaseModel):
    hard: HardConstraint = Field(default_factory=HardConstraint)
    soft: SoftPreference = Field(default_factory=SoftPreference)

    def active_soft_groups(self) -> dict[str, str]:
        return {g: getattr(self.soft, g).strip()
                for g in SOFT_GROUPS if getattr(self.soft, g).strip()}


def apply_body_fallback(pref: StructuredPreference,
                        body_shape: str) -> StructuredPreference:
    """If the user gave no hard constraints, derive one from body shape."""
    if pref.hard.is_empty():
        pref.hard = HardConstraint(
            fit_bias=BODY_FALLBACK.get(body_shape),
            source="body_fallback",
        )
    return pref
