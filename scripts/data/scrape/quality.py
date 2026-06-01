"""Quality checks for the scraped VN catalog parquet files.

This module is intentionally model-free. It validates the raw catalog stream before
Tầng 1 KB embedding/generation consumes it: schema, joins, enum categories,
price sanity, URL shape, image presence, and simple distribution summaries.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from outfitmatch.vocab import ITEM_CATEGORY_SET
from scripts.data.scrape.base import CATALOG_DIR, REPO_ROOT
from scripts.data.scrape.config import STORES_BY_ID
from scripts.data.scrape.normalize import PRICE_MAX_VND, PRICE_MIN_VND

CATALOG_PARQUET = CATALOG_DIR / "catalog_metadata.parquet"
LINKS_PARQUET = CATALOG_DIR / "item_store_links.parquet"

CATALOG_COLUMNS: tuple[str, ...] = (
    "item_id",
    "category",
    "source_product_type",
    "gender",
    "formality",
    "image_path",
    "title_vi",
    "desc_vi",
    "colors",
    "collected_date",
    "collector",
)
LINK_COLUMNS: tuple[str, ...] = (
    "item_id",
    "store_id",
    "source_product_id",
    "product_url",
    "price_vnd",
    "sale_price_vnd",
    "sku",
    "in_stock",
    "available_sizes",
    "sizes_in_stock",
)

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


@dataclass(frozen=True)
class QualityIssue:
    """One data-quality issue emitted by :func:`check_catalog`."""

    level: str
    code: str
    message: str
    count: int = 1
    sample: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QualityReport:
    """Catalog-quality report with aggregate counts and issue list."""

    total_items: int
    total_links: int
    store_counts: dict[str, int]
    category_counts: dict[str, int]
    issues: list[QualityIssue]

    @property
    def error_count(self) -> int:
        """Number of error-level checks that failed."""
        return sum(1 for issue in self.issues if issue.level == "error")

    @property
    def warning_count(self) -> int:
        """Number of warning-level checks that failed."""
        return sum(1 for issue in self.issues if issue.level == "warning")

    @property
    def ok(self) -> bool:
        """True when no error-level issue is present."""
        return self.error_count == 0


def _sample(values: Iterable[Any], n: int = 5) -> list[str]:
    out: list[str] = []
    for value in values:
        if pd.isna(value):
            out.append("<NA>")
        else:
            out.append(str(value))
        if len(out) >= n:
            break
    return out


def _issue(
    issues: list[QualityIssue],
    *,
    level: str,
    code: str,
    message: str,
    count: int,
    sample: Iterable[Any] = (),
) -> None:
    if count <= 0:
        return
    issues.append(
        QualityIssue(level=level, code=code, message=message, count=count, sample=_sample(sample))
    )


def _missing_columns(df: pd.DataFrame, required: tuple[str, ...]) -> list[str]:
    return [col for col in required if col not in df.columns]


def _read_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_parquet(path)


def _invalid_color_rows(colors: pd.Series) -> list[str]:
    bad: list[str] = []
    for idx, raw in colors.items():
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            bad.append(str(idx))
            continue
        if not isinstance(parsed, list) or not all(isinstance(v, str) for v in parsed):
            bad.append(str(idx))
    return bad


def check_catalog(
    catalog_path: Path = CATALOG_PARQUET,
    links_path: Path = LINKS_PARQUET,
    *,
    repo_root: Path = REPO_ROOT,
) -> QualityReport:
    """Validate scraped catalog/link parquet files and return a quality report."""
    return check_frames(_read_parquet(catalog_path), _read_parquet(links_path), repo_root=repo_root)


def check_frames(
    catalog: pd.DataFrame,
    links: pd.DataFrame,
    *,
    repo_root: Path = REPO_ROOT,
    check_images: bool = True,
) -> QualityReport:
    """In-memory core of :func:`check_catalog`.

    ``check_images=False`` skips the local-file existence check, which is useful
    when the batch gate runs before downloading images or when a smoke test uses
    ``--no-images``.
    """
    issues: list[QualityIssue] = []

    missing_catalog = _missing_columns(catalog, CATALOG_COLUMNS)
    missing_links = _missing_columns(links, LINK_COLUMNS)
    _issue(
        issues,
        level="error",
        code="missing_catalog_columns",
        message="catalog parquet is missing required columns",
        count=len(missing_catalog),
        sample=missing_catalog,
    )
    _issue(
        issues,
        level="error",
        code="missing_link_columns",
        message="item_store_links parquet is missing required columns",
        count=len(missing_links),
        sample=missing_links,
    )
    if missing_catalog or missing_links:
        return QualityReport(0, 0, {}, {}, issues)

    duplicate_items = catalog.loc[catalog["item_id"].duplicated(), "item_id"]
    duplicate_links = links.loc[links[["item_id", "store_id"]].duplicated(), "item_id"]
    _issue(
        issues,
        level="error",
        code="duplicate_item_id",
        message="catalog item_id must be unique",
        count=int(duplicate_items.shape[0]),
        sample=duplicate_items,
    )
    _issue(
        issues,
        level="error",
        code="duplicate_item_store_link",
        message="each (item_id, store_id) link must be unique",
        count=int(duplicate_links.shape[0]),
        sample=duplicate_links,
    )

    invalid_categories = catalog.loc[~catalog["category"].isin(ITEM_CATEGORY_SET), "category"]
    _issue(
        issues,
        level="error",
        code="invalid_category",
        message="category must come from outfitmatch.vocab.ITEM_CATEGORY",
        count=int(invalid_categories.shape[0]),
        sample=invalid_categories,
    )

    missing_titles = catalog.loc[catalog["title_vi"].fillna("").astype(str).str.strip() == ""]
    _issue(
        issues,
        level="error",
        code="missing_title",
        message="title_vi must be non-empty",
        count=int(missing_titles.shape[0]),
        sample=missing_titles["item_id"],
    )

    invalid_colors = _invalid_color_rows(catalog["colors"])
    _issue(
        issues,
        level="error",
        code="invalid_colors_json",
        message="colors must be a JSON list of strings",
        count=len(invalid_colors),
        sample=invalid_colors,
    )

    if check_images:
        image_paths = catalog["image_path"].fillna("").astype(str)
        missing_image = catalog.loc[
            ~image_paths.map(lambda p: bool(p) and (repo_root / p).exists())
        ]
        _issue(
            issues,
            level="error",
            code="missing_image_file",
            message="image_path must point to an existing local file",
            count=int(missing_image.shape[0]),
            sample=missing_image["image_path"],
        )

    catalog_ids = set(catalog["item_id"].astype(str))
    link_ids = set(links["item_id"].astype(str))
    catalog_without_link = sorted(catalog_ids - link_ids)
    link_without_catalog = sorted(link_ids - catalog_ids)
    _issue(
        issues,
        level="error",
        code="catalog_without_link",
        message="every catalog row must have at least one store link",
        count=len(catalog_without_link),
        sample=catalog_without_link,
    )
    _issue(
        issues,
        level="error",
        code="link_without_catalog",
        message="every store link item_id must exist in catalog",
        count=len(link_without_catalog),
        sample=link_without_catalog,
    )

    invalid_stores = links.loc[~links["store_id"].isin(STORES_BY_ID), "store_id"]
    _issue(
        issues,
        level="error",
        code="invalid_store_id",
        message="store_id must be registered in scripts.data.scrape.config.STORES",
        count=int(invalid_stores.shape[0]),
        sample=invalid_stores,
    )

    urls = links["product_url"].fillna("").astype(str)
    invalid_urls = links.loc[~urls.str.match(_URL_RE), "product_url"]
    _issue(
        issues,
        level="error",
        code="invalid_product_url",
        message="product_url must be an absolute http(s) URL",
        count=int(invalid_urls.shape[0]),
        sample=invalid_urls,
    )

    prices = pd.to_numeric(links["price_vnd"], errors="coerce")
    invalid_prices = links.loc[prices.isna() | (prices < PRICE_MIN_VND) | (prices > PRICE_MAX_VND)]
    _issue(
        issues,
        level="error",
        code="invalid_price",
        message=f"price_vnd must be between {PRICE_MIN_VND} and {PRICE_MAX_VND}",
        count=int(invalid_prices.shape[0]),
        sample=invalid_prices["item_id"],
    )

    sale_prices = pd.to_numeric(links["sale_price_vnd"], errors="coerce")
    sale_above_price = links.loc[sale_prices.notna() & prices.notna() & (sale_prices > prices)]
    _issue(
        issues,
        level="error",
        code="sale_price_above_price",
        message="sale_price_vnd cannot be greater than price_vnd",
        count=int(sale_above_price.shape[0]),
        sample=sale_above_price["item_id"],
    )

    empty_desc = catalog.loc[catalog["desc_vi"].fillna("").astype(str).str.strip() == ""]
    _issue(
        issues,
        level="warning",
        code="empty_description",
        message="desc_vi is empty; downstream tagger will rely mostly on title/image",
        count=int(empty_desc.shape[0]),
        sample=empty_desc["item_id"],
    )

    store_counts = links["store_id"].value_counts().sort_index().astype(int).to_dict()
    category_counts = catalog["category"].value_counts().sort_index().astype(int).to_dict()
    return QualityReport(
        total_items=int(catalog.shape[0]),
        total_links=int(links.shape[0]),
        store_counts=store_counts,
        category_counts=category_counts,
        issues=issues,
    )


def summarize_catalog(report_or_issues: QualityReport | Iterable[QualityIssue]) -> str:
    """Render a stable human-readable quality report."""
    if isinstance(report_or_issues, QualityReport):
        report = report_or_issues
        issues = report.issues
        lines = [
            f"items: {report.total_items}",
            f"links: {report.total_links}",
            f"errors: {report.error_count}",
            f"warnings: {report.warning_count}",
            "stores: " + json.dumps(report.store_counts, ensure_ascii=False, sort_keys=True),
            "categories: " + json.dumps(report.category_counts, ensure_ascii=False, sort_keys=True),
        ]
    else:
        issues = list(report_or_issues)
        lines = []
    for issue in sorted(issues, key=lambda x: (x.level, x.code)):
        line = f"{issue.level.upper()} {issue.code}: {issue.message} (count={issue.count})"
        if issue.sample:
            line += " sample=" + json.dumps(issue.sample, ensure_ascii=False)
        lines.append(line)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for catalog quality checks."""
    parser = argparse.ArgumentParser(description="Validate scraped catalog parquet quality")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PARQUET)
    parser.add_argument("--links", type=Path, default=LINKS_PARQUET)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args(argv)

    report = check_catalog(args.catalog, args.links, repo_root=args.repo_root)
    print(summarize_catalog(report))
    if report.error_count > 0 or (args.warnings_as_errors and report.warning_count > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
