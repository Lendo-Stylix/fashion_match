import asyncio
import json
import os
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

async def main():
    url = "https://aristino.com/products/ao-khoac-blazer-nam-aristino-abzm040z"
    print(f"[*] Analyzing URL: {url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="networkidle")
        
        # Extract HTML
        html_content = await page.content()
        with open(os.path.join(BASE_DIR, "sample_product.html"), "w", encoding="utf-8") as f:
            f.write(html_content)
        print("[*] Saved sample_product.html")

        # Extract AX tree via CDP
        cdp = await page.context.new_cdp_session(page)
        full_tree = await cdp.send("Accessibility.getFullAXTree")
        with open(os.path.join(BASE_DIR, "sample_product_ax.json"), "w", encoding="utf-8") as f:
            json.dump(full_tree, f, ensure_ascii=False, indent=2)
        print("[*] Saved sample_product_ax.json")
        
        # Wait, also check if there's any Next.js JSON state script
        next_data = await page.evaluate('''() => {
            const script = document.getElementById('__NEXT_DATA__') || document.getElementById('__NUXT__');
            if (script) return script.textContent;
            return null;
        }''')
        
        if next_data:
            with open(os.path.join(BASE_DIR, "sample_product_state.json"), "w", encoding="utf-8") as f:
                f.write(next_data)
            print("[*] Found and saved __NEXT_DATA__ / __NUXT__ state!")
        else:
            print("[*] No SSR JSON state found.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
