#!/usr/bin/env python
"""scrape_sizes.py - Fill missing available_sizes and sizes_in_stock for YODY and Canifa."""
from __future__ import annotations

import asyncio, json, logging, random, re, sys, time
from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

import httpx, pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
LINKS_PARQUET = REPO_ROOT / 'data' / 'custom' / 'catalog' / 'item_store_links.parquet'
CACHE_ROOT = REPO_ROOT / 'data' / 'cache' / 'raw'

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)-8s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('scrape_sizes')

_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)

def _norm_size(size: str) -> str:
    return size.strip().upper()

# Canifa: parse sizes from cached HTML
_SIZE_RE = re.compile(
    r'<div class="product__option-item product__option-size(?:\s+[^>]*?)?">\s*(\w+)\s*</div>',
    re.DOTALL,
)

def _canifa_sizes_from_html(html: str) -> list[str]:
    seen, out = set(), []
    for m in _SIZE_RE.finditer(html):
        sz = _norm_size(m.group(1))
        if sz and sz not in seen:
            seen.add(sz); out.append(sz)
    return out

def _find_canifa_cache(cache_dir: Path, slug: str) -> Path | None:
    exact = cache_dir / f'product_html_{slug}.txt'
    if exact.exists():
        return exact
    candidates = list(cache_dir.glob(f'product_html_{slug[:15]}*.txt'))
    for c in candidates:
        name = c.name[len('product_html_'):]
        if name.startswith(slug[:15]):
            return c
    return next((c for c in candidates if c.exists()), None)

# YODY async batch fetcher
async def _yody_fetch_one(client, handle: str):
    try:
        r = await client.get(
            f'https://yody.vn/api/products/{handle}',
            headers={'User-Agent': _USER_AGENT, 'Accept': 'application/json'},
            timeout=20.0,
        )
        if r.status_code != 200:
            return handle, [], []
        data = r.json()
    except Exception:
        return handle, [], []
    product = data.get('product', {})
    variants = product.get('variants', [])
    seen, seen_s = set(), set()
    all_s, in_stock = [], []
    for v in variants:
        sz = _norm_size(str(v.get('size', {}).get('name', '')))
        if not sz:
            continue
        if sz not in seen:
            seen.add(sz); all_s.append(sz)
        if v.get('in_stock') and sz not in seen_s:
            seen_s.add(sz); in_stock.append(sz)
    return handle, all_s, in_stock

async def _yody_batch(handles: list[str], sem_val: int = 4):
    sem = asyncio.Semaphore(sem_val)
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=8)) as client:
        async def _do(h: str):
            async with sem:
                r = await _yody_fetch_one(client, h)
                await asyncio.sleep(0.05)
                return r
        return await asyncio.gather(*[_do(h) for h in handles])

def scrape_yody(df, dry_run=False):
    yody = df[df['store_id'] == 'yody_vn']
    needs = yody[yody['available_sizes'] == '[]']
    log.info('YODY: %d items, %d need update', len(yody), len(needs))
    if len(needs) == 0:
        return 0
    if dry_run:
        log.info('[DRY RUN] Would update %d YODY items', len(needs))
        return len(needs)

    item_map = []
    for idx, row in needs.iterrows():
        m = re.search(r'yody\.vn/product/([^/?#]+)', row['product_url'])
        if m:
            item_map.append((idx, m.group(1)))

    BATCH = 50
    total_updated = 0
    total_errors = 0

    for batch_start in range(0, len(item_map), BATCH):
        batch = item_map[batch_start:batch_start + BATCH]
        chunk_handles = [h for _, h in batch]
        t0 = time.time()
        results = asyncio.run(_yody_batch(chunk_handles, sem_val=4))
        elapsed = time.time() - t0

        result_map = {h: (all_s, in_s) for h, all_s, in_s in results}
        batch_updated = 0

        for idx, handle in batch:
            all_s, in_s = result_map.get(handle, ([], []))
            if all_s:
                df.at[idx, 'available_sizes'] = json.dumps(all_s, ensure_ascii=False)
                df.at[idx, 'sizes_in_stock'] = json.dumps(in_s, ensure_ascii=False)
                batch_updated += 1
            else:
                total_errors += 1

        total_updated += batch_updated
        log.info(
            '  YODY batch %d-%d/%d: %.1fs, %d/%d OK (total updated=%d, errors=%d)',
            batch_start + 1,
            batch_start + len(batch),
            len(item_map),
            elapsed,
            batch_updated,
            len(batch),
            total_updated,
            total_errors,
        )
        if batch_start + BATCH < len(item_map):
            time.sleep(1.0)

    log.info('YODY done: updated=%d, errors=%d', total_updated, total_errors)
    return total_updated

def scrape_canifa(df, dry_run=False):
    canifa = df[df['store_id'] == 'canifa_vn']
    needs = canifa[canifa['available_sizes'] == '[]']
    log.info('Canifa: %d items, %d need update', len(canifa), len(needs))
    if len(needs) == 0:
        return 0
    if dry_run:
        log.info('[DRY RUN] Would update %d Canifa items', len(needs))
        return len(needs)

    cache_dir = CACHE_ROOT / 'canifa_vn'
    updated = errors = 0
    for idx, row in needs.iterrows():
        slug = row['product_url'].split('/')[-1].split('?')[0].rstrip('/')
        if not slug:
            errors += 1; continue
        cache_file = _find_canifa_cache(cache_dir, slug)
        if cache_file is None:
            errors += 1; continue
        try:
            html = cache_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            errors += 1; continue
        sizes = _canifa_sizes_from_html(html)
        if not sizes:
            errors += 1; continue
        df.at[idx, 'available_sizes'] = json.dumps(sizes, ensure_ascii=False)
        df.at[idx, 'sizes_in_stock'] = json.dumps(sizes, ensure_ascii=False)
        updated += 1
    log.info('Canifa done: updated=%d, errors=%d', updated, errors)
    return updated

def main(argv=None):
    ap = ArgumentParser(description='Fill missing size data for YODY and Canifa')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--stores', default='yody_vn,canifa_vn')
    args = ap.parse_args(argv)
    stores = [s.strip() for s in args.stores.split(',')]

    if not LINKS_PARQUET.exists():
        log.error('Not found: %s', LINKS_PARQUET); return 1
    df = pd.read_parquet(LINKS_PARQUET)
    log.info('Loaded %d rows from parquet', len(df))

    total = 0
    if 'yody_vn' in stores:
        log.info('=== YODY ===')
        total += scrape_yody(df, dry_run=args.dry_run)
    if 'canifa_vn' in stores:
        log.info('=== Canifa ===')
        total += scrape_canifa(df, dry_run=args.dry_run)

    if not args.dry_run:
        df.to_parquet(LINKS_PARQUET, index=False)
        log.info('Saved -> %s', LINKS_PARQUET)
        vdf = pd.read_parquet(LINKS_PARQUET)
        for s in stores:
            sub = vdf[vdf['store_id'] == s]
            nonempty = sub[sub['available_sizes'] != '[]']
            log.info('  %s: %d/%d have sizes', s, len(nonempty), len(sub))
    else:
        log.info('[DRY RUN] No changes written')

    log.info('Done. Total updated: %d', total)
    return 0

if __name__ == '__main__':
    sys.exit(main())
