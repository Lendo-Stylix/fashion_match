#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Asynchronous Product Image Downloader
=====================================
Downloads images from fashion product JSON files and updates paths.
"""

import os
import sys
import glob
import json
import asyncio
import aiohttp
import hashlib
import logging
import urllib.parse
from typing import Dict, List, Set

# Reconfigure stdout to support UTF-8 formatting in Windows console if needed
sys.stdout.reconfigure(encoding='utf-8')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Configuration
CONCURRENT_REQUESTS = 25
SEMAPHORE = asyncio.Semaphore(CONCURRENT_REQUESTS)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

def get_image_filename(url: str, brand: str) -> str:
    """Generate a unique filename based on the brand and MD5 hash of the URL."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    _, ext = os.path.splitext(path)
    ext = ext.split('?')[0].split('#')[0].lower()
    
    # Validation of common image extensions
    if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg']:
        ext = '.jpg'
        
    url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
    return f"{brand}_{url_hash}{ext}"

def write_file_sync(data: bytes, dest_path: str):
    """Synchronously write data to a file using a temporary file to avoid corruption."""
    temp_dest = f"{dest_path}.tmp"
    try:
        with open(temp_dest, 'wb') as f:
            f.write(data)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(temp_dest, dest_path)
    except Exception as e:
        if os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except Exception:
                pass
        raise e

