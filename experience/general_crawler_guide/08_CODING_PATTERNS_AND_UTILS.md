# Reusable Coding Patterns & Utility Functions

## Foundation: The 3 Core AX Tree Helpers
These 3 functions appear in EVERY script. Copy them first:
```python
def get_role(node):
    return node.get("role", {}).get("value", "")

def get_name(node):
    return node.get("name", {}).get("value", "").strip()

def get_props(node):
    result = {}
    for p in node.get("properties", []):
        pname = p["name"]
        val = p["value"].get("value")
        if val is not None:
            result[pname] = val
    return result
```

## Pattern: Async AX Tree Retrieval with Session Cleanup
```python
async def get_ax_tree(page):
    cdp_session = await page.context.new_cdp_session(page)
    try:
        full_tree = await cdp_session.send("Accessibility.getFullAXTree")
        return full_tree.get("nodes", [])
    finally:
        await cdp_session.detach()  # ALWAYS detach
```
IMPORTANT: Always wrap in try/finally. CDP sessions leak if not detached.

## Pattern: CDP Click with Coordinate Calculation
```python
async def click_node_via_cdp(page, backend_node_id: int):
    cdp = await page.context.new_cdp_session(page)
    try:
        await cdp.send("DOM.scrollIntoViewIfNeeded", {"backendNodeId": backend_node_id})
        await asyncio.sleep(0.5)
        box = await cdp.send("DOM.getBoxModel", {"backendNodeId": backend_node_id})
        content = box["model"]["content"]
        x = (content[0] + content[2]) / 2
        y = (content[1] + content[5]) / 2
        await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        return True
    except Exception as e:
        print(f"Click failed for node {backend_node_id}: {e}")
        return False
    finally:
        await cdp.detach()
```
Coordinate math: `content` array = `[x1,y1, x2,y2, x3,y3, x4,y4]` (quad corners)
Center = average of opposite corners

## Pattern: Find Node by Text and Role
```python
def find_node_by_text_and_role(nodes, target_text, target_role):
    for n in nodes:
        if get_role(n) == target_role and target_text.lower() in get_name(n).lower():
            return n
    return None
```
Uses case-insensitive substring matching for robustness.

## Pattern: Build Parent-Child Tree Maps
```python
def build_tree_maps(nodes):
    id_map = {n["nodeId"]: n for n in nodes}
    children_map = {}
    root = None
    for n in nodes:
        pid = n.get("parentId")
        if pid is None:
            root = n
        else:
            children_map.setdefault(pid, []).append(n["nodeId"])
    # Handle orphan nodes
    if root:
        root_id = root["nodeId"]
        for n in nodes:
            pid = n.get("parentId")
            if pid and pid not in id_map:
                children_map.setdefault(root_id, []).append(n["nodeId"])
    return root, id_map, children_map
```
Orphan handling: Nodes whose parent doesn't exist get attached to root.

## Pattern: Ancestor/Sibling Group Finder
```python
def find_group_for_node(node_id, id_map, children_map, group_names):
    curr_id = node_id
    visited = set()
    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        curr_node = id_map.get(curr_id)
        if not curr_node: break
        name = get_name(curr_node).upper()
        if name in group_names: return name
        pid = curr_node.get("parentId")
        if pid:
            for cid in children_map.get(pid, []):
                cnode = id_map.get(cid)
                if cnode and get_name(cnode).upper() in group_names:
                    return get_name(cnode).upper()
        curr_id = pid
    return None
```

## Pattern: Retry Loop for Dynamic Content
```python
target_node = None
for attempt in range(15):
    nodes = await get_ax_tree(page)
    target_node = find_node_by_text_and_role(nodes, "TARGET_TEXT", "link")
    if target_node:
        break
    await asyncio.sleep(1)
if not target_node:
    print("ERROR: Element not found after 15 attempts")
```

## Pattern: Popup Cleanup
```python
async def clean_popups(page):
    try:
        await page.evaluate("""() => {
            ['#antsomi-slidedown-container', 'div[class*="popup"]', 'div[class*="modal"]', '.modal-backdrop']
            .forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
        }""")
    except: pass
```

## Pattern: Windows Encoding Setup
Put this at the TOP of every script:
```python
import sys, io
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

## Pattern: Async HTTP with Semaphore
```python
semaphore = asyncio.Semaphore(5)
async def fetch(session, url):
    async with semaphore:
        await asyncio.sleep(0.5)  # Rate limit
        async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
            return await resp.text()

async with aiohttp.ClientSession() as session:
    tasks = [fetch(session, url) for url in urls]
    results = await asyncio.gather(*tasks)
```

## Pattern: Incremental JSON Save
```python
results = {}
if os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        results = json.load(f)

results[category_name] = new_data

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
```
Always use `ensure_ascii=False` for Vietnamese text.

## Pattern: Product URL Extraction from AX Tree
```python
def extract_product_urls(nodes, url_pattern="/products/", base_url="https://example.com"):
    urls = set()
    for n in nodes:
        if get_role(n) == "link":
            url = get_props(n).get("url", "")
            if url_pattern in url:
                clean_url = url.split("?")[0]
                if clean_url.startswith("/"):
                    clean_url = base_url + clean_url
                urls.add(clean_url)
    return list(urls)
```

## Pattern: Total Count Extraction
```python
def get_total_count(nodes, pattern_regex):
    for n in nodes:
        if get_role(n) == "StaticText":
            match = re.search(pattern_regex, get_name(n), re.IGNORECASE)
            if match:
                return int(match.group(1))
    return None
```

## Project File Template
Every new scraper script should start with:
```python
import asyncio
import json
import os
import sys
import io
import re
from playwright.async_api import async_playwright

# Windows encoding fix
if sys.platform.startswith("win"):
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Config
CHROME_CDP_URL = "http://localhost:9222"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Core AX Tree helpers
def get_role(node): return node.get("role", {}).get("value", "")
def get_name(node): return node.get("name", {}).get("value", "").strip()
def get_props(node):
    return {p["name"]: p["value"].get("value") for p in node.get("properties", []) if p["value"].get("value") is not None}

async def get_ax_tree(page):
    cdp = await page.context.new_cdp_session(page)
    try:
        return (await cdp.send("Accessibility.getFullAXTree")).get("nodes", [])
    finally:
        await cdp.detach()
```
