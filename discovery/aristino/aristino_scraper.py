import asyncio
import json
import os
import sys
import io
import re
from playwright.async_api import async_playwright

# Thiết lập stdout/stderr hỗ trợ UTF-8 cho Windows Terminal để tránh UnicodeEncodeError
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Core settings
CHROME_CDP_URL = "http://localhost:9222"
COLLECTION_URL = "https://aristino.com/collections/trang-phuc"
OUTPUT_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "scraped_products.json")

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
            if val == "true":
                val = True
            elif val == "false":
                val = False
            result[pname] = val
    return result

async def get_ax_tree(page):
    """
    Trích xuất Accessibility Tree đầy đủ từ trang hiện tại qua CDP
    """
    cdp_session = await page.context.new_cdp_session(page)
    try:
        full_tree = await cdp_session.send("Accessibility.getFullAXTree")
        return full_tree.get("nodes", [])
    finally:
        await cdp_session.detach()

async def clean_popups(page):
    """
    Xóa bỏ các banner quảng cáo hoặc popup đè màn hình bằng JS
    """
    try:
        await page.evaluate("""() => {
            const selectors = [
                '#antsomi-slidedown-container',
                '.antsomi-slidedown-container',
                'div[id*="slidedown"]',
                'div[class*="slidedown"]',
                'div[class*="popup"]',
                'div[class*="modal"]',
                '.modal-backdrop'
            ];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
        }""")
    except Exception as e:
        print(f"[*] Lỗi khi dọn dẹp popup quảng cáo: {e}")

async def click_node_via_cdp(page, backend_node_id: int):
    """
    Cuộn đến và click vào node sử dụng backendDOMNodeId qua CDP
    """
    cdp = await page.context.new_cdp_session(page)
    try:
        await cdp.send("DOM.scrollIntoViewIfNeeded", {
            "backendNodeId": backend_node_id
        })
        await asyncio.sleep(0.5)

        box = await cdp.send("DOM.getBoxModel", {
            "backendNodeId": backend_node_id
        })
        content = box["model"]["content"]
        x = (content[0] + content[2]) / 2
        y = (content[1] + content[5]) / 2

        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
        })
        await cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
        })
        return True
    except Exception as e:
        print(f"[!] Lỗi click node id={backend_node_id}: {e}")
        return False
    finally:
        await cdp.detach()

def extract_categories(nodes):
    """
    Trích xuất toàn bộ checkbox danh mục sản phẩm thuộc nhóm 'SẢN PHẨM'
    """
    categories = []
    id_map = {n["nodeId"]: n for n in nodes}
    children_map = {}
    for n in nodes:
        nid = n["nodeId"]
        pid = n.get("parentId")
        if pid:
            if pid not in children_map:
                children_map[pid] = []
            children_map[pid].append(nid)

    def find_group_for_node(node_id):
        curr_id = node_id
        visited = set()
        while curr_id and curr_id not in visited:
            visited.add(curr_id)
            curr_node = id_map.get(curr_id)
            if not curr_node:
                break
            name = get_name(curr_node).upper()
            if name == "SẢN PHẨM":
                return "SẢN PHẨM"
            
            # Kiểm tra các sibling
            pid = curr_node.get("parentId")
            if pid:
                child_ids = children_map.get(pid, [])
                for cid in child_ids:
                    cnode = id_map.get(cid)
                    if cnode and get_name(cnode).upper() == "SẢN PHẨM":
                        return "SẢN PHẨM"
            curr_id = pid
        return None

    for node in nodes:
        if node.get("ignored"):
            continue
        role = get_role(node)
        name = get_name(node)
        bid = node.get("backendDOMNodeId")
        nid = node["nodeId"]
        
        if role == "checkbox" and name and bid:
            group = find_group_for_node(nid)
            if group == "SẢN PHẨM":
                categories.append({
                    "name": name,
                    "bid": bid,
                    "checked": get_props(node).get("checked", False)
                })
    return categories

def get_total_product_count(nodes):
    """
    Tìm số lượng sản phẩm tổng cộng hiển thị trên trang (ví dụ: '1363 sản phẩm')
    """
    for n in nodes:
        if get_role(n) == "StaticText":
            name = get_name(n)
            # Tìm pattern chứa số và chữ 'sản phẩm'
            match = re.search(r"(\d+)\s+sản\s+phẩm", name, re.IGNORECASE)
            if match:
                return int(match.group(1))
    return None

def extract_product_urls(nodes):
    """
    Trích xuất toàn bộ URL sản phẩm độc nhất hiện đang hiển thị
    """
    urls = set()
    for n in nodes:
        if get_role(n) == "link":
            props = get_props(n)
            url = props.get("url", "")
            if "/products/" in url:
                clean_url = url.split("?")[0]
                # Chuẩn hóa nếu là relative path
                if clean_url.startswith("/"):
                    clean_url = "https://aristino.com" + clean_url
                urls.add(clean_url)
    return list(urls)