async def download_image(session: aiohttp.ClientSession, url: str, dest_path: str, retries: int = 3) -> bool:
    """Asynchronously download an image with retries, exponential backoff, and concurrency control."""
    if os.path.exists(dest_path):
        return True

    for attempt in range(retries):
        async with SEMAPHORE:
            try:
                async with session.get(url, headers=HEADERS, timeout=20, ssl=False) as response:
                    if response.status == 200:
                        content = await response.read()
                        await asyncio.to_thread(write_file_sync, content, dest_path)
                        return True
                    elif response.status == 429:
                        wait_time = 2 * (attempt + 1)
                        logging.warning(f"HTTP 429 Too Many Requests for {url}. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        if attempt == retries - 1:
                            logging.error(f"Failed to download {url}: HTTP {response.status}")
                            return False
                        await asyncio.sleep(1)
            except Exception as e:
                if attempt == retries - 1:
                    logging.error(f"Error downloading {url} on final attempt: {e}")
                    # Clean up temp file if exists
                    temp_dest = f"{dest_path}.tmp"
                    if os.path.exists(temp_dest):
                        try:
                            os.remove(temp_dest)
                        except Exception:
                            pass
                    return False
                await asyncio.sleep(1)
    return False

def extract_urls_from_products(products: List[Dict]) -> Set[str]:
    """Extract all web URLs from a list of products."""
    urls = set()
    for product in products:
        # 1. Product images
        images = product.get("images")
        if isinstance(images, list):
            for img in images:
                if isinstance(img, str) and (img.startswith("http://") or img.startswith("https://")):
                    urls.add(img)
                    
        # 2. Featured image
        feat_img = product.get("featured_image")
        if isinstance(feat_img, str) and (feat_img.startswith("http://") or feat_img.startswith("https://")):
            urls.add(feat_img)
            
        # 3. Variant images
        variants = product.get("variants")
        if isinstance(variants, list):
            for var in variants:
                var_images = var.get("images")
                if isinstance(var_images, list):
                    for img in var_images:
                        if isinstance(img, str) and (img.startswith("http://") or img.startswith("https://")):
                            urls.add(img)
    return urls

def update_product_urls(products: List[Dict], url_to_local: Dict[str, str]) -> int:
    """Update all web URLs to local relative paths in the product list."""
    updated_count = 0
    for product in products:
        # 1. Product images
        images = product.get("images")
        if isinstance(images, list):
            new_images = []
            for img in images:
                if img in url_to_local:
                    new_images.append(url_to_local[img])
                    updated_count += 1
                else:
                    new_images.append(img)
            product["images"] = new_images
            
        # 2. Featured image
        feat_img = product.get("featured_image")
        if feat_img in url_to_local:
            product["featured_image"] = url_to_local[feat_img]
            updated_count += 1
            
        # 3. Variant images
        variants = product.get("variants")
        if isinstance(variants, list):
            for var in variants:
                var_images = var.get("images")
                if isinstance(var_images, list):
                    new_var_images = []
                    for img in var_images:
                        if img in url_to_local:
                            new_var_images.append(url_to_local[img])
                            updated_count += 1
                        else:
                            new_var_images.append(img)
                    var["images"] = new_var_images
    return updated_count

async def process_brand_json(session: aiohttp.ClientSession, json_path: str):
    """Process a single brand JSON file, downloading its images and updating paths."""
    brand_dir = os.path.dirname(os.path.dirname(json_path))
    brand = os.path.basename(brand_dir)
    logging.info(f"=== Processing brand: {brand.upper()} ===")
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read JSON file {json_path}: {e}")
        return

    if not isinstance(products, list):
        logging.error(f"JSON data in {json_path} is not a list. Skipping.")
        return

    urls = extract_urls_from_products(products)
    if not urls:
        logging.info(f"No web URLs found in {json_path}. It might be already processed.")
        return

    # Image destination folder
    dest_dir = os.path.join(os.path.dirname(json_path), f"{brand}_images")
    os.makedirs(dest_dir, exist_ok=True)

    # Map URLs to filenames and paths
    url_to_local = {}
    download_tasks = []
    
    already_existed = 0
    to_download = 0

    for url in urls:
        filename = get_image_filename(url, brand)
        dest_path = os.path.join(dest_dir, filename)
        relative_path = f"{brand}_images/{filename}"
        
        url_to_local[url] = relative_path
        
        if os.path.exists(dest_path):
            already_existed += 1
        else:
            to_download += 1
            download_tasks.append((url, dest_path))

    logging.info(f"Found {len(urls)} unique URLs. {already_existed} already exist. Downloading {to_download} images...")

    success_urls = set()
    
    if download_tasks:
        # Run downloads asynchronously
        async_tasks = [download_image(session, url, path) for url, path in download_tasks]
        results = await asyncio.gather(*async_tasks)
        
        downloaded = 0
        failed = 0
        for (url, _), success in zip(download_tasks, results):
            if success:
                success_urls.add(url)
                downloaded += 1
            else:
                failed += 1
                
        logging.info(f"Downloads for {brand}: {downloaded} succeeded, {failed} failed.")
    
    # We map successful or already existing URLs to local paths in the JSON.
    # URLs that failed will remain as web URLs.
    url_mapping_to_update = {}
    for url, rel_path in url_to_local.items():
        dest_path = os.path.join(dest_dir, os.path.basename(rel_path))
        if os.path.exists(dest_path):
            url_mapping_to_update[url] = rel_path

    updated_fields = update_product_urls(products, url_mapping_to_update)
    logging.info(f"Updated {updated_fields} image references in JSON.")

    # Save updated JSON
    try:
        temp_json = f"{json_path}.tmp"
        with open(temp_json, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        
        if os.path.exists(json_path):
            os.remove(json_path)
        os.rename(temp_json, json_path)
        logging.info(f"Successfully saved updated JSON to {json_path}")
    except Exception as e:
        if os.path.exists(temp_json):
            try:
                os.remove(temp_json)
            except Exception:
                pass
        logging.error(f"Failed to save JSON file {json_path}: {e}")

async def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    harvest_dir = os.path.join(script_dir, "harvest")
    
    # Find all JSON files under harvest/*/output/*.json
    search_pattern = os.path.join(harvest_dir, "*", "output", "*.json")
    json_files = glob.glob(search_pattern)
    
    if not json_files:
        logging.error(f"No JSON files found matching pattern: {search_pattern}")
        return
        
    logging.info(f"Found {len(json_files)} brand JSON files to process.")
    
    async with aiohttp.ClientSession() as session:
        for json_path in json_files:
            await process_brand_json(session, json_path)
            
    logging.info("All brands processed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
