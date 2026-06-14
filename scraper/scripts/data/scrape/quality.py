# -*- coding: utf-8 -*-
"""
Quality Gates Module
====================
Path: scripts/data/scrape/quality.py

Performs quality control checks on the scraped fashion datasets before export.
"""

import os
import json
import logging
import pandas as pd
from typing import Tuple, List, Dict, Any, Set

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("QualityGate")

# Valid values for ITEM_CATEGORY validation
VALID_ITEM_CATEGORIES = {
    "TOPS_SHIRT",
    "TOPS_POLO",
    "TOPS_T_SHIRT",
    "TOPS_SWEATSHIRT_HOODIE",
    "TOPS_SWEATER",
    "TOPS_OTHER",
    "OUTERWEAR_JACKET",
    "BOTTOMS_JEANS",
    "BOTTOMS_PANTS",
    "BOTTOMS_SHORTS",
    "BOTTOMS_SKIRT",
    "BOTTOMS_OTHER",
    "DRESS",
    "SUIT",
    "SHOES_SANDAL",
    "SHOES_SNEAKER",
    "SHOES_HEELS",
    "SHOES_OTHER",
    "ACC_BELT",
    "ACC_WALLET",
    "ACC_HAT",
    "ACC_BAG",
    "ACC_SOCKS",
    "ACC_OTHER",
    "SPORTSWEAR",
    "UNKNOWN"
}

# Registered stores/vendors
REGISTERED_STORE_IDS = {
    "4MEN", "5SFASHION", "ARISTINO", "BADRABBIT", "CANIFA", 
    "CITYCYCLE", "COOLMATE", "DEGREY", "DIRTYCOINS", "ELISE", 
    "GUMAC", "HM", "IVYMODA", "JUNO", "LEVENTS", "OWEN", 
    "TEELAB", "UNDERARMOUR", "UNIQLO", "YAME", "YODY"
}

