import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright

# Define paths relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(BASE_DIR, "input.txt")
RAW_OUTPUT = os.path.join(BASE_DIR, "ax_full_raw.json")
FILTERED_OUTPUT = os.path.join(BASE_DIR, "ax_no_ignored.json")
COMPACT_OUTPUT = os.path.join(BASE_DIR, "ax_compact.txt")

# Roles configuration for compacting (from ax_compact.py)
INTERACTIVE = {
    "button", "link", "textbox", "searchbox", "combobox",
    "listbox", "option", "checkbox", "radio",
    "menuitem", "tab", "switch", "slider"
}
LANDMARK = {
    "banner", "contentinfo", "navigation", "main",
    "search", "region", "complementary", "form", "dialog"
}
STRUCTURE = {"heading", "list", "listitem", "separator"}
ROOT = {"RootWebArea"}
SKIP = {"generic", "InlineTextBox", "none"}
KEEP_PROPS = {"focused", "disabled", "expanded", "checked", "level", "url", "editable", "required"}

def get_role(node):
    return node.get("role", {}).get("value", "")

def get_name(node):
    return node.get("name", {}).get("value", "").strip()

def get_props(node):
    result = {}
    for p in node.get("properties", []):
        pname = p["name"]
        if pname not in KEEP_PROPS:
            continue
        val = p["value"].get("value")
        if val is None or val is False or val == "false":
            continue
        if pname == "url" and isinstance(val, str) and len(val) > 80:
            val = val[:77] + "..."
        result[pname] = val
    return result

def should_keep(node):
    role = get_role(node)
    name = get_name(node)
    children = node.get("childIds", [])

    if role in ROOT or role in INTERACTIVE or role in LANDMARK:
        return True
    if role in STRUCTURE and (name or children):
        return True
    if role == "StaticText" and name and len(name) > 1:
        return True
    if role == "image" and name:
        return True
    return False

def format_node(role, name, bid, props, depth):
    parts = [role]
    if name:
        parts.append(f'"{name}"')
    parts.append(f"id={bid}")

    state_parts = []
    for key in ["focused", "disabled", "expanded", "checked", "editable", "required"]:
        if key in props:
            val = props[key]
            if val is True:
                state_parts.append(key)
            else:
                state_parts.append(f"{key}={val}")

    if "level" in props:
        state_parts.append(f"level={props['level']}")
    if "url" in props:
        state_parts.append(f"url={props['url']}")

    if state_parts:
        parts.append("| " + ", ".join(state_parts))

    indent = "  " * depth
    return indent + " | ".join(parts[:3]) + (" " + parts[3] if len(parts) > 3 else "")

def compact_tree(json_data):
    nodes = json_data.get("nodes", [])
    if not nodes:
        return "", {}

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

    orphans = []
    for n in nodes:
        pid = n.get("parentId")
        if pid and pid not in id_map:
            orphans.append(n)

    if orphans and root:
        root_id = root["nodeId"]
        if root_id not in children_map:
            children_map[root_id] = []
        for orph in orphans:
            children_map[root_id].append(orph["nodeId"])

    if not root:
        return "", {}

    lines = []
    stats = {"total": len(nodes), "kept": 0, "skipped": 0}

    def dfs(node_id, depth=0):
        if node_id not in id_map:
            return

        node = id_map[node_id]
        role = get_role(node)
        name = get_name(node)
        bid = node.get("backendDOMNodeId", "?")
        props = get_props(node)

        if should_keep(node):
            line = format_node(role, name, bid, props, depth)
            lines.append(line)
            stats["kept"] += 1
            next_depth = depth + 1
        else:
            stats["skipped"] += 1
            next_depth = depth

        for child_id in children_map.get(node_id, []):
            dfs(child_id, next_depth)

    dfs(root["nodeId"])
    return "\n".join(lines), stats

async def main():
    if not os.path.exists(INPUT_FILE):
        print(f"[!] Không tìm thấy file {INPUT_FILE}. Vui lòng tạo file và nhập URL.")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        url = f.read().strip()

    if not url:
        print(f"[!] File {INPUT_FILE} trống. Vui lòng thêm URL.")
        sys.exit(1)

    print(f"[*] Đọc URL từ input.txt: {url}")

    async with async_playwright() as p:
        browser_url = "http://localhost:9222"
        print(f"[*] Đang kết nối tới trình duyệt Chrome qua CDP: {browser_url}...")
        
        try:
            browser = await p.chromium.connect_over_cdp(browser_url)
        except Exception as e:
            print(f"[!] Lỗi kết nối: {e}")
            print("    -> Vui lòng chạy file chrome.bat trước để mở Chrome ở cổng 9222.")
            sys.exit(1)

        # Lấy context mặc định hoặc tạo mới
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        try:
            print(f"[*] Đang điều hướng đến: {url} ...")
            await page.goto(url, wait_until="domcontentloaded")
            # Chờ thêm một chút để trang ổn định
            await page.wait_for_timeout(2000)

            print("[*] Đang trích xuất Accessibility Tree...")
            cdp_session = await page.context.new_cdp_session(page)
            full_tree = await cdp_session.send("Accessibility.getFullAXTree")

            # 1. Lưu bản Raw JSON
            with open(RAW_OUTPUT, "w", encoding="utf-8") as f:
                json.dump(full_tree, f, ensure_ascii=False, indent=2)
            print(f"✅ Đã lưu bản RAW JSON: {RAW_OUTPUT}")

            # 2. Lọc bỏ các node bị 'ignored'
            nodes = full_tree.get("nodes", [])
            filtered_nodes = [node for node in nodes if not node.get("ignored")]
            filtered_tree = {**full_tree, "nodes": filtered_nodes}
            
            with open(FILTERED_OUTPUT, "w", encoding="utf-8") as f:
                json.dump(filtered_tree, f, ensure_ascii=False, indent=2)
            print(f"✅ Đã lọc bỏ 'ignored' nodes và lưu: {FILTERED_OUTPUT}")

            # 3. Rút gọn cây (Compacting)
            compact_text, stats = compact_tree(filtered_tree)
            with open(COMPACT_OUTPUT, "w", encoding="utf-8") as f:
                f.write(compact_text)
            print(f"✅ Đã tạo bản rút gọn compact text: {COMPACT_OUTPUT}")

            # Thống kê
            if stats:
                reduction = (stats["skipped"] / stats["total"]) * 100 if stats["total"] > 0 else 0
                print("\n" + "="*50)
                print("📊 THỐNG KÊ RÚT GỌN AX TREE:")
                print(f" - Tổng số nodes:      {stats['total']}")
                print(f" - Số nodes giữ lại:   {stats['kept']}")
                print(f" - Số nodes loại bỏ:   {stats['skipped']}")
                print(f" - Tỉ lệ nén giảm tải: {reduction:.2f}%")
                print("="*50 + "\n")

        except Exception as e:
            print(f"[!] Có lỗi xảy ra trong quá trình xử lý trang: {e}")
        finally:
            # Không đóng tab để người dùng có thể debug trực tiếp trên Chrome
            pass

if __name__ == "__main__":
    asyncio.run(main())