async def toggle_checkbox(page, category_name: str, target_state: bool):
    """
    Click và chờ checkbox cập nhật trạng thái mục tiêu
    """
    print(f"[*] Đang {'chọn' if target_state else 'bỏ chọn'} danh mục '{category_name}'...")
    
    # Đóng popup trước khi thao tác
    await clean_popups(page)
    
    # Quét lại AX tree để lấy thông tin mới nhất
    nodes = await get_ax_tree(page)
    categories = extract_categories(nodes)
    
    target_cat = next((c for c in categories if c["name"] == category_name), None)
    if not target_cat:
        print(f"[!] Không tìm thấy danh mục '{category_name}' trên trang.")
        return False
        
    current_state = target_cat["checked"]
    if current_state == target_state:
        print(f"[*] Danh mục '{category_name}' đã ở trạng thái mong muốn.")
        return True
        
    # Kích hoạt click
    success = await click_node_via_cdp(page, target_cat["bid"])
    if not success:
        return False
        
    # Chờ tối đa 10s để trạng thái thay đổi trong AX tree
    print("[*] Chờ danh mục cập nhật bộ lọc trên trang...")
    for _ in range(10):
        await asyncio.sleep(1.5)
        new_nodes = await get_ax_tree(page)
        new_cats = extract_categories(new_nodes)
        new_target = next((c for c in new_cats if c["name"] == category_name), None)
        if new_target and new_target["checked"] == target_state:
            print(f"[OK] Cập nhật thành công trạng thái danh mục '{category_name}'!")
            return True
            
    print(f"[!] Cảnh báo: Trạng thái danh mục '{category_name}' chưa được phản hồi trong AX tree.")
    return False

async def scrape_current_category_products(page, category_name: str):
    """
    Quá trình cào toàn bộ sản phẩm của danh mục hiện tại bằng cách click 'Xem tất cả' nếu cần
    """
    print(f"\n🚀 BẮT ĐẦU CÀO SẢN PHẨM CHO DANH MỤC: '{category_name}'")
    print("-" * 50)
    
    # 1. Lấy dữ liệu ban đầu
    nodes = await get_ax_tree(page)
    total_count = get_total_product_count(nodes)
    
    if total_count is None:
        print("[!] Không tìm thấy số lượng sản phẩm tổng cộng. Đang thử quét sản phẩm trực tiếp...")
        urls = extract_product_urls(nodes)
        print(f"[+] Tìm thấy {len(urls)} sản phẩm hiển thị.")
        return urls
        
    print(f"[STATS] Tổng số sản phẩm cần lấy: {total_count}")
    
    # Vòng lặp bấm nút "Xem tất cả"
    while True:
        nodes = await get_ax_tree(page)
        urls = extract_product_urls(nodes)
        current_visible = len(urls)
        print(f"[*] Số sản phẩm đang hiển thị trên DOM: {current_visible}/{total_count}")
        
        if current_visible >= total_count:
            print("✅ Đã hiển thị đầy đủ toàn bộ sản phẩm!")
            break
            
        # Tìm nút "Xem tất cả"
        xem_tat_ca_btn = None
        for n in nodes:
            if get_role(n) == "button" and "xem tất cả" in get_name(n).lower():
                # Kiểm tra xem có bị disabled không
                if not get_props(n).get("disabled", False):
                    xem_tat_ca_btn = n
                    break
                    
        if not xem_tat_ca_btn:
            print("[*] Không tìm thấy nút 'Xem tất cả' hoặc nút đã bị ẩn/vô hiệu hóa.")
            break
            
        btn_bid = xem_tat_ca_btn.get("backendDOMNodeId")
        print(f"[*] Đang click nút 'Xem tất cả' (id={btn_bid}) để tải thêm sản phẩm...")
        
        # Bấm nút
        await clean_popups(page)
        click_ok = await click_node_via_cdp(page, btn_bid)
        if not click_ok:
            print("[!] Click nút 'Xem tất cả' thất bại. Dừng tải thêm.")
            break
            
        # Chờ 3s để tải dữ liệu AJAX mới
        await asyncio.sleep(3)
        
    # Quét lại lần cuối cùng để trích xuất đầy đủ URL
    final_nodes = await get_ax_tree(page)
    final_urls = extract_product_urls(final_nodes)
    print(f"🎉 Hoàn thành cào danh mục '{category_name}'! Tổng cộng: {len(final_urls)} URLs.")
    return final_urls

