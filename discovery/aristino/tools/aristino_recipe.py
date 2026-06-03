import asyncio
import json
import os
import sys
import io
from playwright.async_api import async_playwright

# Thiết lập stdout/stderr hỗ trợ UTF-8 cho Windows Terminal để tránh UnicodeEncodeError
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Core settings
CHROME_CDP_URL = "http://localhost:9222"
HOME_URL = "https://aristino.com"
TARGET_COLLECTION_URL = "https://aristino.com/collections/trang-phuc"

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

def build_tree_maps(nodes):
    """
    Xây dựng bản đồ nút và bản đồ quan hệ cha-con
    """
    id_map = {n["nodeId"]: n for n in nodes}
    children_map = {}
    root = None

    for n in nodes:
        nid = n["nodeId"]
        pid = n.get("parentId")
        if pid is None:
            root = n
        else:
            if pid not in children_map:
                children_map[pid] = []
            children_map[pid].append(nid)

    # Xử lý các node mồ côi (nếu có) bằng cách gắn vào root
    if root:
        root_id = root["nodeId"]
        if root_id not in children_map:
            children_map[root_id] = []
        for n in nodes:
            pid = n.get("parentId")
            if pid and pid not in id_map:
                children_map[root_id].append(n["nodeId"])

    return root, id_map, children_map

async def click_node_via_cdp(page, backend_node_id: int):
    """
    Cuộn đến và click vào node sử dụng backendDOMNodeId qua CDP
    """
    cdp = await page.context.new_cdp_session(page)
    try:
        # Cuộn màn hình đến phần tử
        await cdp.send("DOM.scrollIntoViewIfNeeded", {
            "backendNodeId": backend_node_id
        })
        # Chờ 0.5 giây để hiệu ứng cuộn mượt mà
        await asyncio.sleep(0.5)

        # Lấy Box Model để tính tọa độ tâm
        box = await cdp.send("DOM.getBoxModel", {
            "backendNodeId": backend_node_id
        })
        content = box["model"]["content"]
        x = (content[0] + content[2]) / 2
        y = (content[1] + content[5]) / 2

        # Gửi sự kiện Click chuột
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

def find_node_by_text_and_role(nodes, target_text, target_role):
    """
    Tìm kiếm node có role và name khớp với text
    """
    for n in nodes:
        role = get_role(n)
        name = get_name(n)
        if role == target_role and target_text.lower() in name.lower():
            return n
    return None

def extract_filters(nodes):
    """
    Nhóm các tùy chọn bộ lọc bằng cách tìm kiếm tổ tiên (ancestor) hoặc các sibling của tổ tiên
    có tên trùng với nhóm bộ lọc
    """
    filter_groups = {
        "NHÃN HÀNG": [],
        "MÀU SẮC": [],
        "SẢN PHẨM": [],
        "KÍCH CỠ": [],
        "FORM DÁNG": [],
        "GIÁ": []
    }
    
    # Xây dựng id_map và children_map
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
                
            # 1. Kiểm tra chính tên node này
            name = get_name(curr_node).upper()
            if name in filter_groups:
                return name
                
            # 2. Kiểm tra các sibling của node này (các con khác của parent)
            pid = curr_node.get("parentId")
            if pid:
                child_ids = children_map.get(pid, [])
                for cid in child_ids:
                    cnode = id_map.get(cid)
                    if cnode:
                        cname = get_name(cnode).upper()
                        if cname in filter_groups:
                            return cname
            curr_id = pid
        return None

    for node in nodes:
        if node.get("ignored"):
            continue
            
        role = get_role(node)
        name = get_name(node)
        bid = node.get("backendDOMNodeId")
        nid = node["nodeId"]
        
        if not bid or not name:
            continue
            
        # Tìm nhóm dựa trên cấu trúc cây/lân cận
        group = find_group_for_node(nid)
        
        if group:
            if role == "checkbox":
                if not any(item["bid"] == bid for item in filter_groups[group]):
                    filter_groups[group].append({
                        "name": name,
                        "bid": bid,
                        "role": role,
                        "checked": get_props(node).get("checked", False)
                    })
            elif group == "MÀU SẮC" and role == "StaticText":
                if name not in ["MÀU SẮC", "SẮP XẾP"] and len(name) > 1:
                    if not any(item["name"] == name for item in filter_groups[group]):
                        filter_groups[group].append({
                            "name": name,
                            "bid": bid,
                            "role": role,
                            "checked": False
                        })
                        
    return filter_groups

