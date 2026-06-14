# Chrome DevTools Protocol (CDP) Setup

> **Purpose of this document:** Teach an AI agent (or human developer) with **zero prior context** exactly how to launch Chrome in a scraper-friendly mode, connect to it from Python via Playwright, and troubleshoot every common failure. Every flag, every line of code, and every design decision is explained with *why* — not just *what*.

---

## Table of Contents

1. [What is CDP?](#what-is-cdp)
2. [CDP vs WebDriver (Selenium) — Why CDP Wins for This Project](#cdp-vs-webdriver-selenium--why-cdp-wins-for-this-project)
3. [The `chrome.bat` Script — Explained Line by Line](#the-chromebat-script--explained-line-by-line)
4. [Every Chrome Flag Explained in Depth](#every-chrome-flag-explained-in-depth)
5. [Connecting from Python (Playwright)](#connecting-from-python-playwright)
6. [The CDP Session Object — What It Is and When to Recreate It](#the-cdp-session-object--what-it-is-and-when-to-recreate-it)
7. [Common Errors and Fixes](#common-errors-and-fixes)
8. [Why Not Launch Chrome via Playwright Directly?](#why-not-launch-chrome-via-playwright-directly)
9. [Advanced Tips](#advanced-tips)

---

## What is CDP?

**Chrome DevTools Protocol (CDP)** is the low-level protocol that Chrome's built-in DevTools (the F12 panel) uses to communicate with the browser engine. It is a WebSocket-based JSON-RPC protocol that exposes nearly every internal subsystem of the browser:

- **Page navigation & lifecycle** — load pages, intercept network requests, capture screenshots
- **DOM inspection & manipulation** — query elements, modify HTML, inject JavaScript
- **Accessibility Tree** — read the full AX (accessibility) tree that assistive technologies see
- **Network interception** — monitor/modify HTTP requests and responses in flight
- **JavaScript execution** — run arbitrary JS in the page context
- **Profiling & performance** — CPU profiles, heap snapshots, tracing

### How it works at the network level

```
┌──────────────┐   WebSocket (ws://localhost:9222)   ┌──────────────────┐
│  Python      │ ◄──────────────────────────────────► │  Chrome Browser  │
│  (Playwright)│   JSON-RPC messages over WS          │  (with CDP open) │
└──────────────┘                                      └──────────────────┘
```

When Chrome is started with `--remote-debugging-port=9222`, it opens a WebSocket server on that port. Any client that speaks the CDP JSON-RPC protocol can connect and control Chrome. Playwright is one such client; `puppeteer` is another; you can even use raw WebSocket calls via `websockets` in Python.

### Key concept: CDP gives you the REAL browser

Unlike HTTP-based scrapers (`requests`, `httpx`, `aiohttp`), CDP controls a **real Chrome instance** that:
- Executes JavaScript (React, Vue, Angular apps render fully)
- Stores cookies and localStorage (login sessions persist)
- Has a real DOM and Accessibility Tree
- Respects CORS, CSP, and other browser security policies
- Looks like a genuine user to anti-bot systems

---

## CDP vs WebDriver (Selenium) — Why CDP Wins for This Project

| Aspect | Selenium (WebDriver) | Playwright via CDP |
|---|---|---|
| **Protocol** | WebDriver (W3C standard), HTTP-based | CDP (Chrome-native), WebSocket-based |
| **Browser control** | High-level commands only | Direct access to browser internals |
| **Accessibility Tree** | Not accessible | Full AX tree via `cdp_session.send("Accessibility.getFullAXTree")` |
| **Network interception** | Limited/hacky | First-class support via `page.route()` or CDP `Network` domain |
| **Speed** | Slower (HTTP round-trips per command) | Faster (persistent WebSocket, batched commands) |
| **Profile persistence** | Possible but awkward | Native via `--user-data-dir` |
| **Detection by anti-bot** | Easily detected (`navigator.webdriver = true`) | Harder to detect with pre-launched Chrome |
| **Attach to existing browser** | Difficult | Native via `connect_over_cdp()` |

**Bottom line:** CDP gives us the Accessibility Tree (critical for this scraper's AI-driven element identification) and lets us attach to a pre-launched Chrome where a human can log in manually.

---

## The `chrome.bat` Script — Explained Line by Line

This is the exact script used to launch Chrome in CDP-ready mode. Save it as `chrome.bat` in the **root directory of your project workspace** so that all scraper modules can share the same instance.

```batch
@echo off
setlocal enabledelayedexpansion

:: Di chuyển vào thư mục chứa file bat (thư mục gốc dự án)
cd /d "%~dp0"

:: Đường dẫn mặc định tới Chrome trên Windows
set CHROME_BIN="C:\Program Files\Google\Chrome\Application\chrome.exe"
set PORT=9222

:: Định nghĩa thư mục profile riêng biệt tại gốc dự án
set PROFILE_DIR="%~dp0chrome_profile"

echo =================================================
echo   KHOI CHAY CHROME CHO DU AN CRAWLER (PORT %PORT%)
echo   Profile: %PROFILE_DIR%
echo =================================================

:: Tạo thư mục profile nếu chưa tồn tại
if not exist %PROFILE_DIR% mkdir %PROFILE_DIR%

:: Flags khởi chạy tối ưu cho kết nối CDP và cào dữ liệu
set FLAGS=--remote-debugging-port=%PORT% --user-data-dir=%PROFILE_DIR% --force-renderer-accessibility --disable-background-timer-throttling --no-first-run --no-default-browser-check --win-http-proxy-resolver

:: Khởi chạy Chrome
start "" %CHROME_BIN% %FLAGS%

echo ✅ Trình duyệt Chrome đã sẵn sàng điều khiển!
echo 💡 Profile tách biệt hoàn toàn tại: %PROFILE_DIR%

timeout /t 3 >nul
exit
```

### Line-by-line breakdown

#### `@echo off`
Suppresses the printing of each command to the console as it executes. Without this, every line of the `.bat` file would be echoed to the terminal, creating noisy output. This is a standard practice for all production batch scripts.

#### `setlocal enabledelayedexpansion`
Enables **delayed variable expansion** in the batch script. Normally, batch variables (`%VAR%`) are expanded when a line is *parsed*. With delayed expansion enabled, you can use `!VAR!` to expand variables at *execution time*. This matters when variables are set inside loops or `if` blocks. While this particular script doesn't use `!VAR!` syntax, enabling it is a defensive best practice that prevents subtle bugs if the script is extended later with conditional logic.

#### `cd /d "%~dp0"`
Changes the working directory to **the directory where the `.bat` file is located**.

- `%~dp0` — expands to the **d**rive letter and **p**ath of the batch file (`%0`). The `~` strips surrounding quotes.
- `/d` — allows changing both the drive letter AND directory in one command (e.g., from `C:\` to `D:\FPT\...`).

**Why this matters:** This ensures that `%~dp0chrome_profile` (the profile directory) is always relative to the script location, regardless of where the user opens the terminal. If the user runs `D:\scripts\chrome.bat` from `C:\Users\PC>`, without `cd /d`, the profile directory would be created in `C:\Users\PC\` instead of `D:\scripts\`.

#### `set CHROME_BIN="C:\Program Files\Google\Chrome\Application\chrome.exe"`
Stores the path to the Chrome executable. Adjust this if Chrome is installed elsewhere (e.g., `C:\Program Files (x86)\...` for 32-bit, or a custom install location).

**How to find your Chrome path:**
```batch
where chrome
:: or check the shortcut properties of Chrome in Start Menu
```

#### `set PORT=9222`
The TCP port on which Chrome will listen for CDP connections. Port `9222` is the conventional default used in all CDP documentation, Puppeteer defaults, and Playwright examples.

**If port 9222 is already in use** (e.g., another Chrome instance), change this to any free port (e.g., `9223`, `9224`). You'll need to update your Python connection string to match.

#### `set PROFILE_DIR="%~dp0chrome_profile"`
Creates a profile directory path **next to the `.bat` file**. Example: if the `.bat` is at `D:\scraper\chrome.bat`, the profile will be at `D:\scraper\chrome_profile\`.

**Why a custom profile?** See the detailed flag explanation below for `--user-data-dir`.

#### `if not exist %PROFILE_DIR% mkdir %PROFILE_DIR%`
Creates the profile directory if it doesn't already exist. On first run, Chrome needs this directory to exist (or it will create it, but explicitly creating it avoids potential permission issues).

#### `set FLAGS=...`
Stores all Chrome command-line flags in a single variable for readability. Each flag is explained in detail in the next section.

#### `start "" %CHROME_BIN% %FLAGS%`
Launches Chrome as a **separate process** and returns control to the batch script immediately.

- `start` — Windows command to launch a program in a new window/process.
- `""` — The first quoted argument to `start` is the **window title**. An empty string `""` means "no title". **This is required.** Without it, `start` would interpret the Chrome path as the window title and fail to launch.
- `%CHROME_BIN% %FLAGS%` — The actual executable and its arguments.

**Why `start` instead of just running Chrome directly?** Because without `start`, the batch script would **block** until Chrome is closed. With `start`, Chrome runs independently and the script continues to the next line.

#### `timeout /t 3 >nul`
Waits 3 seconds before exiting the batch script. This gives Chrome time to initialize and open the CDP WebSocket server before the script closes the terminal window.

- `/t 3` — wait 3 seconds
- `>nul` — suppress the "Waiting for X seconds, press a key to continue..." message

#### `exit`
Closes the command prompt window. At this point, Chrome is running independently in its own process.

---

## Every Chrome Flag Explained in Depth

### `--remote-debugging-port=9222`

**What it does:** Opens a WebSocket server on TCP port 9222 that speaks the Chrome DevTools Protocol.

**Why it's essential:** This is the single most important flag. Without it, Chrome is just a regular browser with no programmatic access. With it, any CDP client (Playwright, Puppeteer, raw WebSocket) can connect and control Chrome.

**What happens at the network level:**
1. Chrome starts listening on `ws://localhost:9222`
2. A discovery endpoint appears at `http://localhost:9222/json/version` — returns browser WebSocket URL
3. Each tab gets its own WebSocket endpoint at `http://localhost:9222/json/list`

**You can verify Chrome is listening:**
```powershell
# Check if port 9222 is open
netstat -ano | findstr :9222

# Or use curl/Invoke-WebRequest to query the discovery endpoint
Invoke-WebRequest -Uri "http://localhost:9222/json/version" | Select-Object -ExpandProperty Content
```

**Expected response from `/json/version`:**
```json
{
  "Browser": "Chrome/126.0.6478.127",
  "Protocol-Version": "1.3",
  "User-Agent": "Mozilla/5.0 ...",
  "V8-Version": "12.6.228.28",
  "WebKit-Version": "537.36",
  "webSocketDebuggerUrl": "ws://localhost:9222/dev/page/..."
}
```

**Security note:** CDP has **no authentication**. Anyone on your machine (or network, if you bind to `0.0.0.0`) can connect and fully control your browser. Only use on `localhost` and never expose port 9222 to external networks.

---

### `--user-data-dir=<path>`

**What it does:** Tells Chrome to use a **specific directory** as its user profile (bookmarks, cookies, localStorage, cached data, extensions, login sessions — everything).

**Why it's critical for scraping:**

1. **Profile isolation:** Your personal Chrome profile (with your Google account, saved passwords, browsing history) is completely separate from the scraper's profile. No cross-contamination.

2. **Prevents "used by another profile" errors:** Chrome normally locks its profile directory. If your personal Chrome is open and you try to launch another Chrome without `--user-data-dir`, Chrome will either:
   - Show an error: "Chrome is being controlled by automated test software" 
   - Or refuse to launch with: "Your profile could not be opened correctly"
   
   A separate `--user-data-dir` avoids this entirely.

3. **Cookie/session persistence across runs:** When you log into a website (e.g., Tiki, Shopee, a CRM) manually in this Chrome instance, the login session is saved to this profile directory. The next time you run `chrome.bat` and connect your scraper, **the session is still active** — no need to log in again.

4. **Reproducible state:** You can delete the entire `chrome_profile` directory to get a "fresh" browser. Or you can copy/backup the directory to preserve a known-good state with specific logins.

**What the directory contains:**
```
chrome_profile/
├── Default/
│   ├── Cookies              ← SQLite DB of all cookies
│   ├── Local Storage/       ← localStorage data per origin
│   ├── Session Storage/     ← sessionStorage data
│   ├── Login Data           ← saved passwords (encrypted)
│   ├── Preferences          ← browser settings JSON
│   ├── History              ← browsing history SQLite DB
│   └── Cache/               ← HTTP cache
├── Local State              ← encryption keys, profile metadata
└── ...
```

---

### `--force-renderer-accessibility`

**What it does:** Forces Chrome to **always build and maintain the Accessibility Tree (AX Tree)** for every page, even when no assistive technology (screen reader) is connected.

**Why it's CRITICAL for this scraper:**

This scraper uses the Accessibility Tree as a primary mechanism for understanding page structure. The AX Tree provides a semantic view of the page:

```
# Example: What the DOM sees vs what the AX Tree sees

DOM:
<div class="sc-1a2b3c xyz-module__price--abc123" data-v-abc>
  <span class="sc-4d5e6f">₫</span>
  <span class="sc-7g8h9i">1.290.000</span>
</div>

AX Tree:
role: text
name: "₫1.290.000"
```

The AX Tree cuts through obfuscated class names and deeply nested `<div>` soup to give you the **semantic meaning** of each element. But Chrome **does not build the AX Tree by default** — it only builds it when a screen reader (like NVDA or JAWS) or another assistive technology requests it.

**Without `--force-renderer-accessibility`:**
```python
cdp = await page.context.new_cdp_session(page)
result = await cdp.send("Accessibility.getFullAXTree")
# result["nodes"] might be EMPTY or contain only a skeleton tree
```

**With `--force-renderer-accessibility`:**
```python
cdp = await page.context.new_cdp_session(page)
result = await cdp.send("Accessibility.getFullAXTree")
# result["nodes"] contains the COMPLETE tree with all roles, names, values
```

**This flag is non-negotiable.** If you forget it, the entire AX-tree-based scraping strategy breaks silently — you'll get empty or partial data with no error message.

---

### `--disable-background-timer-throttling`

**What it does:** Prevents Chrome from throttling (slowing down) `setTimeout`, `setInterval`, and `requestAnimationFrame` in background tabs.

**Why it matters for scraping:**

By default, Chrome aggressively throttles JavaScript timers in background tabs to save CPU and battery:
- `setTimeout` minimum delay increases to 1000ms (instead of 4ms)
- `setInterval` is limited to once per second
- `requestAnimationFrame` stops entirely

This becomes a problem when:
1. Your scraper opens multiple tabs and processes them in sequence
2. A page relies on JavaScript timers to finish rendering (lazy-loaded content, infinite scroll triggers, SPA route transitions)
3. You navigate to a new page but the previous tab's unfinished JS timers are relevant

With this flag, all tabs behave as if they are in the foreground, and timers run at full speed.

**Practical example:** A product listing page uses `setInterval` to progressively load images. Without this flag, switching to another tab causes the image loading to slow to 1 image/second instead of the normal rate. Your scraper might then capture placeholder images instead of real product photos.

---

### `--no-first-run`

**What it does:** Skips the "Welcome to Chrome" first-run experience that appears when Chrome launches with a brand-new profile.

**Why it matters:** On the first launch of a new `--user-data-dir` profile, Chrome normally shows:
- A "Welcome to Chrome" tab
- An import dialog (import bookmarks from another browser)
- A "Set up sync" prompt

These dialogs interfere with scraping by:
- Opening unexpected tabs (your scraper expects to find one tab, finds two)
- Showing modal dialogs that block page interaction
- Redirecting the first tab to `chrome://welcome` instead of `about:blank`

With `--no-first-run`, Chrome starts with a clean `about:blank` tab, ready for your scraper.

---

### `--no-default-browser-check`

**What it does:** Suppresses the "Chrome is not your default browser. Set it as default?" notification bar.

**Why it matters:** This notification bar appears at the top of the browser window and can:
- Shift the page content down (breaking coordinate-based click calculations)
- Intercept keyboard focus
- Appear unpredictably, causing intermittent test/scraper failures

Disabling it ensures consistent page layout.

---

### `--win-http-proxy-resolver`

**What it does:** Tells Chrome to use the Windows system proxy settings (from Internet Options / Settings → Network & Internet → Proxy) instead of Chrome's own proxy resolution logic.

**Why it matters:**
- If you're behind a corporate proxy, this flag ensures Chrome uses the same proxy settings as the rest of your system
- Avoids "ERR_PROXY_CONNECTION_FAILED" or "ERR_TUNNEL_CONNECTION_FAILED" errors
- If you're NOT behind a proxy, this flag is harmless — it just means "use whatever Windows says," and Windows says "direct connection"
- Particularly important in Vietnamese corporate/university networks (FPT, VNPT environments) where proxy auto-config (PAC) scripts are common

---

## Connecting from Python (Playwright)

### The Connection Code

```python
from playwright.async_api import async_playwright

async def connect_to_chrome():
    """
    Connect to an already-running Chrome instance via CDP.
    Chrome must be running with --remote-debugging-port=9222.
    """
    async with async_playwright() as p:
        # Step 1: Connect to Chrome via CDP
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        
        # Step 2: Get existing browser context (preserves cookies/session)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        
        # Step 3: Get existing page/tab (reuse what's already open)
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Step 4: Set viewport to ensure desktop layout
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Now ready to scrape
        await page.goto("https://example.com")
        print(await page.title())
```

### Step-by-step explanation

#### Step 1: `connect_over_cdp("http://localhost:9222")`

This does **NOT** launch a new Chrome process. It connects to an **already-running** Chrome instance via the CDP WebSocket.

**What happens under the hood:**
1. Playwright sends an HTTP GET to `http://localhost:9222/json/version`
2. Chrome responds with the WebSocket URL: `ws://localhost:9222/devtools/browser/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
3. Playwright opens a WebSocket connection to that URL
4. All subsequent commands (navigation, clicks, JS execution) flow over this WebSocket

**If Chrome is not running**, you'll get:
```
playwright._impl._errors.Error: connect ECONNREFUSED 127.0.0.1:9222
```
**Fix:** Run `chrome.bat` first, then connect.

#### Step 2: `browser.contexts[0]` — Reusing Existing Context

A **BrowserContext** in Playwright is an isolated browsing session — think of it as an incognito window. It contains:
- Cookies
- localStorage
- sessionStorage
- Cache
- Authentication state

When you connect to a pre-launched Chrome via CDP, Chrome already has at least one context (the default browsing context with all the cookies from `--user-data-dir`).

```python
# Reuse existing context → preserves login sessions, cookies
context = browser.contexts[0] if browser.contexts else await browser.new_context()
```

**Why `browser.contexts[0]`?** Because we want to reuse the existing session. If you logged into a website manually in Chrome before starting the scraper, `browser.contexts[0]` gives you access to that authenticated session.

**When `browser.contexts` is empty:** This can happen if Chrome has no tabs (unlikely but possible after all tabs are closed). In that case, `await browser.new_context()` creates a fresh context.

#### Step 3: `context.pages[0]` — Reusing Existing Tab

```python
page = context.pages[0] if context.pages else await context.new_page()
```

When Chrome is already open, it typically has at least one tab (the `about:blank` or whatever page the user navigated to). `context.pages[0]` gives you a handle to that tab.

**Why reuse instead of creating new?** 
- Avoids tab proliferation (each `await context.new_page()` opens a new tab)
- If the user has already navigated to a target page manually, you can start scraping immediately
- The existing tab already has the correct context (cookies, localStorage)

#### Step 4: `page.set_viewport_size({"width": 1920, "height": 1080})`

```python
await page.set_viewport_size({"width": 1920, "height": 1080})
```

**Why 1920×1080?**
- Most websites serve their **desktop layout** at this resolution
- Mobile/responsive layouts (triggered at smaller widths) often hide elements, collapse menus, or rearrange content — making scraping harder
- 1920×1080 is the most common desktop resolution worldwide
- Screenshots taken at this resolution are human-readable and useful for debugging

**Without setting viewport:** The viewport size depends on the Chrome window size, which might be small (e.g., 800×600) if Chrome opened in a small window. This could trigger mobile layouts.

---

## The CDP Session Object — What It Is and When to Recreate It

### What is a CDP Session?

A `CDPSession` is a direct, low-level communication channel to a specific page's Chrome DevTools Protocol endpoint. While Playwright provides high-level methods (`.click()`, `.fill()`, `.goto()`), the CDP session lets you send raw CDP commands.

```python
# Create a CDP session for a specific page
cdp_session = await page.context.new_cdp_session(page)

# Send a raw CDP command
ax_tree = await cdp_session.send("Accessibility.getFullAXTree")
```

### When to create a NEW CDP session

**Critical rule:** After navigating to a new page (especially cross-origin navigation), the old CDP session may become **stale**. The page's internal target ID changes, and the old session points to a target that no longer exists.

```python
# ❌ WRONG — stale session after navigation
cdp_session = await page.context.new_cdp_session(page)
await page.goto("https://example.com/page1")
tree1 = await cdp_session.send("Accessibility.getFullAXTree")  # Works

await page.goto("https://example.com/page2")
tree2 = await cdp_session.send("Accessibility.getFullAXTree")  # May FAIL or return stale data!

# ✅ CORRECT — new session after navigation
cdp_session = await page.context.new_cdp_session(page)
await page.goto("https://example.com/page1")
tree1 = await cdp_session.send("Accessibility.getFullAXTree")  # Works

await page.goto("https://example.com/page2")
cdp_session = await page.context.new_cdp_session(page)  # NEW session for new page
tree2 = await cdp_session.send("Accessibility.getFullAXTree")  # Works
```

### Practical pattern for safe CDP usage

```python
async def get_ax_tree(page):
    """Always create a fresh CDP session before reading AX tree."""
    cdp = await page.context.new_cdp_session(page)
    try:
        result = await cdp.send("Accessibility.getFullAXTree")
        return result.get("nodes", [])
    finally:
        await cdp.detach()
```

The `detach()` in the `finally` block is good hygiene — it closes the WebSocket channel for that session and frees resources.

---

## Common Errors and Fixes

### Error: `connect ECONNREFUSED 127.0.0.1:9222`

**Cause:** Chrome is not running, or it's running without `--remote-debugging-port=9222`.

**Fix:**
1. Run `chrome.bat` first
2. Verify Chrome is listening:
   ```powershell
   netstat -ano | findstr :9222
   ```
3. If no output, Chrome didn't start with the CDP flag. Close all Chrome instances and re-run `chrome.bat`.

**Common mistake:** Having a personal Chrome instance already running. Chrome might reuse the existing process (which doesn't have CDP enabled) instead of starting a new one. **Solution:** Close ALL Chrome windows before running `chrome.bat`, OR ensure the `--user-data-dir` is different from your personal profile.

---

### Error: `browser.contexts` is empty / `No context available`

**Cause:** Chrome is running with CDP, but somehow has no browsing contexts.

**Fix:**
```python
if browser.contexts:
    context = browser.contexts[0]
else:
    context = await browser.new_context()
```

This is already handled in our connection code. If it keeps happening, check if Chrome launched correctly (it should show at least one window/tab).

---

### Stale CDP Session — AX Tree Returns Empty or Old Data

**Symptoms:**
- `Accessibility.getFullAXTree` returns nodes from a previous page
- CDP commands throw `Target closed` or `Session closed` errors
- AX tree is suspiciously small (only root node)

**Cause:** The CDP session was created before a page navigation, and the page's internal target changed.

**Fix:** Always create a new CDP session after navigation:
```python
await page.goto(url, wait_until="networkidle")
await page.wait_for_timeout(1000)  # Extra safety margin for JS rendering
cdp_session = await page.context.new_cdp_session(page)  # FRESH session
tree = await cdp_session.send("Accessibility.getFullAXTree")
```

---

### Popups / Overlays Blocking Clicks

**Symptoms:**
- `page.click(selector)` fails with "Element is not visible" or "Element is covered by another element"
- Cookie consent banners, newsletter popups, or chat widgets cover target elements

**Fix — Remove popup overlays via JavaScript before clicking:**
```python
# Generic popup removal — run before interacting with page
await page.evaluate("""
    // Remove common popup/overlay patterns
    const selectors = [
        '[class*="popup"]', '[class*="modal"]', '[class*="overlay"]',
        '[class*="cookie"]', '[class*="consent"]', '[class*="banner"]',
        '[id*="popup"]', '[id*="modal"]', '[id*="overlay"]',
    ];
    for (const sel of selectors) {
        document.querySelectorAll(sel).forEach(el => el.remove());
    }
    // Remove fixed-position overlays
    document.querySelectorAll('*').forEach(el => {
        const style = getComputedStyle(el);
        if (style.position === 'fixed' && style.zIndex > 999) {
            el.remove();
        }
    });
""")
```

**More surgical approach — target specific known popups:**
```python
# Example: Remove Tiki's cookie consent
await page.evaluate("""
    const cookieBanner = document.querySelector('.cookie-consent-banner');
    if (cookieBanner) cookieBanner.remove();
""")
```

---

### Error: `Page crashed` or `Target crashed`

**Cause:** Chrome ran out of memory, usually when:
- Too many tabs are open simultaneously
- Pages are extremely heavy (large SPAs, video-heavy pages)
- The scraper runs for hours without closing/restarting Chrome

**Fix:**
1. Close tabs you're done with: `await page.close()`
2. Restart Chrome periodically (re-run `chrome.bat` every few hundred pages)
3. Add a memory check:
   ```python
   import psutil
   
   def check_chrome_memory():
       """Warn if Chrome is using too much memory."""
       for proc in psutil.process_iter(['name', 'memory_info']):
           if proc.info['name'] == 'chrome.exe':
               mem_mb = proc.info['memory_info'].rss / (1024 * 1024)
               if mem_mb > 2000:  # 2GB threshold
                   print(f"⚠️ Chrome using {mem_mb:.0f} MB — consider restarting")
   ```

---

### Error: `Timeout 30000ms exceeded` on `page.goto()`

**Cause:** Page takes too long to load (slow network, heavy page, server not responding).

**Fix — Use appropriate wait strategies:**
```python
# Option 1: Wait for DOM content loaded (faster, doesn't wait for images/XHR)
await page.goto(url, wait_until="domcontentloaded", timeout=60000)

# Option 2: Wait for network to be idle (slower, but page is fully loaded)
await page.goto(url, wait_until="networkidle", timeout=60000)

# Option 3: Just commit (fastest, page may not be rendered yet)
await page.goto(url, wait_until="commit", timeout=60000)
```

**Recommendation for scraping:** Use `domcontentloaded` + explicit wait for the specific element you need:
```python
await page.goto(url, wait_until="domcontentloaded", timeout=60000)
await page.wait_for_selector(".product-price", timeout=15000)
```

---

### Chrome Opens but Connects to Wrong/Personal Profile

**Cause:** Another Chrome instance is already running with the default profile, and Chrome reuses that process.

**Fix:** 
1. Close ALL Chrome windows (check Task Manager for `chrome.exe` processes)
2. Or kill all Chrome processes before launching:
   ```batch
   taskkill /F /IM chrome.exe /T 2>nul
   timeout /t 2 >nul
   start "" %CHROME_BIN% %FLAGS%
   ```

**Nuclear option — add to `chrome.bat` before the `start` command:**
```batch
:: Kill any existing Chrome processes
taskkill /F /IM chrome.exe /T 2>nul
timeout /t 2 >nul
```

⚠️ **Warning:** This will close your personal Chrome too! Only use if you're okay with that.

---

## Why Not Launch Chrome via Playwright Directly?

Playwright can launch its own Chrome/Chromium instance:

```python
# This is what you'd do WITHOUT pre-launched Chrome
browser = await p.chromium.launch(headless=False)
context = await browser.new_context()
page = await context.new_page()
```

**Here's why we DON'T do this for our scraper:**

### 1. Limited Profile Persistence

Playwright's launched browser uses a **temporary profile** by default. When the script ends, cookies, localStorage, and login sessions are **destroyed**. You'd need to log in every time.

You *can* specify `user_data_dir` in Playwright's launch options, but the behavior is inconsistent — Playwright sometimes modifies the profile in ways that break things on the next launch.

### 2. No Manual Login Capability

With a pre-launched Chrome:
1. Run `chrome.bat`
2. Manually navigate to the target site and log in (enter credentials, solve CAPTCHAs, do 2FA)
3. Login session is saved to `chrome_profile/`
4. Run your scraper script — it connects to the same Chrome and **the session is already active**

With Playwright-launched Chrome, there's no opportunity for step 2. You'd need to automate the entire login flow, which is:
- Fragile (login pages change frequently)
- Difficult with CAPTCHAs (need third-party solving services)
- Impossible with hardware 2FA tokens

### 3. Real-Time Debugging

With a pre-launched Chrome, you can:
- See exactly what the scraper sees in real-time (the Chrome window is visible)
- Open DevTools (F12) to inspect elements while the scraper runs
- Manually intervene if something goes wrong (close a popup, complete a CAPTCHA)
- Compare what Chrome shows vs. what your scraper extracts

With Playwright's `launch(headless=False)`, you get a visible window too — but it's Playwright's bundled Chromium, not the system Chrome. Differences:
- Playwright's Chromium may have different behavior than the system Chrome
- Extensions don't work the same way
- Some sites detect Playwright's Chromium and serve different content

### 4. Anti-Bot Detection

Pre-launched system Chrome with `--user-data-dir`:
- Uses the real system Chrome binary (not Chromium)
- Has a real user profile with browsing history (looks like a real user)
- `navigator.webdriver` is NOT set to `true` (unlike Playwright-launched browsers)
- User-Agent matches the real Chrome version

Playwright-launched Chrome:
- Sets `navigator.webdriver = true` (detectable)
- Has an empty profile (suspicious — who has zero browsing history?)
- Uses Playwright's specific User-Agent string
- Various fingerprinting differences that anti-bot systems detect

### 5. Summary Table

| Feature | Pre-launched Chrome + CDP | Playwright `launch()` |
|---|---|---|
| Login persistence | ✅ Survives script restarts | ❌ Lost unless manual save/restore |
| Manual login possible | ✅ Before connecting script | ❌ Must automate everything |
| CAPTCHA handling | ✅ Solve manually in browser | ❌ Need automated solver |
| Real-time observation | ✅ Same Chrome window | ⚠️ Separate Chromium window |
| Anti-bot stealth | ✅ Real Chrome, real profile | ❌ `webdriver=true`, empty profile |
| Simplicity | ✅ One .bat file | ⚠️ Complex launch options |
| Cleanup required | ❌ Must close Chrome manually | ✅ Auto-closes on script exit |

---

## Advanced Tips

### Tip 1: Check if Chrome is Already Running Before Launching

Add this to the top of `chrome.bat`:
```batch
:: Check if Chrome is already listening on the CDP port
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo Chrome is already running on port %PORT%. Skipping launch.
    exit
)
```

### Tip 2: Use a Helper Function to Ensure Connection

```python
import asyncio
from playwright.async_api import async_playwright

async def ensure_chrome_connection(port=9222, max_retries=5):
    """
    Connect to Chrome via CDP with retry logic.
    Returns (browser, context, page) tuple.
    """
    async with async_playwright() as p:
        for attempt in range(max_retries):
            try:
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
                await page.set_viewport_size({"width": 1920, "height": 1080})
                print(f"✅ Connected to Chrome on port {port}")
                return browser, context, page
            except Exception as e:
                print(f"⚠️ Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
        raise ConnectionError(f"Failed to connect to Chrome on port {port} after {max_retries} attempts")
```

### Tip 3: Graceful Disconnection

When your scraper finishes, **disconnect** cleanly — but do NOT close the browser (since it's pre-launched and you want the session to persist):

```python
# ✅ CORRECT — disconnect without closing Chrome
await browser.close()  # This disconnects Playwright, but does NOT close Chrome

# ❌ WRONG — this would close Chrome entirely
# Don't use browser.close() if you want Chrome to stay open
# Actually, Playwright's close() on a CDP-connected browser only disconnects,
# it does NOT terminate the Chrome process. This is safe.
```

### Tip 4: Multiple Pages / Tabs

If your scraper needs to open multiple product pages:

```python
# Open new tab in existing context (shares cookies)
new_page = await context.new_page()
await new_page.goto("https://example.com/product/123")

# Process the page...

# Close the tab when done (frees memory)
await new_page.close()
```

### Tip 5: Verify the AX Tree is Working

Run this quick diagnostic after connecting:

```python
async def verify_ax_tree(page):
    """Verify that the Accessibility Tree is available and populated."""
    await page.goto("https://example.com")
    cdp = await page.context.new_cdp_session(page)
    result = await cdp.send("Accessibility.getFullAXTree")
    nodes = result.get("nodes", [])
    
    if len(nodes) == 0:
        print("❌ AX Tree is EMPTY. Did you launch Chrome with --force-renderer-accessibility?")
        return False
    elif len(nodes) < 10:
        print(f"⚠️ AX Tree has only {len(nodes)} nodes. May be incomplete.")
        return False
    else:
        print(f"✅ AX Tree has {len(nodes)} nodes. Working correctly.")
        return True
```

### Tip 6: Environment-Specific Chrome Paths

Different machines may have Chrome installed in different locations:

```python
import os
import platform

def find_chrome_path():
    """Find Chrome executable path on Windows."""
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Chrome not found. Install Chrome or update the path.")
```

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────┐
│                   CDP Scraper Setup                      │
│                                                          │
│  1. Run chrome.bat           → Chrome starts with CDP    │
│  2. (Optional) Log in        → Session saved to profile  │
│  3. Run Python scraper       → Connects via CDP          │
│  4. Scraper reads AX Tree    → Understands page layout   │
│  5. Scraper extracts data    → Saves to JSON/CSV         │
│  6. Script ends              → Chrome stays running       │
│                                                          │
│  Key URLs:                                               │
│  • CDP endpoint:  http://localhost:9222                   │
│  • Version info:  http://localhost:9222/json/version      │
│  • Tab list:      http://localhost:9222/json/list         │
│                                                          │
│  Key flags:                                              │
│  --remote-debugging-port=9222                            │
│  --user-data-dir=<profile_path>                          │
│  --force-renderer-accessibility   ← DON'T FORGET THIS   │
└─────────────────────────────────────────────────────────┘
```