async def main():
    print("="*60)
    print("[SCRAPER] ARISTINO PRODUCT SCANNER BY CATEGORIES (AX TREE)")
    print("="*60)
    
    async with async_playwright() as p:
        print(f"[*] Kết nối tới trình duyệt Chrome qua CDP: {CHROME_CDP_URL}...")
        try:
            browser = await p.chromium.connect_over_cdp(CHROME_CDP_URL)
        except Exception as e:
            print(f"[!] Thất bại: {e}. Vui lòng chạy file chrome.bat trước.")
            sys.exit(1)
            
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Đặt viewport kích thước desktop để tránh responsive layout mobile
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Đi tới trang danh sách sản phẩm trực tiếp
        if page.url.rstrip('/') != COLLECTION_URL:
            print(f"[*] Đang chuyển tới trang danh mục: {COLLECTION_URL}...")
            await page.goto(COLLECTION_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            
        # Dọn dẹp popup quảng cáo ban đầu
        await clean_popups(page)
        
        # Quét lấy toàn bộ danh mục sản phẩm từ nhóm SẢN PHẨM
        print("[*] Đang phân tích các danh mục sản phẩm hiện có...")
        nodes = await get_ax_tree(page)
        categories = extract_categories(nodes)
        
        if not categories:
            print("[!] Không tìm thấy danh mục sản phẩm nào trong nhóm SẢN PHẨM.")
            await browser.close()
            sys.exit(1)
            
        print(f"✅ Đã tìm thấy {len(categories)} danh mục sản phẩm:")
        for idx, cat in enumerate(categories):
            print(f"  {idx+1}. {cat['name']} (id={cat['bid']})")
            
        # Hỏi ý kiến người dùng chạy toàn bộ hay chạy từng danh mục
        print("\n" + "="*50)
        print(" CHỌN CHẾ ĐỘ CÀO DỮ LIỆU:")
        print("  1. Cào toàn bộ danh mục (Chế độ tự động)")
        print("  2. Chỉ cào một danh mục cụ thể (Chọn theo số thứ tự)")
        print("="*50)
        
        choice = input("Nhập lựa chọn của bạn (1 hoặc 2) [Mặc định: 1]: ").strip()
        
        target_categories = []
        if choice == "2":
            try:
                cat_idx_str = input(f"Nhập số thứ tự danh mục để cào (1 - {len(categories)}): ").strip()
                cat_idx = int(cat_idx_str) - 1
                if 0 <= cat_idx < len(categories):
                    target_categories = [categories[cat_idx]]
                else:
                    print(f"[!] Số thứ tự không hợp lệ. Vui lòng nhập từ 1 đến {len(categories)}.")
                    await browser.close()
                    sys.exit(1)
            except ValueError:
                print("[!] Số thứ tự phải là một số nguyên.")
                await browser.close()
                sys.exit(1)
        else:
            target_categories = categories

        # Tạo cấu trúc lưu kết quả cào
        results = {}
        # Nếu file kết quả cũ đã tồn tại, đọc nó lên để bổ sung hoặc bắt đầu mới
        if os.path.exists(OUTPUT_JSON_PATH):
            try:
                with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
                    results = json.load(f)
            except Exception:
                pass
                
        # Duyệt qua các danh mục mục tiêu
        for cat in target_categories:
            name = cat["name"]
            
            # Bỏ chọn tất cả các danh mục khác trước để chỉ lọc riêng danh mục này
            nodes_before = await get_ax_tree(page)
            active_cats = extract_categories(nodes_before)
            for active_cat in active_cats:
                if active_cat["checked"] and active_cat["name"] != name:
                    await toggle_checkbox(page, active_cat["name"], False)
            
            # Chọn danh mục cần cào
            success = await toggle_checkbox(page, name, True)
            if not success:
                print(f"[!] Bỏ qua danh mục '{name}' do lỗi chọn bộ lọc.")
                continue
            
            # Chờ 3s để bộ lọc được áp dụng và danh sách sản phẩm được cập nhật hoàn toàn
            print("[*] Chờ 3s để bộ lọc được áp dụng và danh sách sản phẩm được cập nhật...")
            await asyncio.sleep(3)
                
            # Thực hiện cào sản phẩm
            product_urls = await scrape_current_category_products(page, name)
            results[name] = product_urls
            
            # Lưu kết quả sau mỗi danh mục để tránh mất dữ liệu nếu dừng đột ngột
            with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"💾 Đã lưu kết quả danh mục '{name}' vào file: {OUTPUT_JSON_PATH}")
            
            # Bỏ chọn sau khi cào xong
            await toggle_checkbox(page, name, False)
            
        print("\n" + "="*50)
        print("🏆 QUÁ TRÌNH CÀO DỮ LIỆU ĐÃ HOÀN THÀNH!")
        print(f"Tổng số danh mục đã cào: {len(target_categories)}")
        print(f"File kết quả lưu tại: {OUTPUT_JSON_PATH}")
        print("="*50)
        
        print("\n[*] Trình duyệt vẫn được giữ nguyên để bạn kiểm tra.")
        input("Nhấn Enter để đóng kết nối và thoát chương trình...")
        await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Đã dừng script.")
