"""
core/ax_utils.py — Xử lý Accessibility Tree.

Refactor & tối ưu từ:
  e:/AI_Manager/filter_ignored_nodes.py
  e:/AI_Manager/ax_compact.py
"""

# ── Phân loại Role ────────────────────────────────────────────────────────────

INTERACTIVE = {
    "button", "link", "textbox", "searchbox", "combobox",
    "listbox", "option", "checkbox", "radio",
    "menuitem", "tab", "switch", "slider",
}

LANDMARK = {
    "banner", "contentinfo", "navigation", "main",
    "search", "region", "complementary", "form", "dialog",
}

STRUCTURE = {"heading", "list", "listitem", "separator"}

ROOT = {"RootWebArea"}

SKIP = {"generic", "InlineTextBox", "none"}

KEEP_PROPS = {"focused", "disabled", "expanded", "checked", "level", "url", "editable", "required"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_role(node: dict) -> str:
    return node.get("role", {}).get("value", "")


def _get_name(node: dict) -> str:
    return node.get("name", {}).get("value", "").strip()


def _get_props(node: dict) -> dict:
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


def _should_keep(node: dict) -> bool:
    role = _get_role(node)
    name = _get_name(node)
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


def _format_node(role: str, name: str, bid, props: dict, depth: int) -> str:
    parts = [role]
    if name:
        parts.append(f'"{name}"')
    parts.append(f"id={bid}")

    state_parts = []
    for key in ["focused", "disabled", "expanded", "checked", "editable", "required"]:
        if key in props:
            val = props[key]
            state_parts.append(key if val is True else f"{key}={val}")
    if "level" in props:
        state_parts.append(f"level={props['level']}")
    if "url" in props:
        state_parts.append(f"url={props['url']}")
    if state_parts:
        parts.append("| " + ", ".join(state_parts))

    indent = "  " * depth
    base = " | ".join(parts[:3])
    extra = (" " + parts[3]) if len(parts) > 3 else ""
    return indent + base + extra


# ── API công khai ─────────────────────────────────────────────────────────────

def filter_ignored(ax_data: dict) -> dict:
    """
    Lọc bỏ các node có ignored=True.
    Input/Output: dict dạng {nodes: [...]}
    """
    nodes = ax_data.get("nodes", [])
    filtered = [n for n in nodes if not n.get("ignored")]
    return {"nodes": filtered}


def compact_tree(ax_data: dict) -> tuple[str, dict]:
    """
    Rút gọn AX Tree thành compact text.
    Returns (compact_text, stats_dict).
    """
    nodes = ax_data.get("nodes", [])
    id_map = {n["nodeId"]: n for n in nodes}

    # Build children map
    children_map: dict[str, list] = {}
    root = None
    for n in nodes:
        nid = n["nodeId"]
        pid = n.get("parentId")
        if pid is None:
            root = n
        else:
            children_map.setdefault(pid, []).append(nid)

    # Xử lý orphans (node cha đã bị lọc)
    if root:
        root_id = root["nodeId"]
        for n in nodes:
            pid = n.get("parentId")
            if pid and pid not in id_map:
                children_map.setdefault(root_id, []).append(n["nodeId"])

    if not root:
        return "", {"total": len(nodes), "kept": 0, "skipped": len(nodes)}

    lines = []
    stats = {"total": len(nodes), "kept": 0, "skipped": 0}

    def dfs(node_id: str, depth: int = 0):
        if node_id not in id_map:
            return
        node = id_map[node_id]
        role = _get_role(node)
        name = _get_name(node)
        bid = node.get("backendDOMNodeId", "?")
        props = _get_props(node)

        if _should_keep(node):
            lines.append(_format_node(role, name, bid, props, depth))
            stats["kept"] += 1
            next_depth = depth + 1
        else:
            stats["skipped"] += 1
            next_depth = depth  # Không tăng depth

        for child_id in children_map.get(node_id, []):
            dfs(child_id, next_depth)

    dfs(root["nodeId"])
    return "\n".join(lines), stats


def extract_static_texts(ax_data: dict) -> list[str]:
    """
    Trích xuất tất cả StaticText có nội dung để phân tích text.
    Dùng để parse thông tin sản phẩm khi không có structured payload.
    """
    texts = []
    for node in ax_data.get("nodes", []):
        if _get_role(node) == "StaticText":
            name = _get_name(node)
            if name and len(name) > 1:
                texts.append(name)
    return texts
