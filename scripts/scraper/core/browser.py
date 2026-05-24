"""
core/browser.py — Quản lý kết nối Chrome và điều hướng trang.

Tham khảo từ: e:/AI_Manager/get_accessibility_tree.py
"""

import asyncio
import time
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from config import (
    BROWSER_URL, PAGE_LOAD_TIMEOUT, NETWORK_IDLE_TIMEOUT, USER_AGENT,
    HEADLESS_MODE
)


_playwright_context_manager = None
_browser: Optional[Browser] = None


async def connect_browser() -> Browser:
    """Khởi chạy Chrome cục bộ (headless) hoặc kết nối qua CDP tùy cấu hình."""
    global _browser, _playwright_context_manager
    if _browser is not None:
        return _browser

    _playwright_context_manager = await async_playwright().start()
    
    if HEADLESS_MODE:
        print(f"[Browser] Đang khởi chạy Chrome ngầm (headless=True)...")
        try:
            _browser = await _playwright_context_manager.chromium.launch(
                headless=True,
                args=["--disable-gpu", "--no-sandbox"]
            )
            print("[Browser] Khởi chạy thành công!")
            return _browser
        except Exception as e:
            print(f"[Browser] LỖI khởi chạy headless Chrome: {e}")
            raise
    else:
        print(f"[Browser] Đang kết nối tới Chrome tại {BROWSER_URL}...")
        try:
            _browser = await _playwright_context_manager.chromium.connect_over_cdp(BROWSER_URL)
            print(f"[Browser] Kết nối thành công! Có {len(_browser.contexts)} context(s).")
            return _browser
        except Exception as e:
            print(f"[Browser] LỖI kết nối CDP: {e}. Hãy chạy chrome_launcher.bat trước!")
            raise


async def create_new_page(browser: Browser) -> tuple[BrowserContext, Page]:
    """Tạo một BrowserContext và Page mới để chạy song song độc lập."""
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1280, "height": 800}
    )
    page = await context.new_page()
    return context, page


async def close_browser() -> None:
    """Đóng browser và stop playwright instance."""
    global _browser, _playwright_context_manager
    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None
    if _playwright_context_manager is not None:
        try:
            await _playwright_context_manager.stop()
        except Exception:
            pass
        _playwright_context_manager = None
    print("[Browser] Đã đóng Chrome và giải phóng tài nguyên.")


async def navigate_and_wait(page: Page, url: str) -> bool:
    """
    Navigate đến URL và chờ trang load xong.
    Returns True nếu thành công, False nếu lỗi.
    """
    try:
        await page.goto(
            url,
            timeout=PAGE_LOAD_TIMEOUT,
            wait_until="domcontentloaded"
        )
        # Chờ thêm để JS render
        try:
            await page.wait_for_load_state(
                "networkidle",
                timeout=NETWORK_IDLE_TIMEOUT
            )
        except Exception:
            pass  # Timeout networkidle là ok, vẫn tiếp tục
        return True
    except Exception as e:
        print(f"[Browser] LỖI navigate đến {url}: {e}")
        return False


async def scroll_to_bottom(page: Page, pause: float = 1.5, max_scrolls: int = 20) -> None:
    """
    Scroll trang xuống dần để trigger lazy-load.
    Dừng khi không còn nội dung mới.
    """
    prev_height = 0
    for i in range(max_scrolls):
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break  # Không còn nội dung mới
        prev_height = curr_height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(pause)
    print(f"[Browser] Đã scroll {i+1} lần.")


async def get_full_ax_tree(page: Page) -> dict:
    """
    Lấy toàn bộ Accessibility Tree qua CDP.
    Tương tự với get_accessibility_tree.py trong AI_Manager.
    """
    cdp = await page.context.new_cdp_session(page)
    tree = await cdp.send("Accessibility.getFullAXTree")
    await cdp.detach()
    return tree


async def get_page_html(page: Page) -> str:
    """Lấy HTML source sau khi JS đã render."""
    return await page.content()