async def main():
    print("="*60)
    print("[RECIPE] ARISTINO AUTOMATION - ĐIỀU HƯỚNG & TRÍCH XUẤT BỘ LỌC")
    print("="*60)

    async with async_playwright() as p:
        print(f"[*] Kết nối tới trình duyệt Chrome qua CDP: {CHROME_CDP_URL}...")
        try:
            browser = await p.chromium.connect_over_cdp(CHROME_CDP_URL)
        except Exception as e:
            print(f"[!] Thất bại: {e}")
            print("    -> Vui lòng chạy file chrome.bat trước để mở Chrome ở cổng 9222.")
            sys.exit(1)

        # Lấy context và trang
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        # Đặt viewport kích thước desktop để đảm bảo hiển thị thanh menu ngang
        print("[*] Thiết lập kích thước màn hình 1920x1080 (Desktop)...")
        await page.set_viewport_size({"width": 1920, "height": 1080})

        # Bước 1: Điều hướng tới trang chủ nếu chưa ở trang chủ Aristino
        current_url = page.url.rstrip('/')
        if current_url != HOME_URL:
            print(f"[*] Đang chuyển hướng trình duyệt tới trang chủ: {HOME_URL}...")
            await page.goto(HOME_URL, wait_until="domcontentloaded")
            # Chờ thêm 3s để trang load đầy đủ
            await page.wait_for_timeout(3000)
        else:
            print(f"[*] Trình duyệt đang ở: {current_url}")

        # Bước 2: Phân tích AX Tree trang chủ để tìm nút "TRANG PHỤC" (Chờ động tối đa 15 giây)
        print("[*] Đang phân tích Accessibility Tree trang chủ (chờ tối đa 15s)...")
        trang_phuc_node = None
        nodes = []
        for attempt in range(15):
            nodes = await get_ax_tree(page)
            trang_phuc_node = find_node_by_text_and_role(nodes, "TRANG PHỤC", "link")
            if not trang_phuc_node:
                # Fallback tìm kiếm diện rộng
                for n in nodes:
                    name = get_name(n)
                    if "TRANG PHỤC" in name.upper() and n.get("backendDOMNodeId"):
                        trang_phuc_node = n
                        break
            if trang_phuc_node:
                break
            await asyncio.sleep(1)

        if not trang_phuc_node:
            print("[!] Rất tiếc, không tìm thấy nút 'TRANG PHỤC' trên trang chủ.")
            print(f"[DEBUG] Tổng số node lấy được: {len(nodes)}")
            print("[DEBUG] Các node có chứa chữ 'TRANG' hoặc 'PHỤC':")
            found_any = False
            for n in nodes:
                name = get_name(n)
                role = get_role(n)
                bid = n.get("backendDOMNodeId")
                if ("TRANG" in name.upper() or "PHỤC" in name.upper()) and bid:
                    print(f"  - Role: {role} | Name: '{name}' | id={bid}")
                    found_any = True
            if not found_any:
                print("  (Không tìm thấy node nào chứa chữ TRANG hoặc PHỤC)")
            
            print("[DEBUG] Danh sách 15 link đầu tiên trên trang:")
            link_count = 0
            for n in nodes:
                role = get_role(n)
                name = get_name(n)
                bid = n.get("backendDOMNodeId")
                if role == "link" and bid:
                    print(f"  - Link {link_count+1}: '{name}' | id={bid}")
                    link_count += 1
                    if link_count >= 15:
                        break
            await browser.close()
            sys.exit(1)

        bid = trang_phuc_node.get("backendDOMNodeId")
        name = get_name(trang_phuc_node)
        role = get_role(trang_phuc_node)
        print(f"[TARGET] Đã tìm thấy nút: Role='{role}' | Name='{name}' | backendDOMNodeId={bid}")

        # Bước 3: Click vào nút "TRANG PHỤC" (Thử nhiều cấp độ tương tác)
        print(f"[*] Thực hiện click vào nút '{name}' (id={bid})...")
        
        # Xóa các banner/popup quảng cáo cản trở click (như antsomi slidedown container)
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
                    document.querySelectorAll(sel).forEach(el => {
                        el.remove();
                    });
                });
            }""")
        except Exception as e:
            print(f"[*] Lỗi khi dọn dẹp popup quảng cáo: {e}")

        # Nhấn Escape để đóng các popup (nếu có)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        
        # Thử click vào link node
        click_success = await click_node_via_cdp(page, bid)
        await page.wait_for_timeout(2000)

        # Nếu vẫn ở trang chủ, thử click vào StaticText con của "TRANG PHỤC"
        if page.url.rstrip('/') == HOME_URL:
            child_text_node = find_node_by_text_and_role(nodes, "TRANG PHỤC", "StaticText")
            if child_text_node:
                child_bid = child_text_node.get("backendDOMNodeId")
                print(f"[*] Vẫn ở trang chủ. Thử click vào StaticText con (id={child_bid})...")
                await click_node_via_cdp(page, child_bid)
                await page.wait_for_timeout(2000)

        # Nếu vẫn ở trang chủ, sử dụng fallback click qua Playwright locator để đảm bảo chuyển hướng
        if page.url.rstrip('/') == HOME_URL:
            print("[*] Vẫn ở trang chủ. Sử dụng Playwright Locator fallback để click...")
            try:
                await page.locator("a:has-text('TRANG PHỤC')").first.click(timeout=5000)
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[!] Lỗi click fallback: {e}")

        # Chờ trang list sản phẩm tải xong
        print("[*] Chờ chuyển hướng và tải trang danh mục sản phẩm...")
        try:
            await page.wait_for_url("**/collections/trang-phuc**", timeout=10000)
            print("[OK] Đã chuyển hướng thành công tới trang danh sách sản phẩm!")
        except Exception:
            print(f"[*] URL hiện tại: {page.url} (Tiếp tục phân tích...)")
        
        # Bước 4: Trích xuất AX Tree của trang List để tìm khu vực "BỘ LỌC" (Chờ động tối đa 15 giây)
        print("[*] Đang phân tích Accessibility Tree trang danh sách sản phẩm (chờ bộ lọc load, tối đa 15s)...")
        
        filter_groups = {}
        list_nodes = []
        
        for attempt in range(15):
            list_nodes = await get_ax_tree(page)
            filter_groups = extract_filters(list_nodes)
            
            # Kiểm tra xem nhóm bộ lọc "SẢN PHẨM" hoặc nhóm khác đã xuất hiện chưa
            if any(len(options) > 0 for options in filter_groups.values()):
                break
            await asyncio.sleep(1)

        # Hiển thị các nhóm bộ lọc ra màn hình
        print("\n" + "="*50)
        print("[STATS] DANH MỤC LỌC SẢN PHẨM (SẢN PHẨM):")
        print("="*50)
        
        san_pham_options = filter_groups.get("SẢN PHẨM", [])
        all_options = {}  # Lưu trữ các option để user có thể tương tác
        option_idx = 1

        if san_pham_options:
            for opt in san_pham_options:
                status = "[x]" if opt["checked"] else "[ ]"
                print(f"  {option_idx}. {status} {opt['name']} (id={opt['bid']})")
                all_options[option_idx] = opt
                option_idx += 1
        else:
            print("[!] Không tìm thấy tùy chọn bộ lọc nào trong nhóm SẢN PHẨM.")
            await browser.close()
            sys.exit(0)

        print("\n" + "="*50)
        print("[INFO] GỢI Ý TƯƠNG TÁC DỰA TRÊN RECIPE:")
        print(" Nhập số thứ tự (1, 2, 3...) để click chọn danh mục sản phẩm tương ứng.")
        print(" Nhấn Enter để kết thúc và giữ nguyên trình duyệt để debug.")
        print("="*50)

        # Cho phép tương tác chọn bộ lọc trong CLI
        try:
            while True:
                user_choice = input("\n-> Nhập lựa chọn của bạn (hoặc Enter để thoát): ").strip()
                if not user_choice:
                    break
                
                if user_choice.isdigit():
                    idx = int(user_choice)
                    if idx in all_options:
                        target_opt = all_options[idx]
                        print(f"[*] Đang click vào bộ lọc: '{target_opt['name']}' (id={target_opt['bid']})...")
                        ok = await click_node_via_cdp(page, target_opt["bid"])
                        if ok:
                            print(f"[OK] Đã chọn '{target_opt['name']}'! Xem trình duyệt để thấy kết quả lọc.")
                            # Chờ chút để trang cập nhật kết quả lọc
                            await page.wait_for_timeout(2000)
                        else:
                            print("[!] Click bộ lọc thất bại.")
                    else:
                        print("[!] Số thứ tự không hợp lệ.")
                else:
                    print("[!] Vui lòng nhập số thứ tự hợp lệ.")
        except KeyboardInterrupt:
            print("\n[!] Đã thoát chế độ tương tác CLI.")

        # Ngắt kết nối cẩn thận, giữ Chrome chạy
        await browser.close()
        print("\n[*] Đã đóng kết nối CDP. Trình duyệt Chrome vẫn mở để bạn kiểm tra.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Đã dừng script.")
