import base64
import html
import json
import os
import time
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_ace import st_ace
from streamlit_local_storage import LocalStorage

BACKEND_URL = "http://backend:8000"
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
localS = LocalStorage()

st.set_page_config(page_title="机械臂工作台", page_icon="🤖", layout="wide", initial_sidebar_state="expanded")

# ── CSS ────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* ── 全局 ── */
nav[data-testid="stSidebarNav"] { display: none !important; }
div[data-testid="stSidebarNav"] { display: none !important; }
ul[data-testid="stSidebarNavItems"] { display: none !important; }
div[data-testid="stSidebarNavSeparator"] { display: none !important; }
.block-container { padding-top: 0.25rem !important; }
.brand { font-size: 1.15rem; font-weight: 600; }

/* ── 侧边栏整体 ── */
section[data-testid="stSidebar"] > div { padding: 0.5rem 0.4rem 0.4rem !important; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
  margin: 0 !important; padding: 0 !important;
}

/* ── 侧边栏内的 Streamlit 按钮（刷新、保存、操作等） ── */
section[data-testid="stSidebar"] .stButton { margin: 0 !important; }
section[data-testid="stSidebar"] .stButton > button {
  font-size: 12px !important; line-height: 1.05 !important;
  min-height: 20px !important; height: 20px !important;
  padding: 0 4px !important;
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  color: #2f3438 !important;
  width: 100%;
  text-align: left !important;
  justify-content: flex-start !important;
  font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(128,128,128,0.15) !important;
}
/* 历史树：贴近 VS Code，使用等宽字体和更紧凑间距 */
section[data-testid="stSidebar"] div[class*="st-key-tree_select_"] button,
section[data-testid="stSidebar"] div[class*="st-key-tree_rename_"] button,
section[data-testid="stSidebar"] div[class*="st-key-tree_mark_final_"] button {
  font-family: Consolas, "Cascadia Mono", "Courier New", monospace !important;
  font-size: 11px !important;
  min-height: 19px !important;
  height: 19px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}
section[data-testid="stSidebar"] div[class*="st-key-tree_select_"] button {
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}
section[data-testid="stSidebar"] div[class*="st-key-tree_rename_"] button,
section[data-testid="stSidebar"] div[class*="st-key-tree_mark_final_"] button {
  min-width: 22px !important;
  width: 22px !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
  justify-content: center !important;
  text-align: center !important;
  overflow: visible !important;
}
section[data-testid="stSidebar"] div[class*="st-key-tree_rename_"] .stButton,
section[data-testid="stSidebar"] div[class*="st-key-tree_mark_final_"] .stButton {
  min-width: 22px !important;
  width: 22px !important;
  overflow: visible !important;
}
/* 侧边栏内 text_input 紧凑 */
section[data-testid="stSidebar"] .stTextInput { margin: 0 !important; }
section[data-testid="stSidebar"] .stTextInput input {
  font-size: 11px !important;
  height: 19px !important;
  min-height: 19px !important;
  max-height: 19px !important;
  padding: 0 4px !important;
  border-radius: 0 !important;
  border: 1px solid rgba(60,60,60,0.35) !important;
  box-sizing: border-box !important;
}
section[data-testid="stSidebar"] div[class*="st-key-rn_inline_"] .stTextInput {
  margin: 0 !important;
  padding: 0 !important;
}
section[data-testid="stSidebar"] div[class*="st-key-rn_inline_"] input {
  line-height: 19px !important;
}
section[data-testid="stSidebar"] div[class*="st-key-rn_inline_"] [data-testid="stWidgetLabel"],
section[data-testid="stSidebar"] div[class*="st-key-rn_inline_"] p {
  display: none !important;
}
section[data-testid="stSidebar"] div[class*="st-key-rn_inline_"] [data-baseweb="input"] {
  min-height: 19px !important;
  height: 19px !important;
}
section[data-testid="stSidebar"] div[class*="st-key-history_search"] {
  margin: 0 !important;
  padding: 0 !important;
  min-height: 19px !important;
  height: 19px !important;
  overflow: hidden !important;
}
section[data-testid="stSidebar"] div[class*="st-key-history_search"] .stTextInput,
section[data-testid="stSidebar"] div[class*="st-key-history_search"] [data-testid="stTextInput"] {
  margin: 0 !important;
  padding: 0 !important;
  min-height: 19px !important;
  height: 19px !important;
}
section[data-testid="stSidebar"] div[class*="st-key-history_search"] [data-baseweb="input"] {
  min-height: 19px !important;
  height: 19px !important;
  border-radius: 0 !important;
}
section[data-testid="stSidebar"] div[class*="st-key-history_search"] input {
  height: 19px !important;
  min-height: 19px !important;
  max-height: 19px !important;
  font-size: 11px !important;
  line-height: 19px !important;
  padding: 0 4px !important;
}
section[data-testid="stSidebar"] .stTextInput label { display: none; }

