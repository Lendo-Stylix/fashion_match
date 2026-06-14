# Accessibility Tree (AX Tree) — Deep Dive

> **Purpose of this document:** Give any developer or AI agent — even one with zero prior context —
> everything needed to retrieve, parse, filter, compact, traverse, and interact with Chrome's
> Accessibility Tree using Playwright + CDP. Every code block is production-tested; every
> design decision is explained with its *why*.

---

## Table of Contents

1. [What is the Accessibility Tree?](#what-is-the-accessibility-tree)
2. [Why We Use the AX Tree Instead of the DOM](#why-we-use-the-ax-tree-instead-of-the-dom)
3. [How to Retrieve the Full AX Tree](#how-to-retrieve-the-full-ax-tree)
4. [Raw AX Tree Node Structure](#raw-ax-tree-node-structure)
5. [Helper Functions to Parse Nodes](#helper-functions-to-parse-nodes)
6. [The 3-Stage Processing Pipeline](#the-3-stage-processing-pipeline)
7. [How to Read the Compact AX Tree](#how-to-read-the-compact-ax-tree)
8. [Building Parent-Child Maps](#building-parent-child-maps)
9. [Finding a Node's Group via Ancestor / Sibling Traversal](#finding-a-nodes-group-via-ancestor--sibling-traversal)
10. [Interacting with AX Tree Nodes (Click)](#interacting-with-ax-tree-nodes-click)
11. [Typing Text into Input Fields](#typing-text-into-input-fields)
12. [Common Pitfalls & Debugging](#common-pitfalls--debugging)
13. [Performance Characteristics](#performance-characteristics)
14. [Quick Reference Cheat-Sheet](#quick-reference-cheat-sheet)

---

## What is the Accessibility Tree?

Chrome (and every modern browser) maintains **two parallel representations** of every web page:

| Representation | What it contains | Who uses it |
|---|---|---|
| **DOM Tree** | Every HTML element, CSS class, inline style, wrapper div, script tag, etc. | The rendering engine (Blink) |
| **Accessibility Tree (AX Tree)** | A **semantic** view — only the elements that carry meaning: buttons, links, headings, text, images with alt-text, form controls, landmarks | Screen readers (NVDA, JAWS, VoiceOver) and — critically for us — **automated scrapers** |

### How Chrome builds the AX Tree

1. Chrome walks the DOM top-to-bottom.
2. For each DOM element it asks: *"Does this element have a semantic role?"*
   - A `<button>` → role `button`
   - A `<a href="...">` → role `link`
   - A `<div>` with no ARIA attributes → role `generic` (often ignored)
   - A `<div role="navigation">` → role `navigation` (a landmark)
3. Chrome computes the **accessible name** for each node using a complex algorithm
   ([Accessible Name and Description Computation](https://www.w3.org/TR/accname-1.1/)):
   - `aria-label` attribute wins first
   - Then `aria-labelledby` (referencing another element's text)
   - Then the element's **text content** (for buttons, links)
   - Then `alt` (for images)
   - Then `title` or `placeholder`
4. Chrome attaches **properties/states**: focused, disabled, expanded, checked, etc.
5. The result is a lean tree where every node has: `role`, `name`, `properties`, and parent/child relationships.

### What gets stripped away

The AX tree **does not contain**:
- CSS class names (`.product-card`, `.filter-wrapper`)
- Inline styles (`style="display:flex"`)
- Purely decorative `<div>` / `<span>` wrappers
- `<script>` and `<style>` tags
- Hidden elements (`display:none`, `aria-hidden="true"`)
- Comment nodes

This is exactly why it's so useful for scraping: **it's pre-cleaned**.

---

## Why We Use the AX Tree Instead of the DOM

This is a critical design decision. Here's the full reasoning:

### Problem: DOM is noisy and brittle

A typical e-commerce product card in the DOM might look like:

```html
<div class="sc-1a2b3c product-card__wrapper">
  <div class="sc-4d5e6f product-card__inner">
    <div class="sc-7g8h9i product-card__image-container">
      <a href="/product/ao-polo" class="sc-jk0l1m">
        <img src="..." alt="Áo Polo Ngắn Tay" class="sc-2n3o4p" />
      </a>
    </div>
    <div class="sc-5q6r7s product-card__info">
      <a href="/product/ao-polo" class="sc-8t9u0v product-card__title">
        <h3 class="sc-1w2x3y">Áo Polo Ngắn Tay</h3>
      </a>
      <div class="sc-4z5a6b product-card__price">
        <span class="sc-7c8d9e">599,000₫</span>
      </div>
    </div>
  </div>
</div>
```

That's **10+ elements** for what is semantically just: a link with a name, an image, a heading, and a price.

### Solution: AX Tree gives you the semantic skeleton

The same card in the AX tree:

```
link | "Áo Polo Ngắn Tay" | id=1234 | url=/product/ao-polo
  img | "Áo Polo Ngắn Tay" | id=1235
heading | "Áo Polo Ngắn Tay" | id=1240 | level=3
StaticText | "599,000₫" | id=1245
```

**4 nodes** instead of 10+. No CSS class names that change on every deploy.

### Specific advantages for scraping

| Advantage | Explanation |
|---|---|
| **Resilience** | CSS class names change when the site rebuilds (`sc-1a2b3c` → `sc-9x8y7z`). AX tree roles never change — a button is always a button. |
| **Smaller payload** | A full DOM might be 5-10MB of HTML. The compact AX tree is 30-80KB of text. |
| **LLM-friendly** | You can feed the compact AX tree directly to an LLM and ask "which checkbox should I click?" The LLM can actually understand the 50KB tree. It cannot process 5MB of HTML. |
| **Built-in semantics** | No need to guess "is this div a button?" Chrome already figured that out. |
| **Interaction-ready** | Every interactive node has a `backendDOMNodeId` you can use to click it via CDP. |

### When NOT to use the AX Tree

- When you need **CSS-based visual layout** information (grid positions, colors)
- When you need to extract `data-*` attributes that aren't exposed to accessibility
- When the site has **very poor accessibility** (no ARIA roles, no semantic HTML) — the AX tree will be nearly empty. In practice this is rare for modern e-commerce sites.

---

## How to Retrieve the Full AX Tree

### The Core Function

```python
async def get_ax_tree(page):
    """
    Retrieve the full Accessibility Tree for the current page via CDP.
    
    Returns:
        list[dict]: A list of AX tree nodes. Each node is a dict with keys:
                    nodeId, role, name, properties, childIds, parentId, 
                    backendDOMNodeId, ignored, etc.
    
    IMPORTANT: Creates and detaches a CDP session each call to avoid stale sessions.
    """
    cdp_session = await page.context.new_cdp_session(page)
    try:
        full_tree = await cdp_session.send("Accessibility.getFullAXTree")
        return full_tree.get("nodes", [])
    finally:
        await cdp_session.detach()
```

### Why `finally: await cdp_session.detach()`?

Every call to `page.context.new_cdp_session(page)` opens a new DevTools Protocol
session — essentially a WebSocket connection to Chrome's internals. If you don't
detach:

1. **Resource leak**: Each session holds memory in both the Python process and the
   Chrome process. After 20-30 un-detached sessions, Chrome starts to slow down.
2. **Connection limit**: Chrome has a limit on concurrent CDP connections per target.
   You'll get `"Target already has an attached session"` errors.

The `try/finally` pattern guarantees detachment even if `send()` throws an exception.

### Why create a NEW session each time?

```python
# ❌ BAD: Reusing a session across navigations
cdp = await page.context.new_cdp_session(page)
await page.goto("https://site.com/page1")
tree1 = await cdp.send("Accessibility.getFullAXTree")  # Works
await page.goto("https://site.com/page2")
tree2 = await cdp.send("Accessibility.getFullAXTree")  # 💥 May fail or return stale data!

# ✅ GOOD: New session per retrieval
tree1 = await get_ax_tree(page)  # Session created + detached internally
await page.goto("https://site.com/page2")
tree2 = await get_ax_tree(page)  # Fresh session, fresh data
```

When a page navigates, the underlying Chrome target may change or the DOM is
completely replaced. A CDP session attached to the old page is now stale. The call
may silently succeed but return data from a destroyed document, or it may throw a
`"Session closed"` / `"Target closed"` error. **Always create fresh.**

### Timing: When to call `get_ax_tree`

The AX tree reflects the **current state** of the page. If the page is still loading
or an animation is in progress, you'll get an incomplete tree. Best practice:

```python
# Wait for the page to be fully loaded and idle
await page.wait_for_load_state("networkidle")
await asyncio.sleep(1)  # Extra safety margin for JS-rendered content

# NOW get the tree
nodes = await get_ax_tree(page)
```

For single-page apps (React, Vue) that update via AJAX without full page loads:

```python
# After clicking a filter that triggers AJAX
await click_node_via_cdp(page, checkbox_id)
await asyncio.sleep(2)  # Wait for AJAX + re-render
nodes = await get_ax_tree(page)  # Fresh tree reflecting new state
```

---

## Raw AX Tree Node Structure

Here is an actual node from `Accessibility.getFullAXTree` on an Aristino product page,
with annotations:

```json
{
  "nodeId": "abcd-1234",
  "ignored": false,
  "role": {
    "type": "role",
    "value": "link"
  },
  "name": {
    "type": "computedString",
    "value": "TRANG PHỤC"
  },
  "properties": [
    {
      "name": "url",
      "value": {
        "type": "string",
        "value": "https://aristino.com/collections/trang-phuc"
      }
    },
    {
      "name": "focused",
      "value": {
        "type": "boolean",
        "value": false
      }
    }
  ],
  "childIds": ["child-1", "child-2"],
  "parentId": "parent-xyz",
  "backendDOMNodeId": 536
}
```

### Field-by-field explanation

| Field | Type | Meaning |
|---|---|---|
| `nodeId` | string | Internal AX tree ID. Used for parent-child relationships within the AX tree. **Not** the DOM node ID. Changes between tree retrievals. |
| `ignored` | boolean | If `true`, Chrome determined this node is not semantically meaningful (e.g., a purely decorative `<div>`). **Always filter these out.** |
| `role` | `{type, value}` | The semantic role. Common values: `link`, `button`, `textbox`, `heading`, `checkbox`, `StaticText`, `generic`, `navigation`, `main`, `img`, `RootWebArea` |
| `name` | `{type, value}` | The accessible name — the text that a screen reader would announce. For a link, it's the link text. For an image, it's the alt text. For a heading, it's the heading text. |
| `properties` | `[{name, value}]` | Additional state/properties. Common: `url` (links), `focused`, `disabled`, `expanded`, `checked`, `level` (headings), `editable`, `required`, `value` (inputs) |
| `childIds` | `[string]` | List of `nodeId`s for this node's children in the AX tree. |
| `parentId` | string | `nodeId` of this node's parent. The root node has no `parentId`. |
| `backendDOMNodeId` | integer | **THE MOST IMPORTANT FIELD FOR INTERACTION.** This is the stable ID that maps back to the actual DOM element. Used by `DOM.scrollIntoViewIfNeeded`, `DOM.getBoxModel`, etc. |

### About `backendDOMNodeId`

This integer is Chrome's internal identifier for the DOM node. Unlike `nodeId` (which is
an AX-tree-internal string that changes each time you call `getFullAXTree`), the
`backendDOMNodeId` is **stable** as long as the DOM element exists. This is what we use
to interact with elements:

```python
# The "id" we track in compact text (e.g., "id=536") is backendDOMNodeId
backend_id = node.get("backendDOMNodeId")
if backend_id:
    await click_node_via_cdp(page, backend_id)
```

### Nodes that DON'T have `backendDOMNodeId`

Some AX nodes are "virtual" — they don't map to a single DOM element. Examples:
- The `RootWebArea` node sometimes doesn't have one
- Nodes generated by `aria-owns` relationships

Always check `if node.get("backendDOMNodeId")` before trying to interact.

### Name types

The `name.type` field tells you how Chrome computed the name:

| `name.type` | Source |
|---|---|
| `computedString` | Chrome computed the name from the element's content, `aria-label`, `aria-labelledby`, etc. |
| `attribute` | Came directly from an attribute like `alt` or `title` |
| `contents` | Derived from the element's text content |

In practice, you don't need to differentiate — just read `name.value`.

---

## Helper Functions to Parse Nodes

These three tiny functions are the **foundation** of all AX tree work. Every other
function in the codebase calls them.

```python
def get_role(node: dict) -> str:
    """
    Extract the semantic role from an AX node.
    
    Examples: "link", "button", "heading", "StaticText", "generic", "RootWebArea"
    Returns empty string if role is missing (should never happen for valid nodes).
    """
    return node.get("role", {}).get("value", "")


def get_name(node: dict) -> str:
    """
    Extract the accessible name from an AX node.
    
    This is the human-readable label: "TRANG PHỤC", "Áo Polo", "599,000₫", etc.
    Returns empty string if the node has no name (common for container nodes like
    'navigation' or 'main').
    
    Note: .strip() removes leading/trailing whitespace which is common in computed names.
    """
    return node.get("name", {}).get("value", "").strip()


def get_props(node: dict) -> dict:
    """
    Extract all properties/states from an AX node into a flat dict.
    
    Raw properties look like:
        [{"name": "url", "value": {"type": "string", "value": "https://..."}}, ...]
    
    This returns:
        {"url": "https://...", "focused": False, "expanded": True, ...}
    
    Skips properties where value is None (these are meaningless).
    """
    result = {}
    for p in node.get("properties", []):
        pname = p["name"]
        val = p["value"].get("value")
        if val is not None:
            result[pname] = val
    return result
```

### Why these exist as separate functions

The raw node structure nests values inside `{"type": ..., "value": ...}` wrappers.
Writing `node.get("role", {}).get("value", "")` every time is:
1. Error-prone (forget one `.get()` and you get a `KeyError`)
2. Verbose (clutters the actual logic)
3. Non-obvious (new readers don't know the nesting pattern)

By abstracting into `get_role()`, `get_name()`, `get_props()`, the rest of the code
reads like English:

```python
# Clear and readable
if get_role(node) == "checkbox" and "Áo Polo" in get_name(node):
    props = get_props(node)
    if not props.get("checked"):
        await click_node_via_cdp(page, node["backendDOMNodeId"])
```

### Usage pattern

```python
for node in filtered_nodes:
    role = get_role(node)
    name = get_name(node)
    props = get_props(node)
    backend_id = node.get("backendDOMNodeId")
    
    if role == "link" and "trang-phuc" in props.get("url", ""):
        print(f"Found category link: {name} -> {props['url']}")
```

---

## The 3-Stage Processing Pipeline

This is the core data pipeline. Raw AX tree → filtered → compact text.

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Stage 1     │     │  Stage 2        │     │  Stage 3         │
│  Raw Dump    │────▶│  Filter Ignored │────▶│  Compact Text    │
│  (~2MB JSON) │     │  (~1.5MB JSON)  │     │  (~50KB text)    │
└──────────────┘     └─────────────────┘     └──────────────────┘
```

### Stage 1: Raw Dump

Save the **full, unmodified** AX tree to disk. This is your ground truth for debugging.

```python
import json

async def stage1_raw_dump(page, output_path="ax_full_raw.json"):
    """
    Retrieve and save the complete AX tree with zero modifications.
    
    Why save raw?
    - If Stage 2/3 filtering is too aggressive, you can re-process from raw
    - Useful for debugging: "did the AX tree even contain this element?"
    - Reference for understanding the raw format
    """
    nodes = await get_ax_tree(page)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
    
    print(f"Stage 1: Saved {len(nodes)} raw nodes to {output_path}")
    print(f"         File size: {os.path.getsize(output_path) / 1024:.0f} KB")
    
    return nodes
```

**Typical sizes observed:**

| Site | Raw nodes | File size |
|---|---|---|
| Aristino category page (all products loaded) | ~8,000–12,000 | 1.5–2.5 MB |
| Aristino product detail page | ~3,000–5,000 | 0.6–1.0 MB |
| Aristino homepage | ~5,000–8,000 | 1.0–1.8 MB |

### Stage 2: Filter Ignored Nodes

Chrome marks certain nodes as `ignored: true`. These are nodes that the accessibility
engine determined are **not meaningful** for assistive technology. Examples:
- Empty `<div>` wrappers
- `<span>` elements whose text is already exposed by a parent
- Elements hidden with `aria-hidden="true"`
- Presentational elements (`role="presentation"` or `role="none"`)

```python
def stage2_filter_ignored(nodes):
    """
    Remove nodes that Chrome marked as ignored.
    
    Why Chrome ignores nodes:
    - role="presentation" or role="none" → explicitly decorative
    - aria-hidden="true" → intentionally hidden from assistive tech
    - Empty containers with no accessible content
    - Redundant text nodes whose content is already in a parent's name
    
    Returns: filtered list (typically 70-80% of original size)
    """
    filtered = [node for node in nodes if not node.get("ignored")]
    
    removed = len(nodes) - len(filtered)
    pct = (removed / len(nodes) * 100) if nodes else 0
    print(f"Stage 2: {len(nodes)} → {len(filtered)} nodes ({removed} removed, {pct:.0f}%)")
    
    return filtered
```

**Why not skip Stage 2 and go straight from raw to compact?**

You could. But filtering ignored nodes first:
1. Reduces the input size for Stage 3 (faster processing)
2. Prevents edge cases where an ignored node is the parent of kept nodes (the compact
   builder would need to handle `ignored` parents, which adds complexity)
3. Makes the intermediate JSON (`ax_filtered.json`) useful for analysis — it contains
   only real semantic nodes, in the original JSON format

### Stage 3: Compact Text Representation

This is the **key innovation** that makes the AX tree usable for LLM-based analysis.
We transform the filtered JSON tree into an indented text format that:
- Preserves the tree structure (via indentation)
- Preserves all semantically important information (role, name, id, states)
- Discards noise (generic wrappers, inline text boxes)
- Is small enough to fit in an LLM context window (~50KB vs ~2MB)

#### Node Categorization

```python
# Nodes that represent things users can interact with
INTERACTIVE = {
    "button",       # Clickable buttons
    "link",         # Hyperlinks
    "textbox",      # Text input fields
    "searchbox",    # Search input fields
    "combobox",     # Dropdown selectors
    "listbox",      # List selection widgets
    "option",       # Options within listbox/combobox
    "checkbox",     # Checkboxes (filters!)
    "radio",        # Radio buttons
    "menuitem",     # Items in dropdown menus
    "tab",          # Tab controls
    "switch",       # Toggle switches
    "slider",       # Range sliders (e.g., price range)
}

# Major page sections (HTML5 landmarks / ARIA landmarks)
LANDMARK = {
    "banner",         # <header> — page header
    "contentinfo",    # <footer> — page footer
    "navigation",     # <nav> — navigation menus
    "main",           # <main> — primary content area
    "search",         # Search section
    "region",         # <section> with aria-label
    "complementary",  # <aside> — sidebar content
    "form",           # <form> elements
    "dialog",         # Modal dialogs, popups
}

# Structural elements that give meaning to content organization
STRUCTURE = {
    "heading",     # <h1>–<h6> — section titles
    "list",        # <ul>, <ol> — lists
    "listitem",    # <li> — individual list items
    "separator",   # <hr> — thematic breaks
}

# The root of the entire page
ROOT = {"RootWebArea"}

# Noise nodes — skip them but recurse into their children
SKIP = {
    "generic",         # <div>, <span> with no semantic role
    "InlineTextBox",   # Chrome's internal text rendering nodes
    "none",            # role="none" (same as presentation)
}

# Properties worth showing in the compact output
KEEP_PROPS = {
    "focused",    # Is this element currently focused?
    "disabled",   # Is this element disabled/grayed out?
    "expanded",   # Is this dropdown/accordion expanded?
    "checked",    # Is this checkbox/radio checked?
    "level",      # Heading level (1-6) — critical for structure understanding
    "url",        # Link target URL — critical for navigation
    "editable",   # Is this text field editable?
    "required",   # Is this form field required?
}
```

#### The Compact Builder

```python
def stage3_compact_text(filtered_nodes):
    """
    Transform filtered AX nodes into an indented text tree.
    
    The algorithm:
    1. Build parent-child relationships from nodeId/parentId/childIds
    2. Starting from the root, recursively walk the tree
    3. For each node, decide: KEEP (output a line), SKIP (don't output but visit children),
       or DROP (don't output and don't visit children)
    4. Indentation depth = tree depth from root (2 spaces per level)
    
    Returns: string containing the full compact tree
    """
    # Build lookup maps
    root, id_map, children_map = build_tree_maps(filtered_nodes)
    
    if not root:
        return "(empty tree — no root node found)"
    
    lines = []
    
    def should_keep(node):
        """Decide whether to output a line for this node."""
        role = get_role(node)
        name = get_name(node)
        
        # Always keep root, interactive, and landmark nodes
        if role in ROOT or role in INTERACTIVE or role in LANDMARK:
            return True
        
        # Keep structure nodes if they have a name or have children
        if role in STRUCTURE:
            has_children = bool(children_map.get(node["nodeId"]))
            return bool(name) or has_children
        
        # Keep StaticText if the text is meaningful (more than 1 char)
        if role == "StaticText":
            return len(name) > 1
        
        # Keep images that have alt text (accessible name)
        if role == "img":
            return bool(name)
        
        # Skip generic/InlineTextBox/none but recurse into children
        if role in SKIP:
            return False  # Will still visit children
        
        # For any other role, keep if it has a name
        return bool(name)
    
    def format_node(node):
        """Format a single node into: role | "name" | id=XXX | state1, state2"""
        role = get_role(node)
        name = get_name(node)
        props = get_props(node)
        backend_id = node.get("backendDOMNodeId")
        
        parts = [role]
        
        if name:
            # Truncate very long names (e.g., entire paragraphs)
            display_name = name[:120] + "…" if len(name) > 120 else name
            parts.append(f'"{display_name}"')
        
        if backend_id is not None:
            parts.append(f"id={backend_id}")
        
        # Add relevant properties
        state_parts = []
        for prop_name in KEEP_PROPS:
            if prop_name in props:
                val = props[prop_name]
                if isinstance(val, bool):
                    if val:
                        state_parts.append(prop_name)
                    # Don't show "focused=false", "disabled=false" etc.
                else:
                    state_parts.append(f"{prop_name}={val}")
        
        if state_parts:
            parts.append(", ".join(state_parts))
        
        return " | ".join(parts)
    
    def walk(node_id, depth=0):
        """Recursively walk the tree and build output lines."""
        node = id_map.get(node_id)
        if not node:
            return
        
        indent = "  " * depth
        
        if should_keep(node):
            lines.append(f"{indent}{format_node(node)}")
            # Visit children at depth+1
            for child_id in children_map.get(node_id, []):
                walk(child_id, depth + 1)
        else:
            # Skip this node but visit children at SAME depth (don't increase indent)
            # This "hoists" children up, eliminating the generic wrapper
            for child_id in children_map.get(node_id, []):
                walk(child_id, depth)
    
    walk(root["nodeId"], depth=0)
    
    result = "\n".join(lines)
    
    print(f"Stage 3: {len(filtered_nodes)} nodes → {len(lines)} lines")
    print(f"         Text size: {len(result) / 1024:.0f} KB")
    
    return result
```

#### Why skip generic nodes but still visit their children?

Consider this DOM structure:

```html
<nav>                          <!-- role="navigation" -->
  <div class="nav-wrapper">   <!-- role="generic" → SKIP -->
    <div class="nav-inner">   <!-- role="generic" → SKIP -->
      <a href="/shirts">      <!-- role="link" → KEEP -->
        Áo Sơ Mi
      </a>
    </div>
  </div>
</nav>
```

If we simply dropped `generic` nodes and their children, we'd lose the link entirely.
Instead, we skip the `generic` wrappers but recurse into their children **at the same
indentation level**. The result is:

```
navigation | id=500
  link | "Áo Sơ Mi" | id=520 | url=/shirts
```

The two meaningless `<div>` wrappers are gone. The link appears directly under its
landmark ancestor. Clean and correct.

#### Full pipeline combined

```python
async def process_ax_tree(page, output_dir="ax_output"):
    """Run the complete 3-stage pipeline."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Stage 1: Raw dump
    raw_nodes = await stage1_raw_dump(
        page, 
        os.path.join(output_dir, "ax_full_raw.json")
    )
    
    # Stage 2: Filter
    filtered_nodes = stage2_filter_ignored(raw_nodes)
    with open(os.path.join(output_dir, "ax_filtered.json"), "w", encoding="utf-8") as f:
        json.dump(filtered_nodes, f, ensure_ascii=False, indent=2)
    
    # Stage 3: Compact
    compact_text = stage3_compact_text(filtered_nodes)
    with open(os.path.join(output_dir, "ax_compact.txt"), "w", encoding="utf-8") as f:
        f.write(compact_text)
    
    return raw_nodes, filtered_nodes, compact_text
```

#### Compression results (real-world example)

| Stage | Size | Notes |
|---|---|---|
| Stage 1: `ax_full_raw.json` | 2,100 KB | 11,432 nodes |
| Stage 2: `ax_filtered.json` | 1,580 KB | 8,201 nodes (28% removed) |
| Stage 3: `ax_compact.txt` | 48 KB | 1,847 lines |

**Compression ratio: 97.7%** — from 2.1MB to 48KB while preserving all actionable information.

This 48KB text easily fits in any modern LLM's context window.

---

## How to Read the Compact AX Tree

The compact text is designed to be immediately readable by both humans and LLMs.
Here's how to decode it:

### Format

```
role | "name" | id=XXX | state1, state2, key=value
```

Each pipe-separated field:
1. **Role**: The semantic type (`button`, `link`, `heading`, `checkbox`, etc.)
2. **Name** (in quotes): The human-readable label (may be omitted for containers)
3. **id=XXX**: The `backendDOMNodeId` for interaction (may be omitted for virtual nodes)
4. **States**: Comma-separated list of active states/properties

### Indentation = hierarchy

```
RootWebArea | "Áo Sơ Mi Nam | Aristino" | id=315 | focused, url=https://aristino.com/...
  banner | id=461
    navigation | id=480
      link | "TRANG PHỤC" | id=510 | url=https://aristino.com/collections/trang-phuc
      link | "ÁO" | id=525 | url=https://aristino.com/collections/ao
  main | id=901
    heading | "BỘ LỌC" | id=1046 | level=3
    button | "SẢN PHẨM" | id=1105 | expanded
      checkbox | "Áo Blazer" | id=1111
      checkbox | "Áo Polo ngắn tay" | id=1150
      checkbox | "Áo Sơ Mi Dài Tay" | id=1189 | checked
    button | "KÍCH CỠ" | id=1300 | expanded
      checkbox | "S" | id=1310
      checkbox | "M" | id=1320
      checkbox | "L" | id=1330
    heading | "DANH SÁCH SẢN PHẨM" | id=2000 | level=2
    link | "Áo Sơ Mi Dài Tay ASDL-2301" | id=2050 | url=/product/asdl-2301
    StaticText | "599,000₫" | id=2080
```

### Reading this tree, you can immediately understand

1. **Page structure**: banner → navigation (with category links), then main content area
2. **Filter panel**: "BỘ LỌC" heading, with collapsible filter groups:
   - "SẢN PHẨM" (product type) — expanded, with unchecked/checked checkboxes
   - "KÍCH CỠ" (size) — expanded, with size options
3. **Product listing**: heading "DANH SÁCH SẢN PHẨM", followed by product links and prices
4. **Currently applied filter**: "Áo Sơ Mi Dài Tay" checkbox is `checked`

### State reference

| State | Meaning | Example context |
|---|---|---|
| `focused` | Element has keyboard focus | Currently selected input |
| `disabled` | Element is grayed out / not interactive | Sold-out size option |
| `expanded` | Collapsible section is open | Filter group showing its options |
| `checked` | Checkbox/radio is selected | Active filter checkbox |
| `level=N` | Heading level (1-6) | `level=1` = main title, `level=3` = subsection |
| `url=...` | Link destination | Navigate to this URL |
| `editable` | Text field accepts input | Search box, quantity input |
| `required` | Form field must be filled | Required checkout field |

---

## Building Parent-Child Maps

The AX tree arrives as a **flat list** of nodes with `parentId` and `childIds` references.
To traverse it as an actual tree, you need lookup maps.

```python
def build_tree_maps(nodes):
    """
    Build efficient lookup structures from the flat node list.
    
    Returns:
        root (dict): The root node (RootWebArea, has no parentId)
        id_map (dict): nodeId → node dict (O(1) lookup by AX tree ID)
        children_map (dict): nodeId → [child_nodeId, ...] (O(1) lookup of children)
    
    Why build both id_map and children_map?
    - id_map: needed to go FROM a nodeId TO the full node data
    - children_map: needed to traverse DOWN the tree (parent → children)
    - parentId field on each node: needed to traverse UP the tree (child → parent)
    
    Note: We build children_map from parentId (bottom-up) rather than childIds because
    childIds is sometimes incomplete in the raw data (Chrome optimization). Building
    from parentId is always reliable.
    """
    id_map = {n["nodeId"]: n for n in nodes}
    children_map = {}
    root = None
    
    for n in nodes:
        nid = n["nodeId"]
        pid = n.get("parentId")
        
        if pid is None:
            # Node with no parent = the root of the tree
            root = n
        else:
            # Add this node as a child of its parent
            children_map.setdefault(pid, []).append(nid)
    
    return root, id_map, children_map
```

### Usage example: finding all checkboxes and their parent groups

```python
root, id_map, children_map = build_tree_maps(filtered_nodes)

# Find all checkboxes
checkboxes = [n for n in filtered_nodes if get_role(n) == "checkbox"]

for cb in checkboxes:
    name = get_name(cb)
    props = get_props(cb)
    checked = props.get("checked", False)
    backend_id = cb.get("backendDOMNodeId")
    
    # Walk up to find parent button (the filter group header)
    parent_id = cb.get("parentId")
    parent = id_map.get(parent_id) if parent_id else None
    group = get_name(parent) if parent else "Unknown"
    
    print(f"[{'✓' if checked else ' '}] {name} (group: {group}, id={backend_id})")
```

Output:
```
[ ] Áo Blazer (group: SẢN PHẨM, id=1111)
[ ] Áo Polo ngắn tay (group: SẢN PHẨM, id=1150)
[✓] Áo Sơ Mi Dài Tay (group: SẢN PHẨM, id=1189)
[ ] S (group: KÍCH CỠ, id=1310)
[ ] M (group: KÍCH CỠ, id=1320)
```

### Why `children_map.setdefault(pid, []).append(nid)` instead of `childIds`?

Each node already has a `childIds` field — why not just use that? Two reasons:

1. **Consistency with filtering**: After Stage 2 (filtering ignored nodes), the
   `childIds` arrays still reference removed nodes. Building from `parentId` only
   creates entries for nodes that actually exist in the filtered set.

2. **Reliability**: In rare cases, Chrome doesn't populate `childIds` completely for
   deeply nested subtrees (an internal optimization). `parentId` is always present.

---

## Finding a Node's Group via Ancestor / Sibling Traversal

### The problem

On an e-commerce filter panel, checkboxes are grouped under headings or expandable
buttons. The AX tree might look like:

```
button | "SẢN PHẨM" | id=1105 | expanded        ← group header
  checkbox | "Áo Blazer" | id=1111               ← checkbox is CHILD of the group
  checkbox | "Áo Polo" | id=1150

button | "KÍCH CỠ" | id=1300 | expanded           ← another group header
  checkbox | "S" | id=1310
  checkbox | "M" | id=1320
```

But sometimes the structure is different — the heading is a **sibling** of the
checkbox container, not a parent:

```
heading | "SẢN PHẨM" | id=1100                    ← group header is a SIBLING
generic (skipped)
  checkbox | "Áo Blazer" | id=1111                 ← checkbox is NOT a direct child
  checkbox | "Áo Polo" | id=1150
heading | "KÍCH CỠ" | id=1290
```

We need an algorithm that handles **both** patterns.

### The solution: Walk up and check siblings at each level

```python
def find_group_for_node(node_id, id_map, children_map, group_names):
    """
    Determine which filter group a node belongs to by walking up the tree.
    
    Algorithm:
    1. Start at the target node
    2. Check: is this node itself a group header? (Unlikely for a checkbox, but check anyway)
    3. Move to the parent. Check all of the parent's children (= the node's siblings).
       If any sibling's name matches a known group name, that's our group.
    4. Repeat: move to grandparent, check grandparent's children (= parent's siblings).
    5. Stop when a match is found or we reach the root.
    
    Args:
        node_id: The nodeId (AX tree ID) of the target node (e.g., a checkbox)
        id_map: nodeId → node dict (from build_tree_maps)
        children_map: nodeId → [child_nodeIds] (from build_tree_maps)
        group_names: set of UPPERCASE group name strings to match against
                     e.g., {"SẢN PHẨM", "KÍCH CỠ", "MÀU SẮC", "CHẤT LIỆU"}
    
    Returns:
        The matched group name (UPPERCASE) or None if no group found.
    
    Why UPPERCASE comparison?
        AX tree names might have inconsistent casing: "Sản Phẩm", "SẢN PHẨM", "sản phẩm".
        By comparing in UPPERCASE, we handle all variants.
    """
    curr_id = node_id
    visited = set()  # Prevent infinite loops in case of circular references (shouldn't happen, but safety first)
    
    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        curr_node = id_map.get(curr_id)
        if not curr_node:
            break
        
        # Check current node's name
        name = get_name(curr_node).upper()
        if name in group_names:
            return name
        
        # Check siblings (other children of the same parent)
        pid = curr_node.get("parentId")
        if pid:
            for cid in children_map.get(pid, []):
                cnode = id_map.get(cid)
                if cnode and get_name(cnode).upper() in group_names:
                    return get_name(cnode).upper()
        
        # Move up to parent and repeat
        curr_id = pid
    
    return None
```

### Visual walkthrough

Given this tree:

```
region | id=1000
  heading | "SẢN PHẨM" | id=1100      ← Known group name
  generic | id=1105                     ← Wrapper (skipped in compact output)
    checkbox | "Áo Blazer" | id=1111   ← TARGET NODE
```

Step-by-step for `find_group_for_node("ax-id-of-1111", ...)`:

| Step | Current node | Check node name | Check siblings | Result |
|---|---|---|---|---|
| 1 | checkbox "Áo Blazer" | "ÁO BLAZER" ∉ group_names | siblings of generic container: [checkbox, checkbox, ...] — no match | Continue up |
| 2 | generic (id=1105) | "" ∉ group_names | siblings: heading "SẢN PHẨM" ← **match!** | Return "SẢN PHẨM" |

The algorithm found the group after just 2 hops because the heading was a **sibling** of
the checkbox's parent.

### Usage in scraping

```python
GROUP_NAMES = {"SẢN PHẨM", "KÍCH CỠ", "MÀU SẮC", "CHẤT LIỆU", "KIỂU DÁNG"}

root, id_map, children_map = build_tree_maps(filtered_nodes)

# Build a structured view of all filters
filter_groups = {}
for node in filtered_nodes:
    if get_role(node) == "checkbox":
        group = find_group_for_node(node["nodeId"], id_map, children_map, GROUP_NAMES)
        if group:
            filter_groups.setdefault(group, []).append({
                "name": get_name(node),
                "checked": get_props(node).get("checked", False),
                "backend_id": node.get("backendDOMNodeId"),
            })

# Result:
# {
#   "SẢN PHẨM": [
#     {"name": "Áo Blazer", "checked": False, "backend_id": 1111},
#     {"name": "Áo Polo ngắn tay", "checked": False, "backend_id": 1150},
#   ],
#   "KÍCH CỠ": [
#     {"name": "S", "checked": False, "backend_id": 1310},
#     {"name": "M", "checked": False, "backend_id": 1320},
#   ],
# }
```

---

## Interacting with AX Tree Nodes (Click)

Once you've identified a node to interact with (using its `backendDOMNodeId`), you need
to click it. Playwright's built-in click methods work with CSS selectors, but we don't
have selectors — we have backend node IDs. So we use CDP directly.

### The Complete Click Function

```python
import asyncio

async def click_node_via_cdp(page, backend_node_id):
    """
    Click a DOM element using its backendDOMNodeId via Chrome DevTools Protocol.
    
    This replaces Playwright's page.click() when you only have a backend node ID
    (which is what the AX tree gives you) and no CSS selector.
    
    The process:
    1. Scroll the element into the viewport (it might be off-screen)
    2. Wait for scroll animation to settle
    3. Get the element's bounding box (pixel coordinates)
    4. Calculate the center point
    5. Dispatch mousePressed + mouseReleased at the center (= a click)
    
    Args:
        page: Playwright page object
        backend_node_id: int, the backendDOMNodeId from the AX tree node
    
    Returns:
        True if click succeeded, False if any step failed
    """
    cdp = await page.context.new_cdp_session(page)
    try:
        # ─── Step 1: Scroll element into view ───
        # If the element is below the fold (off-screen), the coordinates from
        # getBoxModel would be outside the viewport and the click would miss.
        # scrollIntoViewIfNeeded handles all scroll containers (not just the page).
        await cdp.send("DOM.scrollIntoViewIfNeeded", {
            "backendNodeId": backend_node_id
        })
        
        # ─── Step 2: Wait for scroll animation ───
        # Many sites have smooth scrolling CSS. If we get coordinates immediately,
        # the element might still be moving. 0.5s handles most animations.
        await asyncio.sleep(0.5)
        
        # ─── Step 3: Get bounding box ───
        # getBoxModel returns the CSS box model: content, padding, border, margin
        # as arrays of quad coordinates (4 corners × 2 values = 8 numbers).
        box = await cdp.send("DOM.getBoxModel", {
            "backendNodeId": backend_node_id
        })
        
        # ─── Step 4: Calculate center point ───
        # The "content" quad is the innermost box (excluding padding/border/margin).
        # It's an array of 8 values: [x1,y1, x2,y2, x3,y3, x4,y4]
        # representing the 4 corners of the content area:
        #
        #   (x1,y1) ──── (x2,y2)      [0,1] ──── [2,3]
        #      │            │             │           │
        #      │  content   │             │  content  │
        #      │            │             │           │
        #   (x4,y4) ──── (x3,y3)      [6,7] ──── [4,5]
        #
        # Center X = average of left and right = (x1 + x2) / 2 = (content[0] + content[2]) / 2
        # Center Y = average of top and bottom = (y1 + y4) / 2 = (content[1] + content[5]) / 2
        #
        # Why content[1] and content[5] for Y (not content[1] and content[7])?
        # content[5] = y3 (bottom-right corner Y), which equals y4 for rectangular elements.
        # Using [1] and [5] is a reliable way to get top-Y and bottom-Y.
        
        content = box["model"]["content"]
        x = (content[0] + content[2]) / 2
        y = (content[1] + content[5]) / 2
        
        # ─── Step 5: Dispatch click events ───
        # A browser "click" is actually TWO events: mousedown then mouseup.
        # Some sites listen specifically for mousePressed or mouseReleased,
        # so we must send both.
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1
        })
        
        return True
    
    except Exception as e:
        print(f"Click failed for backendNodeId={backend_node_id}: {e}")
        return False
    
    finally:
        await cdp.detach()
```

### Understanding the content quad array

The `content` array from `DOM.getBoxModel` contains 8 numbers representing 4 (x,y) points:

```
Index:  0   1   2   3   4   5   6   7
Value: x1  y1  x2  y2  x3  y3  x4  y4

Visual layout (standard rectangular element):

    (x1=100, y1=200) ─────── (x2=300, y2=200)
          │                        │
          │       ELEMENT          │
          │                        │
    (x4=100, y4=250) ─────── (x3=300, y3=250)

Center = ( (100+300)/2, (200+250)/2 ) = (200, 225)
Code:    ( (content[0]+content[2])/2, (content[1]+content[5])/2 )
```

**Why `content[5]` instead of `content[3]` for the bottom Y?**

For a normal rectangle, `y1 == y2` (top edge) and `y3 == y4` (bottom edge). So:
- `content[1]` = y1 = top Y
- `content[3]` = y2 = also top Y (same as content[1] for rectangles!)
- `content[5]` = y3 = bottom Y ← **this is what we need**

Using `(content[1] + content[5]) / 2` correctly averages top and bottom.

### Common errors and how to handle them

| Error | Cause | Fix |
|---|---|---|
| `"Could not find node with given id"` | The element was removed from DOM (page navigated, AJAX update) | Re-fetch the AX tree and find the node again |
| `"Node is detached from document"` | Element existed but is no longer in the active document | Re-fetch AX tree |
| `"Could not compute box model"` | Element has zero size (hidden) or is `display:none` | Check if element is visible; may need to expand a parent accordion first |
| `"Node does not have a layout object"` | Similar to above — element exists in DOM but not rendered | Same as above |

### Robust click with retry

```python
async def click_with_retry(page, backend_node_id, max_retries=3):
    """Click with retry and exponential backoff."""
    for attempt in range(max_retries):
        success = await click_node_via_cdp(page, backend_node_id)
        if success:
            return True
        wait = 1 * (2 ** attempt)  # 1s, 2s, 4s
        print(f"  Retry {attempt + 1}/{max_retries} in {wait}s...")
        await asyncio.sleep(wait)
    return False
```

---

## Typing Text into Input Fields

For text input (search boxes, form fields), we combine CDP clicking with Playwright's
keyboard API:

```python
async def type_into_field(page, backend_node_id, text, delay=100):
    """
    Type text into an input field identified by its backendDOMNodeId.
    
    Process:
    1. Click the field via CDP to focus it (input fields need focus to receive keystrokes)
    2. Clear any existing content (triple-click to select all, then delete)
    3. Type the new text with human-like delay between keystrokes
    
    Args:
        page: Playwright page object
        backend_node_id: int, the backendDOMNodeId of the input field
        text: str, the text to type
        delay: int, milliseconds between each keystroke (100 = human-like speed)
    """
    # Step 1: Focus the input by clicking it
    clicked = await click_node_via_cdp(page, backend_node_id)
    if not clicked:
        print(f"Could not focus input field (backendNodeId={backend_node_id})")
        return False
    
    await asyncio.sleep(0.3)  # Wait for focus animation
    
    # Step 2: Clear existing content
    # Ctrl+A selects all text in the focused field, then Backspace removes it
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Backspace")
    await asyncio.sleep(0.2)
    
    # Step 3: Type the new text
    # delay=100 means 100ms between each character, simulating human typing speed.
    # This is important because:
    # - Some sites have debounced search that triggers on each keystroke
    # - Too-fast typing can be detected as bot behavior
    # - Some React inputs drop characters if typed too fast (state update race condition)
    await page.keyboard.type(text, delay=delay)
    
    return True
```

### Why use Playwright's `keyboard.type()` instead of CDP's `Input.dispatchKeyEvent`?

1. **Simplicity**: `page.keyboard.type("hello")` is one line. CDP requires dispatching
   separate `keyDown`, `char`, `keyUp` events for each character.

2. **Correctness**: Playwright handles IME composition (important for Vietnamese input
   like "Áo"), modifier keys, and browser-specific quirks. CDP's raw key events don't
   handle composition.

3. **Delay support**: The `delay` parameter creates natural typing cadence automatically.

### Finding searchbox / textbox nodes

```python
# Find the search input in the AX tree
search_inputs = [
    n for n in filtered_nodes
    if get_role(n) in ("searchbox", "textbox")
    and n.get("backendDOMNodeId")
]

# Usually the first searchbox is the main search
if search_inputs:
    search_node = search_inputs[0]
    await type_into_field(page, search_node["backendDOMNodeId"], "Áo Polo")
    
    # Press Enter to submit
    await page.keyboard.press("Enter")
    await asyncio.sleep(2)  # Wait for search results
```

---

## Common Pitfalls & Debugging

### Pitfall 1: Stale AX Tree data

**Symptom**: You find a checkbox in the AX tree and try to click it, but the click
does nothing or throws `"Could not find node"`.

**Cause**: The AX tree was retrieved before the page finished rendering, or an AJAX
update changed the DOM after retrieval.

**Fix**:
```python
# Always re-fetch the AX tree right before you need to interact
await asyncio.sleep(1)  # Let the page settle
nodes = await get_ax_tree(page)  # Fresh data
filtered = stage2_filter_ignored(nodes)
# NOW find and click your target
```

### Pitfall 2: backendDOMNodeId changes after DOM mutation

**Symptom**: A `backendDOMNodeId` that worked a moment ago now gives errors.

**Cause**: When JavaScript removes and re-creates a DOM element (common in React/Vue),
the new element gets a different `backendDOMNodeId`. The old ID is now invalid.

**Fix**: Re-fetch the AX tree after any page mutation (clicking filters, navigating,
scrolling that triggers lazy-load).

### Pitfall 3: CDP session errors after navigation

**Symptom**: `"Session closed"` or `"Target closed"` errors.

**Cause**: Reusing a CDP session after `page.goto()` or a JavaScript-triggered navigation.

**Fix**: Always create a new CDP session. The `get_ax_tree()` and `click_node_via_cdp()`
functions in this document already do this correctly with `try/finally`.

### Pitfall 4: Missing nodes in the AX tree

**Symptom**: An element is visible on the page but doesn't appear in the AX tree.

**Causes & fixes**:
- Element has `aria-hidden="true"` → It's intentionally hidden from accessibility.
  You may need to interact with it via Playwright selectors instead.
- Element is inside a Shadow DOM → CDP's `getFullAXTree` may not traverse shadow roots.
  Try `Accessibility.getFullAXTree` with `depth` parameter, or use Playwright's
  shadow-piercing selectors.
- Element is in an iframe → The AX tree only covers the main frame. Get the iframe's
  AX tree separately using `page.frame(...)`.

### Pitfall 5: Compact tree looks different than expected

**Symptom**: The compact text output is missing nodes you expected or has unexpected
nesting.

**Debug approach**:
```python
# 1. Check the raw dump: is the node even there?
import json
with open("ax_full_raw.json") as f:
    raw = json.load(f)
target = [n for n in raw if "Áo Polo" in get_name(n)]
print(f"Found {len(target)} nodes with 'Áo Polo' in raw tree")

# 2. Check if it was filtered as ignored
target_ignored = [n for n in target if n.get("ignored")]
print(f"Of those, {len(target_ignored)} are ignored")

# 3. Check its role — is it in a SKIP category?
for n in target:
    print(f"  role={get_role(n)}, name={get_name(n)}, ignored={n.get('ignored')}")
```

---

## Performance Characteristics

### Timing benchmarks (measured on real Aristino pages)

| Operation | Time | Notes |
|---|---|---|
| `get_ax_tree()` | 200–500ms | Depends on page complexity. Includes CDP session setup. |
| `stage2_filter_ignored()` | <10ms | Pure Python list comprehension on ~10K items |
| `stage3_compact_text()` | 20–50ms | Recursive tree walk + string building |
| `click_node_via_cdp()` | 500–800ms | Dominated by the 500ms scroll sleep |
| `build_tree_maps()` | <5ms | Single pass through node list |
| `find_group_for_node()` | <1ms per node | Usually finds match in 2-4 hops |

### Memory usage

| Data | Memory |
|---|---|
| Raw nodes (11K nodes) | ~15 MB (Python dicts with nested structures) |
| id_map (11K entries) | ~5 MB (references, not copies) |
| children_map | ~2 MB |
| Compact text string | ~50 KB |

**Tip**: If memory is tight, you can discard raw nodes after Stage 2 and discard
filtered nodes after Stage 3, keeping only the compact text and the maps.

---

## Quick Reference Cheat-Sheet

### Getting the AX tree

```python
nodes = await get_ax_tree(page)                   # Full raw tree (list of dicts)
filtered = [n for n in nodes if not n.get("ignored")]  # Remove ignored
```

### Parsing a node

```python
role = get_role(node)                              # "button", "link", "checkbox", ...
name = get_name(node)                              # "Áo Polo Ngắn Tay"
props = get_props(node)                            # {"url": "...", "checked": True, ...}
bid = node.get("backendDOMNodeId")                 # 1234 (for clicking)
```

### Finding specific nodes

```python
# All links
links = [n for n in filtered if get_role(n) == "link"]

# All checked checkboxes
checked = [n for n in filtered if get_role(n) == "checkbox" and get_props(n).get("checked")]

# Node with specific name
target = next((n for n in filtered if get_name(n) == "Áo Blazer"), None)

# All headings level 3
h3s = [n for n in filtered if get_role(n) == "heading" and get_props(n).get("level") == 3]
```

### Interacting

```python
await click_node_via_cdp(page, backend_node_id)               # Click
await type_into_field(page, backend_node_id, "search text")    # Type
await page.keyboard.press("Enter")                            # Submit
```

### Full workflow example

```python
async def click_filter_checkbox(page, checkbox_name):
    """Find and click a filter checkbox by name."""
    # 1. Get fresh AX tree
    nodes = await get_ax_tree(page)
    filtered = [n for n in nodes if not n.get("ignored")]
    
    # 2. Find the checkbox
    target = next(
        (n for n in filtered 
         if get_role(n) == "checkbox" 
         and get_name(n) == checkbox_name
         and n.get("backendDOMNodeId")),
        None
    )
    
    if not target:
        print(f"Checkbox '{checkbox_name}' not found in AX tree")
        return False
    
    # 3. Click it
    bid = target["backendDOMNodeId"]
    success = await click_node_via_cdp(page, bid)
    
    if success:
        print(f"Clicked checkbox: {checkbox_name} (id={bid})")
        await asyncio.sleep(2)  # Wait for filter to apply
    
    return success
```

---

## Summary: The AX Tree Mental Model

```
┌─────────────────────────────────────────────────────────┐
│                    Web Page (DOM)                        │
│  Thousands of elements: divs, spans, classes, styles    │
│  Size: 5-10 MB of HTML                                  │
│  Fragile: CSS classes change on every deploy            │
└────────────────────┬────────────────────────────────────┘
                     │ Chrome Accessibility Engine
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Raw AX Tree (JSON)                         │
│  Semantic nodes only: roles, names, states              │
│  Size: 1-2 MB JSON                                      │
│  Stable: roles and names rarely change                  │
└────────────────────┬────────────────────────────────────┘
                     │ Stage 2: Filter ignored
                     ▼
┌─────────────────────────────────────────────────────────┐
│            Filtered AX Tree (JSON)                      │
│  Only meaningful nodes (no decorative wrappers)         │
│  Size: ~1.5 MB JSON                                     │
└────────────────────┬────────────────────────────────────┘
                     │ Stage 3: Compact
                     ▼
┌─────────────────────────────────────────────────────────┐
│             Compact AX Tree (Text)                      │
│  Indented text: role | "name" | id=XXX | states         │
│  Size: 30-80 KB text                                    │
│  LLM-ready: fits in context window                      │
│  Interaction-ready: ids map to clickable elements       │
└─────────────────────────────────────────────────────────┘
```

Every function in this document is battle-tested on Vietnamese e-commerce sites
(Aristino, and similar). The patterns handle UTF-8 names (Vietnamese characters like
ÁÀẢ, Ô, Ư), AJAX-heavy pages, and complex filter panels with nested expandable sections.

**When in doubt**: re-fetch the AX tree. It only takes 200-500ms and guarantees you're
working with current data.
