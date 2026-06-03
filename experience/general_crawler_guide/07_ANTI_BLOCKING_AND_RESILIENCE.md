# Anti-Blocking Strategies & Error Resilience

## Common Blocking Mechanisms
1. **Rate Limiting (HTTP 429)**: Server returns "Too Many Requests"
2. **IP Blocking**: Your IP gets banned after too many requests
3. **Bot Detection**: JavaScript checks for automation signatures
4. **CAPTCHA**: Human verification challenges
5. **WAF (Web Application Firewall)**: Cloudflare, AWS WAF, etc.
6. **Popup Overlays**: Marketing popups that block interaction

## Strategy 1: Request Rate Limiting
```python
semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
await asyncio.sleep(0.5)  # 500ms delay between each request
```
Why 5 concurrent and 0.5s delay? This mimics a fast human browsing pattern.
Too fast = blocked. Too slow = scraping takes forever.

## Strategy 2: Exponential Backoff on 429
```python
if response.status == 429:
    wait_time = (2 ** attempt) + 1  # 3s, 5s, 9s, 17s, 33s
    await asyncio.sleep(wait_time)
    continue
```
Each retry waits exponentially longer. 5 retries = up to 33 seconds wait.
This gives the server time to cool down.

## Strategy 3: User-Agent Header
```python
headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
```
Always send a realistic User-Agent. Without it, many servers immediately block.

## Strategy 4: Popup/Overlay Removal
Remove popups BEFORE interacting using DOM evaluation. Look for generic modal/popup classes and remove them from the DOM to ensure CDP clicks work.

## Strategy 5: Incremental Saving
```python
# Save after EACH category completes
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
```
If the script crashes at category 15 of 20, you keep data from categories 1-14.
On next run, already-scraped URLs are skipped.

## Strategy 6: Resume Support
```python
existing_urls = set()
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        existing_data = json.load(f)
    for item in existing_data:
        existing_urls.add(item["_scraped_url"])
# Only scrape new URLs
items_to_scrape = [url for url in all_urls if url not in existing_urls]
```

## Strategy 7: Click Fallback Chain
When AX Tree click fails, try multiple fallback methods:
```python
# Method 1: CDP click via backendDOMNodeId
click_success = await click_node_via_cdp(page, bid)

# Method 2: Click StaticText child node instead  
if not click_success:
    child_text = find_node_by_text_and_role(nodes, text, "StaticText")
    await click_node_via_cdp(page, child_text.bid)

# Method 3: Playwright locator fallback
if still_on_same_page:
    await page.locator(f"a:has-text('{text}')").first.click(timeout=5000)
```

## Strategy 8: State Verification Polling
After toggling a checkbox, verify the change actually happened:
```python
for _ in range(10):
    await asyncio.sleep(1.5)
    new_nodes = await get_ax_tree(page)
    # verify expected state in new nodes...
    if target and target["checked"] == desired_state:
        return True
return False  # State didn't change after 15 seconds
```

## Strategy 9: Desktop Viewport
```python
await page.set_viewport_size({"width": 1920, "height": 1080})
```
Many sites show different layouts on mobile. Ensure desktop layout for consistent scraping.

## Strategy 10: Windows Encoding Fix
```python
import sys, io
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```
Avoids `UnicodeEncodeError` on Windows when encountering special characters.

## Strategy 11: Windows Event Loop Fix
```python
import os, asyncio
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```
Fixes `aiohttp`'s ProactorEventLoop issues on Windows.

## Common Error Scenarios & Solutions
| Error | Cause | Solution |
|-------|-------|----------|
| Connection refused | Chrome not running | Run `chrome.bat` first |
| Node ID not found | Page changed after getting AX tree | Re-fetch AX tree |
| Click has no effect | Popup overlay blocking | Run cleanup first |
| UnicodeEncodeError | Windows console encoding | Add UTF-8 reconfigure code |
| HTTP 429 | Too many requests | Reduce semaphore, add delay |
| Empty AX tree | Page still loading | Add retry loop with sleep |
| JSONDecodeError | Regex captured wrong text | Verify regex against actual HTML |
