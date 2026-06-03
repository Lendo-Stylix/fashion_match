import asyncio
import sys
from playwright.async_api import async_playwright

async def interact_with_node(backend_node_id: int, action: str = "click", text: str = None):
    """
    Kết nối tới trình duyệt đang mở và tương tác với node dựa trên backendDOMNodeId (lấy từ ax_compact.txt)
    """
    async with async_playwright() as p:
        browser_url = "http://localhost:9222"
        print(f"[*] Đang kết nối tới trình duyệt Chrome qua CDP: {browser_url}...")
        
        try:
            browser = await p.chromium.connect_over_cdp(browser_url)
        except Exception as e:
            print(f"[!] Lỗi kết nối: {e}. Đảm bảo Chrome đang chạy qua chrome.bat")
            return

        if not browser.contexts:
            print("[!] Không tìm thấy context nào đang mở.")
            return

        context = browser.contexts[0]
        if not context.pages:
            print("[!] Không có tab nào đang mở.")
            return

        # Lấy tab đang active (hoặc tab đầu tiên)
        page = context.pages[0]
        print(f"[*] Tương tác trên trang: {page.url}")

        # Khởi tạo CDP Session để gửi lệnh mức thấp
        cdp = await page.context.new_cdp_session(page)
        
        try:
            print(f"[*] Đang cuộn màn hình đến node id={backend_node_id}...")
            await cdp.send("DOM.scrollIntoViewIfNeeded", {
                "backendNodeId": backend_node_id
            })

            # Lấy tọa độ Box Model
            box = await cdp.send("DOM.getBoxModel", {
                "backendNodeId": backend_node_id
            })
            content = box["model"]["content"]
            # Tính toán tọa độ tâm của element (X, Y)
            x = (content[0] + content[2]) / 2
            y = (content[1] + content[5]) / 2

            if action == "click":
                print(f"[*] Thực hiện Click tại tọa độ ({x}, {y})")
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
                })
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
                })
                print("✅ Click thành công!")
                
            elif action == "type":
                print(f"[*] Thực hiện Click để Focus vào ô nhập liệu...")
                # Phải click để focus trước khi gõ phím
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
                })
                await cdp.send("Input.dispatchMouseEvent", {
                    "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
                })
                
                print(f"[*] Bắt đầu gõ text: '{text}'")
                # Dùng Playwright page.keyboard để gõ text dễ dàng hơn CDP Input.dispatchKeyEvent
                await page.keyboard.type(text, delay=100)
                print("✅ Gõ text thành công!")

        except Exception as e:
            print(f"[!] Lỗi khi tương tác với node {backend_node_id}: {e}")
            print("    -> Nguyên nhân có thể: Node ID không tồn tại, bị ẩn, hoặc tab đã bị đóng/chuyển trang.")
        finally:
            await cdp.detach()
            # Ngắt kết nối, không đóng browser
            await browser.close()

if __name__ == "__main__":
    print("="*50)
    print(" CÔNG CỤ TƯƠNG TÁC AX TREE BẰNG NODE ID")
    print("="*50)
    
    try:
        node_id_input = input("Nhập backendDOMNodeId (từ ax_compact.txt): ").strip()
        if not node_id_input.isdigit():
            print("[!] ID phải là một số nguyên.")
            sys.exit(1)
            
        target_id = int(node_id_input)
        
        action = input("Nhập hành động (click / type) [mặc định: click]: ").strip().lower()
        if not action:
            action = "click"
            
        text_to_type = None
        if action == "type":
            text_to_type = input("Nhập văn bản cần gõ: ")
            
        asyncio.run(interact_with_node(target_id, action, text_to_type))
        
    except KeyboardInterrupt:
        print("\n[!] Đã hủy thao tác.")