/* ── 主区参数栏 icon 按钮：无边框无气泡 ── */
.icon-btn > div > button, .icon-btn button {
  min-height: 24px !important; max-height: 24px !important;
  width: 24px !important; padding: 0 !important;
  font-size: 15px !important; line-height: 1 !important;
  border: none !important; border-radius: 3px !important;
  background: transparent !important; box-shadow: none !important;
  color: #555 !important;
}
.icon-btn > div > button:hover, .icon-btn button:hover {
  background: rgba(0,0,0,0.07) !important; color: #111 !important;
}
.icon-btn button svg {
  display: none !important;
}
.icon-btn button [data-testid="stMarkdownContainer"] {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
div[class*="st-key-toggle_param_settings"] button,
div[class*="st-key-toggle_param_collapse"] button {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  border-radius: 0 !important;
}
div[class*="st-key-toggle_param_settings"] button:hover,
div[class*="st-key-toggle_param_collapse"] button:hover {
  background: rgba(0,0,0,0.07) !important;
}
div.st-key-param_panel {
  border: 1px solid #e6e6ea !important;
  border-radius: 6px !important;
  padding: 2px 6px 12px 6px !important;
}
div.st-key-param_panel div[data-testid="stVerticalBlock"] > div {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}
div.st-key-param_panel div[data-testid="stVerticalBlock"],
div.st-key-param_panel div[data-testid="stHorizontalBlock"] {
  gap: 12px !important;
}
div.st-key-param_header_row div[data-testid="stHorizontalBlock"] {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  padding-top: 0 !important;
  padding-bottom: 2px !important;
  min-height: 26px !important;
  align-items: center !important;
}
div.st-key-param_header_row p {
  margin: 0 !important;
}
/* 标题 markdown 垂直居中 */
div.st-key-param_header_row .stMarkdown {
  display: flex !important;
  align-items: center !important;
  padding: 0 !important;
  margin: 0 !important;
}
div.st-key-param_header_row .stMarkdown p {
  margin: 0 !important;
  line-height: 1 !important;
}
div.st-key-param_panel [data-testid="stWidgetLabel"] {
  min-height: 16px !important;
  margin-bottom: 0 !important;
  display: flex !important;
  align-items: center !important;
}
div.st-key-param_panel [data-testid="stWidgetLabel"] label,
div.st-key-param_panel [data-testid="stWidgetLabel"] p {
  font-size: 14px !important;
  line-height: 1 !important;
  margin: 0 !important;
  padding: 0 !important;
}
div.st-key-param_panel .stTextInput,
div.st-key-param_panel .stSelectbox,
div.st-key-param_panel .stSlider {
  margin: 0 !important;
  padding: 0 !important;
}
div.st-key-param_panel [data-baseweb="input"],
div.st-key-param_panel [data-baseweb="select"] {
  min-height: 30px !important;
  height: 30px !important;
  display: flex !important;
  align-items: center !important;
}
div.st-key-param_panel input {
  min-height: 30px !important;
  height: 30px !important;
  padding: 0 6px !important;
  font-size: 15px !important;
  line-height: 30px !important;
}
div.st-key-param_panel [data-baseweb="select"] > div {
  min-height: 30px !important;
  height: 30px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  font-size: 15px !important;
  align-items: center !important;
}
div.st-key-param_panel .stSlider [data-testid="stTickBar"],
div.st-key-param_panel .stSlider [data-testid="stThumbValue"] {
  display: none !important;
}
div.st-key-param_panel .stSlider [data-baseweb="slider"] {
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  min-height: 18px !important;
}
div[class*="st-key-toggle_param_settings"] button,
div[class*="st-key-toggle_param_collapse"] button {
  min-height: 24px !important;
  max-height: 24px !important;
  height: 24px !important;
  margin-top: 8px !important;
}
div.st-key-video_panel div[data-testid="stVerticalBlockBorderWrapper"],
div[class*="st-key-video_panel"] div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #f6f7f9 !important;
  border-color: #e5e7eb !important;
  overflow: hidden !important;
}
div.st-key-video_panel iframe,
div[class*="st-key-video_panel"] iframe {
  display: block !important;
  width: 100% !important;
  border: none !important;
}
div.st-key-notes_section {
  margin-top: -18px !important;
}
div.st-key-notes_section h5 {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
  line-height: 1.05 !important;
}
div.st-key-notes_section div[data-testid="stVerticalBlock"] > div {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
div.st-key-notes_section .stTextArea {
  margin-top: 0 !important;
}

/* ── 设置图标：隐藏 popover 下拉箭头（保留点击弹窗功能） ── */
div.st-key-param_header_row [data-testid="stPopover"] {
  margin: 0 !important;
  padding: 0 !important;
}
div.st-key-param_header_row [data-testid="stPopover"] button {
  min-height: 24px !important;
  height: 24px !important;
  width: 24px !important;
  padding: 0 !important;
  margin-top: 10px !important;
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}
div.st-key-param_header_row [data-testid="stPopover"] button:hover {
  background: rgba(0,0,0,0.07) !important;
}
div.st-key-param_header_row [data-testid="stPopover"] button svg,
div.st-key-param_header_row [data-testid="stPopover"] button [data-testid*="arrow"],
div.st-key-param_header_row [data-testid="stPopover"] button > span:last-child > svg,
div.st-key-param_header_row [data-testid="stPopover"] button > div > svg {
  display: none !important;
}
div.st-key-param_header_row [data-testid="stPopover"] button::after {
  display: none !important;
  content: none !important;
}
/* 消除 popover 按钮右侧自动插入的 caret 容器 */
div.st-key-param_header_row [data-testid="stPopover"] button [class*="caret"],
div.st-key-param_header_row [data-testid="stPopover"] button [class*="arrow"],
div.st-key-param_header_row [data-testid="stPopover"] button [class*="chevron"] {
  display: none !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# ── 工具函数 ────────────────────────────────────────────────────────────────

def parse_json_field(value, default):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except Exception:
            return default
    return default


def api_get(path, timeout=30):
    return requests.get(f"{BACKEND_URL}{path}", timeout=timeout)


def api_post(path, payload, timeout=30):
    return requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=timeout)


def api_put(path, payload, timeout=30):
    return requests.put(f"{BACKEND_URL}{path}", json=payload, timeout=timeout)


def cancel_current_job():
    """取消当前正在运行的模拟任务（如有）。"""
    job_id = st.session_state.get("current_job_id")
    if job_id and st.session_state.get("is_simulation_running"):
        try:
            api_post(f"/cancel/{job_id}", {}, timeout=8)
        except Exception:
            pass
        st.session_state.is_simulation_running = False
        st.session_state.current_job_id = None


@st.cache_data(ttl=20, show_spinner=False)
def get_history_tree():
    try:
        resp = api_get("/history/tree")
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                for key in ("tree", "items", "data", "history"):
                    val = payload.get(key)
                    if isinstance(val, list):
                        return val
    except requests.exceptions.RequestException:
        pass

    try:
        resp = api_get("/history")
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, list):
                return [
                    {**item, "children": []}
                    for item in payload
                    if isinstance(item, dict) and item.get("id") is not None
                ]
            if isinstance(payload, dict):
                flat = payload.get("history") or payload.get("items") or payload.get("data") or []
                if isinstance(flat, list):
                    return [
                        {**item, "children": []}
                        for item in flat
                        if isinstance(item, dict) and item.get("id") is not None
                    ]
    except requests.exceptions.RequestException:
        pass
    return []


def invalidate_history_cache():
    try:
        get_history_tree.clear()
    except Exception:
        pass


