"""
scraper.py — Orchestrator: điều phối toàn bộ pipeline cào dữ liệu.

Chức năng:
  - Kết nối Chrome, lấy page
  - Lấy danh sách URL sản phẩm
  - Vòng lặp scrape từng sản phẩm
  - Lưu kết quả vào JSONL + ghi log
  - Retry khi lỗi, bỏ qua sản phẩm lỗi liên tiếp
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Optional

from core.browser import connect_browser, create_new_page, close_browser
from config import (
    DELAY_BETWEEN_PAGES, OUTPUT_BASE_DIR, CONCURRENCY_LIMIT, MAX_RETRIES
)


async def scrape_site(
    site_name: str,
    limit: Optional[int] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """
    Scrape toàn bộ sản phẩm của một site.

    Args:
        site_name: 'coolmate' hoặc 'gumac'
        limit: Giới hạn số sản phẩm (None = không giới hạn)
        output_dir: Thư mục lưu kết quả (None = dùng config)

    Returns:
        dict thống kê: {total, success, failed, skipped}
    """
    # Import site-specific module
    if site_name == "coolmate":
        from sites import coolmate as site_module
    elif site_name == "gumac":
        from sites import gumac as site_module
    else:
        raise ValueError(f"Site không được hỗ trợ: {site_name}. Chọn: coolmate, gumac")

    # Setup output
    out_dir = output_dir or os.path.join(OUTPUT_BASE_DIR, site_name)
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(out_dir, f"products_{timestamp}.jsonl")
    log_file = os.path.join(out_dir, f"scrape_log_{timestamp}.txt")

    # Kết nối browser
    browser = await connect_browser()

    stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    print(f"\n{'='*60}")
    print(f"  BẮT ĐẦU SCRAPE: {site_name.upper()} (Headless Parallel)")
    print(f"  Output: {output_file}")
    print(f"{'='*60}\n")

    def _log(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ── Lấy danh sách URL ─────────────────────────────────────────────────
    _log("Đang lấy danh sách URL sản phẩm...")

    # Để lấy danh sách URL ban đầu, ta mở một context tạm thời rồi đóng lại
    context, temp_page = await create_new_page(browser)
    try:
        if site_name == "coolmate":
            product_urls = await site_module.get_all_product_urls(temp_page)
            url_lastmod_pairs = [(url, None) for url in product_urls]
        elif site_name == "gumac":
            url_lastmod_pairs = site_module.get_product_urls_from_sitemap()
    finally:
        await context.close()

    stats["total"] = len(url_lastmod_pairs)
    _log(f"Tổng cộng {stats['total']} URL sản phẩm cần cào.")

    if limit:
        url_lastmod_pairs = url_lastmod_pairs[:limit]
        _log(f"Giới hạn {limit} sản phẩm theo tham số --limit.")

    # ── Vòng lặp scrape song song ──────────────────────────────────────────
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
    write_lock = asyncio.Lock()

    async def safe_log_and_write(msg: str, product: Optional[dict] = None):
        async with write_lock:
            _log(msg)
            if product:
                with open(output_file, "a", encoding="utf-8") as out_f:
                    out_f.write(json.dumps(product, ensure_ascii=False) + "\n")

    async def scrape_one(idx: int, url: str, lastmod: Optional[str]):
        async with sem:
            # Random delay nhẹ trước khi mở page để tránh gửi quá nhiều request cùng 1 lúc
            await asyncio.sleep(random.uniform(0.1, 1.0))
            
            p_context, page = await create_new_page(browser)
            product = None
            success = False
            
            try:
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        if attempt > 1:
                            await asyncio.sleep(DELAY_BETWEEN_PAGES * attempt)
                            
                        if site_name == "coolmate":
                            product = await site_module.scrape_product(page, url)
                        else:
                            product = await site_module.scrape_product(page, url, lastmod)
                            
                        if product and product.get("name"):
                            success = True
                            break
                    except Exception as e:
                        if attempt == MAX_RETRIES:
                            await safe_log_and_write(f"  [Luồng {idx}] Thử lại lần cuối thất bại: {e}")
            finally:
                try:
                    await p_context.close()
                except Exception:
                    pass

            if success and product:
                method = product.get("_parse_method", "unknown")
                await safe_log_and_write(
                    f"[{idx}/{len(url_lastmod_pairs)}] OK: '{product['name']}' | method={method} | url={url}",
                    product=product
                )
                stats["success"] += 1
            else:
                await safe_log_and_write(f"[{idx}/{len(url_lastmod_pairs)}] THẤT BẠI: {url}")
                stats["failed"] += 1

    # Tạo các task chạy song song
    tasks = []
    for idx, (url, lastmod) in enumerate(url_lastmod_pairs, 1):
        tasks.append(scrape_one(idx, url, lastmod))

    if tasks:
        await asyncio.gather(*tasks)

    # Đóng browser giải phóng tài nguyên
    await close_browser()

    # ── Thống kê ─────────────────────────────────────────────────────────
    _log(f"\n{'='*60}")
    _log(f"  KẾT QUẢ SCRAPE: {site_name.upper()}")
    _log(f"  Total URLs  : {stats['total']}")
    _log(f"  Thành công  : {stats['success']}")
    _log(f"  Thất bại    : {stats['failed']}")
    _log(f"  File output : {output_file}")
    _log(f"{'='*60}\n")

    return stats