class QualityGate:
    """Validator class for scraped fashion catalog data."""
    
    REQUIRED_CATALOG_COLS = [
        "item_id", "title", "vendor", "item_category", "gender", 
        "formality", "price", "compare_at_price", "discount_percent", 
        "description", "colors", "sizes", "local_images"
    ]
    
    REQUIRED_LINK_COLS = [
        "item_id", "url", "scraped_url", "store_id", "available"
    ]

    @staticmethod
    def check_required_columns(catalog_df: pd.DataFrame, links_df: pd.DataFrame) -> bool:
        """Verify required columns exist in both dataframes."""
        missing_catalog = [col for col in QualityGate.REQUIRED_CATALOG_COLS if col not in catalog_df.columns]
        missing_links = [col for col in QualityGate.REQUIRED_LINK_COLS if col not in links_df.columns]
        
        success = True
        if missing_catalog:
            logger.error(f"Catalog schema check FAILED. Missing: {missing_catalog}")
            success = False
        if missing_links:
            logger.error(f"Link schema check FAILED. Missing: {missing_links}")
            success = False
            
        if success:
            logger.info("Required columns check: PASSED")
        return success

    @staticmethod
    def check_unique_item_id(catalog_df: pd.DataFrame, links_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Check for unique item_ids and drop any duplicate rows."""
        dup_catalog = catalog_df.duplicated(subset=["item_id"]).sum()
        dup_links = links_df.duplicated(subset=["item_id"]).sum()
        
        if dup_catalog > 0:
            logger.warning(f"Uniqueness check: Found {dup_catalog} duplicate item_ids in catalog. Dropping duplicates.")
            catalog_df = catalog_df.drop_duplicates(subset=["item_id"], keep="first")
        if dup_links > 0:
            logger.warning(f"Uniqueness check: Found {dup_links} duplicate item_ids in links. Dropping duplicates.")
            links_df = links_df.drop_duplicates(subset=["item_id"], keep="first")
            
        return catalog_df, links_df

    @staticmethod
    def check_valid_item_category(df: pd.DataFrame) -> pd.Series:
        """Find rows with invalid ITEM_CATEGORY values."""
        invalid_mask = ~df["item_category"].isin(VALID_ITEM_CATEGORIES)
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            invalid_cats = df.loc[invalid_mask, "item_category"].unique()
            logger.warning(f"Category check: Found {invalid_count} records with unregistered categories: {invalid_cats}")
        return invalid_mask

    @staticmethod
    def check_non_empty_titles(df: pd.DataFrame) -> pd.Series:
        """Find rows with empty or whitespace-only product titles."""
        invalid_mask = df["title"].isna() | (df["title"].astype(str).str.strip() == "")
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            logger.warning(f"Title check: Found {invalid_count} records with empty titles.")
        return invalid_mask

    @staticmethod
    def check_json_list_colors(df: pd.DataFrame) -> pd.Series:
        """Find rows where colors is not a valid list/array."""
        invalid_mask = df["colors"].apply(lambda x: not isinstance(x, (list, tuple, pd.Series)))
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            logger.warning(f"Colors check: Found {invalid_count} records where colors is not a list/array.")
        return invalid_mask

    @staticmethod
    def check_existing_local_images(df: pd.DataFrame, base_dir: str) -> int:
        """Verify that files listed in local_images actually exist on disk."""
        missing_count = 0
        total_count = 0
        for _, row in df.iterrows():
            local_imgs = row.get("local_images")
            if isinstance(local_imgs, list):
                for img_rel_path in local_imgs:
                    if not img_rel_path:
                        continue
                    total_count += 1
                    # Checked path is expected to be relative to the results folder
                    full_path = os.path.join(base_dir, "harvest", "result", img_rel_path)
                    if not os.path.exists(full_path):
                        missing_count += 1
        if missing_count > 0:
            logger.warning(f"Image check: {missing_count} out of {total_count} files are missing locally on disk.")
        else:
            logger.info(f"Image check: All {total_count} local images exist.")
        return missing_count

    @staticmethod
    def check_catalog_link_join_integrity(catalog_df: pd.DataFrame, links_df: pd.DataFrame) -> bool:
        """Verify catalog item_ids match link item_ids exactly."""
        cat_ids = set(catalog_df["item_id"])
        link_ids = set(links_df["item_id"])
        
        missing_links = cat_ids - link_ids
        missing_catalog = link_ids - cat_ids
        
        passed = True
        if missing_links:
            logger.error(f"Join integrity: {len(missing_links)} catalog items are missing links entries.")
            passed = False
        if missing_catalog:
            logger.error(f"Join integrity: {len(missing_catalog)} links items are missing catalog entries.")
            passed = False
            
        if passed:
            logger.info("Join integrity check: PASSED")
        return passed

    @staticmethod
    def check_registered_store_id(df: pd.DataFrame) -> pd.Series:
        """Find rows with unregistered store_ids (vendors)."""
        invalid_mask = ~df["store_id"].astype(str).str.upper().isin(REGISTERED_STORE_IDS)
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            invalid_stores = df.loc[invalid_mask, "store_id"].unique()
            logger.warning(f"Store check: Found {invalid_count} records with unregistered store_ids: {invalid_stores}")
        return invalid_mask

    @staticmethod
    def check_absolute_urls(df: pd.DataFrame) -> pd.Series:
        """Find rows with non-absolute URLs."""
        invalid_mask = df["url"].isna() | (~df["url"].astype(str).str.startswith("http://") & ~df["url"].astype(str).str.startswith("https://"))
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            logger.warning(f"URL check: Found {invalid_count} records with invalid/relative URLs.")
        return invalid_mask

    @staticmethod
    def check_sane_prices(df: pd.DataFrame) -> pd.Series:
        """Find rows with unreasonable prices (<= 0 or > 100,000,000 VND)."""
        invalid_mask = df["price"].isna() | (df["price"] <= 0) | (df["price"] > 100000000)
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            logger.warning(f"Price sanity check: Found {invalid_count} records with insane prices.")
        return invalid_mask

    @staticmethod
    def check_sale_price_consistency(df: pd.DataFrame) -> Tuple[bool, pd.DataFrame]:
        """Verify that price <= compare_at_price. Clean up anomalies."""
        has_compare = df["compare_at_price"].notna() & (df["compare_at_price"] > 0)
        inconsistent = has_compare & (df["price"] > df["compare_at_price"])
        inconsistent_count = inconsistent.sum()
        
        if inconsistent_count > 0:
            logger.warning(f"Price consistency check: Found {inconsistent_count} records where sale price > compare_at_price. Resetting compare_at_price.")
            df_cleaned = df.copy()
            df_cleaned.loc[inconsistent, "compare_at_price"] = None
            df_cleaned.loc[inconsistent, "discount_percent"] = 0
            return False, df_cleaned
            
        return True, df

    @classmethod
    def run_all(cls, catalog_df: pd.DataFrame, links_df: pd.DataFrame, base_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame, bool]:
        """Runs all checks, filters out critical errors, and returns cleaned dataframes."""
        logger.info("Executing Quality Gates checklist...")
        
        # 1. Schema Check
        if not cls.check_required_columns(catalog_df, 	links_df):
            return catalog_df, links_df, False
            
        # 2. Unique item_id
        catalog_df, links_df = cls.check_unique_item_id(catalog_df, links_df)
        
        # 3. critical filters (invalid title, price, or url)
        bad_title = cls.check_non_empty_titles(catalog_df)
        bad_price = cls.check_sane_prices(catalog_df)
        bad_url = cls.check_absolute_urls(links_df)
        
        bad_ids = set(catalog_df.loc[bad_title | bad_price, "item_id"]).union(
            set(links_df.loc[bad_url, "item_id"])
        )
        
        if bad_ids:
            logger.warning(f"Quality Gates: Dropping {len(bad_ids)} records due to critical errors.")
            catalog_df = catalog_df[~catalog_df["item_id"].isin(bad_ids)]
            links_df = links_df[~links_df["item_id"].isin(bad_ids)]
            
        # 4. Non-critical validations and corrections
        _, catalog_df = cls.check_sale_price_consistency(catalog_df)
        cls.check_valid_item_category(catalog_df)
        cls.check_json_list_colors(catalog_df)
        cls.check_registered_store_id(links_df)
        cls.check_existing_local_images(catalog_df, base_dir)
        cls.check_catalog_link_join_integrity(catalog_df, links_df)
        
        logger.info("Quality Gates execution completed.")
        return catalog_df, links_df, True