@st.cache_data(ttl=60, show_spinner=False)
def get_available_algorithms():
    try:
        resp = api_get("/algorithms")
        if resp.status_code == 200:
            return sorted(resp.json().get("algorithms", []))
    except requests.exceptions.RequestException:
        return []
    return []


@st.cache_data(ttl=300, show_spinner=False)
def get_params_for_algorithm(algorithm_name):
    if not algorithm_name:
        return None
    try:
        resp = api_get(f"/algorithms/{algorithm_name}/params")
        if resp.status_code == 200:
            return resp.json()
    except requests.exceptions.RequestException:
        return None
    return None


def fetch_models(api_key, base_url):
    if not api_key or not base_url:
        return [], "缺少 API Key 或 Base URL"
    try:
        resp = api_post("/models", {"api_key": api_key, "base_url": base_url}, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("models", []), data.get("error")
        return [], f"HTTP 错误: {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return [], str(e)


def flatten_nodes(nodes, result=None):
    if result is None:
        result = {}
    for node in nodes:
        result[node["id"]] = node
        flatten_nodes(node.get("children", []), result)
    return result


def normalize_history_tree(nodes):
    """按 parent_id 重建树；无父级草稿保留为独立主条目。"""
    flat_nodes = []

    def collect(items):
        for item in items:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            children = item.get("children") or []
            node = {**item, "children": []}
            flat_nodes.append(node)
            collect(children)

    collect(nodes)
    node_by_id = {node["id"]: node for node in flat_nodes}
    roots = []

    for node in flat_nodes:
        parent_id = node.get("parent_id")
        parent = node_by_id.get(parent_id)
        if parent is not None and parent is not node:
            parent.setdefault("children", []).append(node)
        else:
            roots.append(node)

    def sort_branch_items(items):
        items.sort(key=lambda item: item.get("id") or 0)
        for item in items:
            sort_branch_items(item.get("children") or [])
        return items

    roots.sort(key=lambda item: item.get("id") or 0, reverse=True)
    for root in roots:
        sort_branch_items(root.get("children") or [])
    return roots


def filter_main_history_nodes(nodes, query):
    """只按主条目名称筛选，匹配后保留其分支草稿。"""
    keyword = (query or "").strip().lower()
    if not keyword:
        return nodes
    return [
        node
        for node in nodes
        if keyword in node_display_name(node).lower()
    ]


def history_status_color(node):
    status = node.get("status")
    if status == "success":
        return "#28a745"
    if status == "failed":
        return "#dc3545"
    return "#111111"


def find_main_root_id(node_id, node_map):
    """从任意节点向上回溯到所属的主干（root）id。
    若 node 已是 root（无 parent_id），则返回它自己。
    """
    if node_id is None:
        return None
    cur_id = node_id
    visited = set()
    while cur_id is not None and cur_id not in visited:
        visited.add(cur_id)
        node = node_map.get(cur_id)
        if not node:
            return cur_id
        pid = node.get("parent_id")
        if not pid:
            return cur_id
        cur_id = pid
    return cur_id


def load_node_to_state(node):
    autosave_current_code(force=True)

    # 切换历史节点时，强制取消正在进行的模拟任务
    cancel_current_job()

    params = parse_json_field(node.get("params"), {})
    result = parse_json_field(node.get("result"), {})
    new_code = result.get("generated_code") or result.get("code") or ""
    st.session_state.selected_node_id = node["id"]
    st.session_state.code_editor = new_code
    st.session_state.ace_editor_version += 1  # 强制重建编辑器以刷新内容
    st.session_state.simulation_video = result.get("video")
    st.session_state.run_result = result
    st.session_state.notes_input = node.get("notes", "") or ""
    st.session_state.task_description = node.get("task_description", "") or ""
    st.session_state.selected_algorithm = node.get("algorithm")
    st.session_state.dynamic_params_from_node = params
    # 跟踪草稿状态
    is_draft = node.get("status") == "unsimulated"
    if is_draft:
        st.session_state.current_draft_id = node["id"]
    else:
        st.session_state.current_draft_id = None


def node_display_name(n):
    raw_name = n.get("experiment_name") or n.get("experiment_id") or str(n.get("id"))
    return str(raw_name).split(",")[0].strip()


def truncate_name_for_tree(name: str, depth: int) -> str:
    return name


def commit_inline_rename(node_id: int, input_key: str):
    """on_change 回调：在回调内调用 st.rerun() 可能被吞掉，
    这里只更新 session_state，由 Streamlit 自然 rerun。"""
    new_name = (st.session_state.get(input_key) or "").strip()
    if not new_name:
        st.session_state.rename_node_id = None
        return
    try:
        resp = api_put(f"/history/{node_id}/rename", {"new_name": new_name})
        if resp.status_code != 200:
            st.session_state["_rename_error"] = f"重命名失败: {resp.text}"
            return
        # 成功：退出重命名模式，并清掉残留输入；Streamlit 会自动 rerun。
        st.session_state.rename_node_id = None
        st.session_state.pop(input_key, None)
        st.session_state["_rename_toast"] = f"已重命名为 “{new_name}”"
        invalidate_history_cache()
    except requests.exceptions.RequestException as e:
        st.session_state["_rename_error"] = f"重命名失败: {e}"


def render_tree_nodes(nodes, guides=None):
    if guides is None:
        guides = []

    for idx, node in enumerate(nodes):
        nid = node["id"]
        children = node.get("children") or []
        is_selected = st.session_state.selected_node_id == nid
        is_last = idx == len(nodes) - 1

        # 用 | 绘制文件树式引导线；所有节点始终展开，不显示折叠箭头。
        if guides:
            prefix = "".join("| " if g else "  " for g in guides[:-1]) + "| "
        else:
            prefix = ""
        visible_name = truncate_name_for_tree(node_display_name(node), len(guides))
        is_branch = bool(node.get("parent_id")) or node.get("node_type") == "branch"
        label = f"{prefix}{visible_name}"
        if node.get("is_final"):
            label += " ★"
        if is_branch:
            branch_indent = "  " * len(guides)
            label = f"{branch_indent}◇ {visible_name}" + (" ★" if node.get("is_final") else "")

        has_mark_button = is_branch and node.get("parent_id")
        row_cols = st.columns([1, 0.22, 0.22] if has_mark_button else [1, 0.22], gap="small")
        with row_cols[0]:
            if is_selected:
                st.markdown(
                    f"""
<style>
section[data-testid="stSidebar"] div.st-key-tree_select_{nid} button {{
  background: linear-gradient(90deg, #9aa0a6 0 2px, rgba(128,128,128,0.18) 2px 100%) !important;
}}
</style>
""",
                    unsafe_allow_html=True,
                )
            st.markdown(
                f"""
<style>
section[data-testid="stSidebar"] div.st-key-tree_select_{nid} button {{
  color: {history_status_color(node)} !important;
}}
</style>
""",
                unsafe_allow_html=True,
            )
            if st.session_state.rename_node_id == nid:
                rename_key = f"rn_inline_{nid}"
                if rename_key not in st.session_state:
                    st.session_state[rename_key] = node_display_name(node)
                st.text_input(
                    "",
                    key=rename_key,
                    label_visibility="collapsed",
                    on_change=commit_inline_rename,
                    args=(nid, rename_key),
                    placeholder="输入新名称后回车",
                )
            else:
                if st.button(
                    label,
                    key=f"tree_select_{nid}",
                    use_container_width=True,
                ):
                    load_node_to_state(node)
                    st.rerun()
        if has_mark_button:
            with row_cols[1]:
                if st.button("★", key=f"tree_mark_final_{nid}", use_container_width=True):
                    resp = api_post(f"/history/{nid}/mark-final", {"root_id": node.get("parent_id")})
                    if resp.status_code == 200:
                        st.toast("已标记最终版并覆盖主条目代码")
                        invalidate_history_cache()
                        st.rerun()
                    else:
                        st.error(f"标记失败: {resp.text}")
            rename_col = row_cols[2]
        else:
            rename_col = row_cols[1]

        with rename_col:
            if st.button("✎", key=f"tree_rename_{nid}", use_container_width=True):
                st.session_state[f"rn_inline_{nid}"] = node_display_name(node)
                st.session_state.rename_node_id = nid
                st.rerun()

        # 始终展开子节点（无折叠箭头）
        if children:
            render_tree_nodes(children, guides + [not is_last])


def save_notes(node_id, notes):
    try:
        resp = api_put(f"/history/{node_id}/notes", {"notes": notes})
        if resp.status_code == 200:
            st.toast("备注已保存")
    except requests.exceptions.RequestException as e:
        st.error(f"保存备注失败: {e}")


def ensure_default_expanded(tree_nodes):
    if st.session_state.expanded_nodes:
        return
    for n in tree_nodes:
        nid = n.get("id")
        if nid is not None:
            st.session_state.expanded_nodes.add(nid)


# ── session 默认值 ───────────────────────────────────────────────────────────
if "selected_node_id" not in st.session_state:
    st.session_state.selected_node_id = None
if "code_editor" not in st.session_state:
    st.session_state.code_editor = localS.getItem("current_code") or ""
if "ace_editor_version" not in st.session_state:
    st.session_state.ace_editor_version = 0
if "simulation_video" not in st.session_state:
    st.session_state.simulation_video = None
if "run_result" not in st.session_state:
    st.session_state.run_result = {}
if "notes_input" not in st.session_state:
    st.session_state.notes_input = ""
if "task_description" not in st.session_state:
    st.session_state.task_description = "把红色的方块放到蓝色的碗里"
if "selected_algorithm" not in st.session_state:
    st.session_state.selected_algorithm = None
if "available_models" not in st.session_state:
    st.session_state.available_models = []
if "openai_api_key_value" not in st.session_state:
    st.session_state.openai_api_key_value = localS.getItem("openai_api_key") or ""
if "openai_base_url_value" not in st.session_state:
    st.session_state.openai_base_url_value = localS.getItem("openai_base_url") or ""
if "openai_model_value" not in st.session_state:
    st.session_state.openai_model_value = localS.getItem("openai_model") or "gpt-4-turbo"
if "dynamic_params_from_node" not in st.session_state:
    st.session_state.dynamic_params_from_node = {}
if "rename_node_id" not in st.session_state:
    st.session_state.rename_node_id = None
if "expanded_nodes" not in st.session_state:
    st.session_state.expanded_nodes = set()
if "param_collapsed" not in st.session_state:
    st.session_state.param_collapsed = True
if "current_draft_id" not in st.session_state:
    st.session_state.current_draft_id = None
# ── 异步任务追踪 ─────────────────────────────────────────────────────────────
if "current_job_id" not in st.session_state:
    st.session_state.current_job_id = None
if "is_simulation_running" not in st.session_state:
    st.session_state.is_simulation_running = False
if "sim_status_msg" not in st.session_state:
    st.session_state.sim_status_msg = ""
if "last_autosaved_node_id" not in st.session_state:
    st.session_state.last_autosaved_node_id = None
if "last_autosaved_code" not in st.session_state:
    st.session_state.last_autosaved_code = ""
if "last_autosave_at" not in st.session_state:
    st.session_state.last_autosave_at = 0.0
if "autosave_status_msg" not in st.session_state:
    st.session_state.autosave_status_msg = ""


def autosave_current_code(force=False):
    node_id = st.session_state.get("selected_node_id")
    if not node_id:
        return False

    code = st.session_state.get("code_editor") or ""
    if (
        not force
        and st.session_state.last_autosaved_node_id == node_id
        and st.session_state.last_autosaved_code == code
    ):
        return False

    now = time.time()
    if not force and now - st.session_state.last_autosave_at < 1.5:
        return False

    try:
        resp = api_post(f"/history/{node_id}/code", {"code": code}, timeout=6)
        if resp.status_code == 200:
            st.session_state.last_autosaved_node_id = node_id
            st.session_state.last_autosaved_code = code
            st.session_state.last_autosave_at = now
            st.session_state.autosave_status_msg = f"已自动保存 {datetime.now().strftime('%H:%M:%S')}"
            invalidate_history_cache()
            return True
        st.session_state.autosave_status_msg = f"自动保存失败：HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        st.session_state.autosave_status_msg = f"自动保存失败：{e}"
    return False


def render_code_autosave_beacon():
    node_id = st.session_state.get("selected_node_id")
    if not node_id:
        return

    components.html(
        f"""
<script>
(function() {{
  const parentWindow = window.parent || window;
  parentWindow.__robotArmCodeAutosavePayload = {{
    recordId: {json.dumps(node_id)},
    backendBase: {json.dumps(BACKEND_PUBLIC_URL)},
    code: {json.dumps(st.session_state.get("code_editor") or "")}
  }};

  if (parentWindow.__robotArmCodeAutosaveInstalled) return;
  parentWindow.__robotArmCodeAutosaveInstalled = true;

  function saveCode() {{
    const latest = parentWindow.__robotArmCodeAutosavePayload || {{}};
    if (!latest.recordId || !latest.backendBase) return;

    const payload = JSON.stringify({{ code: latest.code || "" }});
    const url = `${{latest.backendBase}}/history/${{latest.recordId}}/code`;
    if (parentWindow.navigator && parentWindow.navigator.sendBeacon) {{
      const blob = new Blob([payload], {{ type: "application/json" }});
      parentWindow.navigator.sendBeacon(url, blob);
      return;
    }}
    parentWindow.fetch(url, {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: payload,
      keepalive: true
    }}).catch(function() {{}});
  }}

  parentWindow.addEventListener("beforeunload", saveCode);
  parentWindow.document.addEventListener("visibilitychange", function() {{
    if (parentWindow.document.visibilityState === "hidden") saveCode();
  }});
}})();
</script>
""",
        height=0,
        scrolling=False,
    )


def sync_api_settings_to_browser_storage(api_key: str, api_url: str, model: str):
    localS.setItem("openai_api_key", api_key or "", key="save_key")
    localS.setItem("openai_base_url", api_url or "", key="save_url")
    localS.setItem("openai_model", model or "", key="save_model")
    components.html(
        f"""
<script>
(function() {{
  const values = {{
    openai_api_key: {json.dumps(api_key or "")},
    openai_base_url: {json.dumps(api_url or "")},
    openai_model: {json.dumps(model or "")}
  }};
  for (const [key, value] of Object.entries(values)) {{
    if (value) {{
      window.parent.localStorage.setItem(key, value);
    }} else {{
      window.parent.localStorage.removeItem(key);
    }}
  }}
}})();
</script>
""",
        height=0,
        scrolling=False,
    )


# ── 将模拟结果写入 session_state（需在 _poll_job_status 前定义） ─────────────
def apply_simulation_response(data):
    st.session_state.run_result = data if isinstance(data, dict) else {}
    data = st.session_state.run_result
    nested_result = parse_json_field(data.get("result"), {})

    video_data = data.get("video") or nested_result.get("video")
    if video_data is not None:
        st.session_state.simulation_video = video_data

    updated_code = (
        data.get("generated_code")
        or data.get("code")
        or nested_result.get("generated_code")
        or nested_result.get("code")
    )
    if updated_code:
        st.session_state.code_editor = updated_code
        st.session_state.ace_editor_version += 1

    returned_node_id = data.get("node_id") or data.get("record_id") or nested_result.get("node_id")
    if returned_node_id:
        st.session_state.selected_node_id = returned_node_id
        # 模拟结束后写入的节点是已仿真的分支（非草稿），重置 draft 跟踪。
        st.session_state.current_draft_id = None
        invalidate_history_cache()


# ── 轮询后端：检查当前任务状态 ──────────────────────────────────────────────
def _poll_job_status():
    job_id = st.session_state.current_job_id
    if not job_id or not st.session_state.is_simulation_running:
        return

    try:
        resp = api_get(f"/status/{job_id}", timeout=15)
    except Exception:
        return

    if resp.status_code == 404:
        # 后端重启后 job 丢失
        st.session_state.is_simulation_running = False
        st.session_state.current_job_id = None
        st.session_state.sim_status_msg = "⚠️ 任务状态丢失（后端可能已重启）"
        return

    if resp.status_code != 200:
        return

    data = resp.json()
    status = data.get("status", "running")

    if status == "running":
        return  # 继续等待

    # 任务结束
    st.session_state.is_simulation_running = False
    st.session_state.current_job_id = None

    if status == "cancelled":
        st.session_state.sim_status_msg = "⚫ 模拟已取消"
        return

    result = data.get("result") or {}

    # 无论成功/失败都尝试同步可用的结果（视频、代码、日志），这样
    # "代码生成成功但视频为空" 之类的中间态也能看到数据。
    apply_simulation_response(result)

    if status == "done":
        st.session_state.sim_status_msg = "✅ 模拟完成"
    else:
        err = result.get("error", "未知错误")
        st.session_state.sim_status_msg = f"❌ 模拟失败：{err}"


def render_browser_job_status(job_id: str):
    """Use browser-side polling so Streamlit does not rerun the whole page every few seconds."""
    job_id_json = json.dumps(job_id)
    backend_public_url_json = json.dumps(BACKEND_PUBLIC_URL)
    components.html(
        f"""
<div id="job-status-card">
  <span class="dot"></span>
  <span id="job-status-text">模拟任务已启动...</span>
</div>
<script>
const jobId = {job_id_json};
const backendBase = {backend_public_url_json};
const textEl = document.getElementById("job-status-text");
const cardEl = document.getElementById("job-status-card");

async function pollJobStatus() {{
  if (!backendBase) {{
    textEl.textContent = "模拟正在后端运行，请点击下方“检查并加载结果”同步状态。";
    return;
  }}
  try {{
    const response = await fetch(`${{backendBase}}/status/${{jobId}}`, {{ cache: "no-store" }});
    if (response.status === 404) {{
      cardEl.className = "warning";
      textEl.textContent = "任务状态丢失，请点击下方按钮同步页面状态。";
      return;
    }}
    if (!response.ok) {{
      throw new Error(`HTTP ${{response.status}}`);
    }}

    const payload = await response.json();
    if (payload.status === "running") {{
      cardEl.className = "";
      textEl.textContent = "模拟运行中，正在自动检查状态...";
      window.setTimeout(pollJobStatus, 1000);
      return;
    }}

    function triggerStreamlitSync() {{
      const buttons = Array.from(window.parent.document.querySelectorAll("button"));
      const syncButton = buttons.find((button) => button.textContent.includes("手动检查并加载结果"));
      if (syncButton) {{
        syncButton.click();
        return true;
      }}
      return false;
    }}

    cardEl.className = payload.status === "done" ? "done" : "warning";
    textEl.textContent = "任务已结束，正在自动加载结果...";
    if (!triggerStreamlitSync()) {{
      textEl.textContent = "任务已结束，请点击下方按钮加载结果。";
    }}
  }} catch (error) {{
    cardEl.className = "warning";
    textEl.textContent = "自动检查暂时失败，稍后重试；也可点击下方按钮手动确认。";
    window.setTimeout(pollJobStatus, 2000);
  }}
}}

pollJobStatus();
</script>
<style>
body {{
  margin: 0;
  font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
}}
#job-status-card {{
  display: flex;
  align-items: center;
  gap: 8px;
  box-sizing: border-box;
  width: 100%;
  min-height: 42px;
  padding: 10px 12px;
  color: #24426f;
  background: #eef5ff;
  border: 1px solid #cfe2ff;
  border-radius: 8px;
  font-size: 14px;
}}
#job-status-card.done {{
  color: #0f5132;
  background: #d1e7dd;
  border-color: #badbcc;
}}
#job-status-card.warning {{
  color: #664d03;
  background: #fff3cd;
  border-color: #ffecb5;
}}
.dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.2s ease-in-out infinite;
}}
#job-status-card.done .dot,
#job-status-card.warning .dot {{
  animation: none;
}}
@keyframes pulse {{
  0%, 100% {{ opacity: .35; transform: scale(.9); }}
  50% {{ opacity: 1; transform: scale(1.15); }}
}}
</style>
""",
        height=48,
        scrolling=False,
    )


# 在渲染历史树和主区之前同步一次任务状态。
# 这样任务结束时，视频、代码、日志和新增历史能在本轮渲染中直接更新，
# 避免浏览器侧点击同步按钮后再触发一次全页 rerun 造成白屏闪烁。
if st.session_state.is_simulation_running:
    _poll_job_status()

tree_data = normalize_history_tree(get_history_tree())
ensure_default_expanded(tree_data)
node_map = flatten_nodes(tree_data)

if st.session_state.selected_node_id and st.session_state.selected_node_id in node_map:
    active_node = node_map[st.session_state.selected_node_id]
else:
    active_node = None

# ========== 左侧边栏：VS Code 文件树风格 ==========
with st.sidebar:
    st.markdown(
        '<span style="font-size:10px;font-weight:700;color:#888;letter-spacing:.08em">EXPLORER</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<span style="font-size:11px;font-weight:700;color:#666;letter-spacing:.04em">历史记录</span>',
        unsafe_allow_html=True,
    )
    history_search = st.text_input(
        "搜索历史记录",
        key="history_search",
        placeholder="搜索主条目名称",
        label_visibility="collapsed",
    )
    display_tree_data = filter_main_history_nodes(tree_data, history_search)

    if not display_tree_data:
        st.markdown('<p style="font-size:11px;color:#aaa;padding:4px 2px;margin:0">无记录</p>', unsafe_allow_html=True)
    else:
        render_tree_nodes(display_tree_data)

    # ── 当前节点操作工具栏 ──
    if active_node:
        aid = active_node["id"]
        root_id = find_main_root_id(aid, node_map)
        is_branch_node = bool(active_node.get("parent_id")) and root_id and root_id != aid
        st.markdown(
            f'<p style="font-size:10px;color:#aaa;margin:6px 2px 2px 2px">#{aid} · {node_display_name(active_node)}</p>',
            unsafe_allow_html=True,
        )
        if is_branch_node:
            if st.button("★ 标记最终并覆盖主条目", key="sb_mark_final", use_container_width=True):
                resp = api_post(f"/history/{aid}/mark-final", {"root_id": root_id})
                if resp.status_code == 200:
                    st.toast("已标记最终版并覆盖主条目代码")
                    invalidate_history_cache()
                    st.rerun()
                else:
                    st.error(f"标记失败: {resp.text}")
        else:
            ac1, ac2 = st.columns(2, gap="small")
            with ac1:
                if st.button("★ 设为最终", key="sb_final", use_container_width=True):
                    api_post("/history/finalize", {"node_id": aid})
                    invalidate_history_cache()
                    st.rerun()
            with ac2:
                if st.button("↑ 覆盖主干", key="sb_promote", use_container_width=True):
                    api_post(f"/history/{aid}/promote-main", {})
                    st.toast("已覆盖主干")
                    invalidate_history_cache()
                    st.rerun()

# ========== 主区 ==========
st.markdown('<span class="brand">机械臂代码生成与仿真</span>', unsafe_allow_html=True)

# ── 重命名反馈 ────────────────────────────────────────────────────────────
if st.session_state.get("_rename_error"):
    st.error(st.session_state.pop("_rename_error"))
if st.session_state.get("_rename_toast"):
    st.toast(st.session_state.pop("_rename_toast"))

# ── 模拟状态横幅 ─────────────────────────────────────────────────────────────
if st.session_state.is_simulation_running:
    render_browser_job_status(st.session_state.current_job_id)
    if st.button("手动检查并加载结果", key="sync_job_result"):
        _poll_job_status()
elif st.session_state.sim_status_msg:
    msg = st.session_state.sim_status_msg
    if msg.startswith("✅"):
        st.success(msg)
    elif msg.startswith("❌"):
        st.error(msg)
    elif msg.startswith("⚫"):
        st.info(msg)
    else:
        st.warning(msg)

center_col = st.container()

with center_col:
    st.markdown(
        "<div style='text-align:left;font-size:22px;font-weight:700;line-height:1.4;margin-bottom:0.4rem;'>机械臂可视化操作平台</div>",
        unsafe_allow_html=True,
    )
    with st.container(key="param_panel"):
        with st.container(key="param_header_row"):
            _hdr_title, _hdr_tools = st.columns([0.94, 0.06], vertical_alignment="center", gap="small")
            with _hdr_title:
                st.markdown(
                    "<span style='font-size:18px;font-weight:650;line-height:1;'>任务与参数</span>",
                    unsafe_allow_html=True,
                )
            with _hdr_tools:
                _hdr_gear, _hdr_arrow = st.columns([1, 1], gap="small", vertical_alignment="center")
                with _hdr_gear:
                    st.markdown('<div class="icon-btn">', unsafe_allow_html=True)
                    with st.popover("⚙", use_container_width=True):
                        api_key = st.text_input("API Key", type="password", key="openai_api_key_value")
                        api_url = st.text_input("API Base URL", key="openai_base_url_value")
                        if st.button("获取模型列表", use_container_width=True, key="pop_fetch_models"):
                            models, err = fetch_models(api_key, api_url)
                            if models:
                                st.session_state.available_models = models
                            else:
                                st.error(err or "获取失败")
                        if st.session_state.available_models:
                            if st.session_state.openai_model_value not in st.session_state.available_models:
                                st.session_state.openai_model_value = st.session_state.available_models[0]
                            model = st.selectbox(
                                "模型",
                                st.session_state.available_models,
                                key="openai_model_value",
                            )
                        else:
                            model = st.text_input("模型", key="openai_model_value")
                        sync_api_settings_to_browser_storage(api_key, api_url, model)
                    st.markdown("</div>", unsafe_allow_html=True)
                with _hdr_arrow:
                    st.markdown('<div class="icon-btn">', unsafe_allow_html=True)
                    arrow = "▸" if st.session_state.param_collapsed else "▾"
                    if st.button(arrow, key="toggle_param_collapse", use_container_width=True):
                        st.session_state.param_collapsed = not st.session_state.param_collapsed
                    st.markdown("</div>", unsafe_allow_html=True)

        dynamic_params = {}
        algos = get_available_algorithms()
        selected_algorithm = st.session_state.selected_algorithm
        if not algos:
            selected_algorithm = ""
            st.session_state.selected_algorithm = ""
        elif not selected_algorithm or selected_algorithm not in algos:
            selected_algorithm = algos[0]
            st.session_state.selected_algorithm = selected_algorithm
        if not st.session_state.param_collapsed:
            main_param_cols = st.columns(2, gap="small")
            with main_param_cols[0]:
                task_description = st.text_input("任务描述", value=st.session_state.task_description)
                st.session_state.task_description = task_description
            with main_param_cols[1]:
                selected_algorithm = st.selectbox(
                    "算法",
                    options=algos or [""],
                    key="selected_algorithm",
                )

            params_config = get_params_for_algorithm(selected_algorithm) or {}
            if params_config.get("params"):
                param_cols = st.columns(2, gap="small")
                for i, param in enumerate(params_config["params"]):
                    with param_cols[i % 2]:
                        default_v = st.session_state.dynamic_params_from_node.get(param["name"], param.get("default"))
                        param_key = f"dynamic_param_{selected_algorithm}_{param['name']}"
                        if param["type"] == "slider":
                            dynamic_params[param["name"]] = st.slider(
                                param["label"], param["min"], param["max"], value=default_v, key=param_key
                            )
                        else:
                            dynamic_params[param["name"]] = st.text_input(
                                param["label"], value=str(default_v), key=param_key
                            )

    action_cols = st.columns([1, 1, 1, 1])
    with action_cols[0]:
        run_button = st.button(
            "⏹ 停止模拟" if st.session_state.is_simulation_running else "▶ 运行模拟",
            use_container_width=True,
            type="primary",
        )
    with action_cols[1]:
        apply_button = st.button(
            "⏹ 停止" if st.session_state.is_simulation_running else "应用代码并模拟",
            use_container_width=True,
            disabled=st.session_state.is_simulation_running,
        )
    with action_cols[2]:
        new_draft_button = st.button("新建草稿", use_container_width=True)
    with action_cols[3]:
        save_draft_button = st.button("💾 保存草稿", use_container_width=True)

    mid_cols = st.columns([1, 1], gap="small")
    with mid_cols[0]:
        st.markdown("##### 视频")
        with st.container(border=True, key="video_panel"):
            video_data = st.session_state.simulation_video
            if st.session_state.is_simulation_running:
                st.markdown(
                    "<div style='height:400px;display:flex;align-items:center;justify-content:center;"
                    "font-size:14px;color:#888;'>⏳ 模拟运行中，完成后自动显示…</div>",
                    unsafe_allow_html=True,
                )
            elif video_data == "NO_VIDEO_SUPPORTED":
                st.caption("无视频（文本计划）")
                st.markdown("<div style='height:400px;'></div>", unsafe_allow_html=True)
            elif video_data == "E2E_NO_CODE_SUPPORTED":
                st.caption("无视频（端到端）")
                st.markdown("<div style='height:400px;'></div>", unsafe_allow_html=True)
            elif video_data:
                try:
                    components.html(
                        f"""<!DOCTYPE html>
<html>
<head>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: 100%; height: 100%;
    background: #f6f7f9;
    overflow: hidden;
  }}
  video {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #000;
    display: block;
  }}
</style>
</head>
<body>
  <video controls preload="metadata">
    <source src="data:video/mp4;base64,{video_data}" type="video/mp4" />
  </video>
</body>
</html>""",
                        height=400,
                        scrolling=False,
                    )
                except Exception:
                    st.warning("视频解析失败")
                    st.markdown("<div style='height:400px;'></div>", unsafe_allow_html=True)
            else:
                st.caption("暂无视频")
                st.markdown("<div style='height:400px;'></div>", unsafe_allow_html=True)

    with mid_cols[1]:
        st.markdown("##### 代码")
        edited_code = st_ace(
            value=st.session_state.code_editor or "",
            language="python",
            theme="github",
            height=440,
            key=f"ace_editor_{st.session_state.ace_editor_version}",
            wrap=True,
            auto_update=True,
        )
        if edited_code is not None:
            if edited_code != st.session_state.code_editor:
                st.session_state.code_editor = edited_code
                localS.setItem("current_code", edited_code, key="save_current_code")
                autosave_current_code(force=False)

        render_code_autosave_beacon()

with st.container(key="notes_section"):
    st.markdown("##### 备注（随当前选中节点）")
    notes_key = f"notes_box_{st.session_state.selected_node_id or 'none'}"
    notes_text = st.text_area(
        "notes",
        value=st.session_state.notes_input or "",
        height=100,
        key=notes_key,
        label_visibility="collapsed",
    )
    if st.button("保存备注"):
        if st.session_state.selected_node_id:
            save_notes(st.session_state.selected_node_id, notes_text)
            st.session_state.notes_input = notes_text
        else:
            st.warning("请先在左侧栏选择一条记录")

if st.session_state.run_result:
    with st.expander("运行日志", expanded=False):
        st.code(st.session_state.run_result.get("log", ""), language="log")


def get_global_api():
    return (
        st.session_state.get("openai_api_key_value") or "",
        st.session_state.get("openai_base_url_value") or "",
        st.session_state.get("openai_model_value") or "gpt-4-turbo",
    )


def _extract_error_text(resp):
    try:
        payload = resp.json()
        detail = payload.get("detail")
        if isinstance(detail, list):
            return "; ".join(str(item.get("msg", item)) for item in detail)
        if detail:
            return str(detail)
        return str(payload)
    except Exception:
        return resp.text


def _start_job(resp):
    """处理后端返回的 {job_id, status} 并更新 session state。"""
    if resp.status_code == 200:
        data = resp.json()
        job_id = data.get("job_id")
        if job_id:
            st.session_state.current_job_id = job_id
            st.session_state.is_simulation_running = True
            st.session_state.sim_status_msg = ""
            # 不清空代码：当前仍选中历史节点时，空编辑器会被自动保存回该节点。
            st.session_state.simulation_video = None
            st.session_state.run_result = {}
            st.rerun()
        else:
            st.error("后端未返回 job_id，请检查服务日志。")
    else:
        st.error(f"启动失败（{resp.status_code}）：{_extract_error_text(resp)}")


# ── 运行模拟按钮 ──────────────────────────────────────────────────────────────
if run_button:
    if st.session_state.is_simulation_running:
        # 当前正在运行 → 停止
        cancel_current_job()
        st.session_state.sim_status_msg = "⚫ 模拟已取消"
        st.rerun()
    else:
        if not selected_algorithm:
            st.warning("请先选择算法")
            st.stop()
        api_key, api_url, model = get_global_api()
        payload = {
            "task_description": st.session_state.task_description,
            "openai_api_key": api_key,
            "openai_base_url": api_url,
            "selected_model": model,
            "notes": notes_text,
            "base_record_id": st.session_state.selected_node_id,
        }
        payload.update(dynamic_params)
        try:
            resp = api_post(f"/run/{selected_algorithm}", payload, timeout=15)
            _start_job(resp)
        except requests.exceptions.RequestException as e:
            st.error(f"启动失败: {e}")

# ── 新建草稿按钮 ──────────────────────────────────────────────────────────────
# 行为：创建一个独立的、未模拟的草稿主条目，区别于"保存草稿"创建分支草稿。
if new_draft_button:
    if not selected_algorithm:
        st.warning("请先选择算法")
    else:
        try:
            next_name = api_get("/next_draft_id").json().get(
                "next_draft_name", f"草稿-{datetime.now().strftime('%H%M%S')}"
            )
            resp = api_post(
                "/history/draft",
                {
                    "algorithm": selected_algorithm,
                    "task_description": st.session_state.task_description or "",
                    "params": dynamic_params,
                    "code": "",
                    "notes": "",
                    "parent_id": None,
                    "experiment_name": next_name,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                st.session_state.current_draft_id = data["id"]
                st.session_state.selected_node_id = data["id"]
                st.session_state.code_editor = ""
                st.session_state.simulation_video = None
                st.session_state.run_result = {}
                st.session_state.notes_input = ""
                st.session_state.ace_editor_version += 1
                st.toast(f"已创建草稿主条目：{data.get('name', next_name)}")
                invalidate_history_cache()
                st.rerun()
            else:
                st.error(f"创建草稿主条目失败：{resp.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"新建草稿失败: {e}")

# ── 保存草稿按钮 ──────────────────────────────────────────────────────────────
# 行为：永远在当前选中节点所属的"主条目（root）"下创建一个新的分支草稿，
#      不再覆盖任何已有条目（包括草稿自身）。
if save_draft_button:
    if not selected_algorithm:
        st.warning("请先选择算法")
    elif not st.session_state.selected_node_id:
        st.warning("请先在左侧栏选择一个主条目")
    else:
        try:
            code_to_save = st.session_state.code_editor or ""
            parent_id = find_main_root_id(st.session_state.selected_node_id, node_map)
            if parent_id is None:
                st.warning("无法确定主条目，无法创建分支草稿")
            else:
                next_name = api_get(f"/next_draft_id?parent_id={parent_id}").json().get(
                    "next_draft_name", f"草稿-{datetime.now().strftime('%H%M%S')}"
                )
                resp = api_post(
                    "/history/branch",
                    {
                        "algorithm": selected_algorithm,
                        "task_description": st.session_state.task_description or "",
                        "params": dynamic_params,
                        "code": code_to_save,
                        "notes": notes_text,
                        "parent_id": parent_id,
                        "experiment_name": next_name,
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.current_draft_id = data["id"]
                    st.session_state.selected_node_id = data["id"]
                    st.toast(f"分支草稿已创建：{data.get('name', next_name)}")
                    invalidate_history_cache()
                    st.rerun()
                else:
                    st.error(f"创建分支草稿失败：{resp.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"保存草稿失败: {e}")

# ── 应用代码并模拟按钮 ────────────────────────────────────────────────────────
# 行为：永远将模拟结果写为"主条目下的新分支"，不再新建独立的主条目。
#      仅当工作台完全空（没有任何选中节点）时，才允许退化为创建新主条目。
if apply_button and not st.session_state.is_simulation_running:
    if not selected_algorithm:
        st.warning("请先选择算法")
        st.stop()
    api_key, api_url, model = get_global_api()
    main_root_id = find_main_root_id(st.session_state.selected_node_id, node_map)
    payload = {
        "code_to_run": st.session_state.code_editor,
        "openai_api_key": api_key,
        "openai_base_url": api_url,
        "selected_model": model,
        "create_new_record": True,
        "task_description": st.session_state.task_description,
        "algorithm": selected_algorithm,
        "base_record_id": st.session_state.selected_node_id,
        "parent_id": main_root_id,  # ← 关键：让后端把结果挂到主条目下
        "notes": notes_text,
    }
    payload.update(dynamic_params)
    try:
        resp = api_post(f"/apply_code/{selected_algorithm}", payload, timeout=15)
        _start_job(resp)
    except requests.exceptions.RequestException as e:
        st.error(f"启动失败: {e}")
