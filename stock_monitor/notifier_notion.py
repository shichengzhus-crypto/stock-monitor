"""将公告报告推送到 Notion 数据库"""
import requests
from collections import defaultdict

import config

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers():
    return {
        "Authorization": f"Bearer {config.NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _get_title_property_name() -> str:
    """查询数据库结构，找到标题属性的名称（中文 Notion 默认是"名称"）"""
    try:
        resp = requests.get(
            f"{NOTION_API}/databases/{config.NOTION_DATABASE_ID}",
            headers=_headers(), timeout=15,
        )
        if resp.status_code == 200:
            for name, prop in resp.json().get("properties", {}).items():
                if prop.get("type") == "title":
                    return name
    except Exception:
        pass
    return "名称"


# ── 构建 Notion 块的辅助函数 ──────────────────────────────────

def _heading2(text: str) -> dict:
    return {
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _heading3(text: str) -> dict:
    return {
        "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]},
    }


def _paragraph(text: str, bold: bool = False) -> dict:
    return {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": text[:2000]},
                "annotations": {"bold": bold},
            }]
        },
    }


def _link_paragraph(text: str, url: str) -> dict:
    return {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{
                "type": "text",
                "text": {"content": text, "link": {"url": url}},
            }]
        },
    }


def _divider() -> dict:
    return {"type": "divider", "divider": {}}


# ── 主函数 ────────────────────────────────────────────────────

def push_to_notion(announcements: list, date_str: str, date_range: str = ""):
    """把当日公告报告作为一个新页面写入 Notion 数据库"""
    if not config.NOTION_TOKEN:
        print("  [Notion] 未配置 NOTION_TOKEN，跳过推送")
        return
    if not config.NOTION_DATABASE_ID:
        print("  [Notion] 未配置 NOTION_DATABASE_ID，跳过推送")
        return

    # ── 组装页面正文块 ─────────────────────────────────────────
    blocks = []

    # 摘要行
    a_cnt  = len(config.STOCK_CODES)
    hk_cnt = len(config.HK_STOCK_CODES)
    us_cnt = len(config.US_STOCK_CODES)
    period = date_range or date_str
    blocks.append(_paragraph(
        f"📅 {period}　|　A股 {a_cnt} 只 | 港股 {hk_cnt} 只 | 美股 {us_cnt} 只，本期 {len(announcements)} 条相关公告",
        bold=True,
    ))
    blocks.append(_divider())

    if not announcements:
        blocks.append(_paragraph("今日自选股无重要公告。"))
    else:
        grouped = defaultdict(list)
        for ann in announcements:
            label = f"{ann['stock_name']}（{ann['stock_code']}）"
            grouped[label].append(ann)

        for stock_label, anns in grouped.items():
            blocks.append(_heading2(stock_label))
            for ann in anns:
                # 标题行：[类别] 标题（日期）加粗显示
                title_line = f"[{ann['category']}]  {ann['title']}（{ann['time']}）"
                summary = ann.get("summary", "").strip()
                url = ann.get("url", "")

                # 摘要 + 链接合并到一个段落
                rich_text = [
                    {"type": "text", "text": {"content": title_line[:2000]},
                     "annotations": {"bold": True}},
                ]
                blocks.append({
                    "type": "paragraph",
                    "paragraph": {"rich_text": rich_text},
                })

                if summary or url:
                    body_parts = []
                    if summary:
                        body_parts.append({
                            "type": "text",
                            "text": {"content": summary[:1800]},
                        })
                    if url:
                        body_parts.append({
                            "type": "text",
                            "text": {"content": "  查看原文→", "link": {"url": url}},
                        })
                    blocks.append({
                        "type": "paragraph",
                        "paragraph": {"rich_text": body_parts},
                    })

            # 公司之间才加分隔线
            blocks.append(_divider())

    # ── 创建页面（Notion 单次最多 100 个块）────────────────────
    title_prop = _get_title_property_name()
    page_title = f"自选股公告摘要 — {date_range or date_str}"

    first_batch = blocks[:100]
    extra_batches = [blocks[i: i + 100] for i in range(100, len(blocks), 100)]

    payload = {
        "parent": {"database_id": config.NOTION_DATABASE_ID},
        "properties": {
            title_prop: {
                "title": [{"type": "text", "text": {"content": page_title}}]
            }
        },
        "children": first_batch,
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/pages", headers=_headers(), json=payload, timeout=30,
        )
    except Exception as e:
        print(f"  [Notion] 网络错误: {e}")
        return

    if resp.status_code != 200:
        print(f"  [Notion] 创建页面失败 ({resp.status_code}): {resp.text[:300]}")
        return

    page_id  = resp.json()["id"]
    page_url = resp.json().get("url", "")

    # ── 追加超出 100 个的块 ────────────────────────────────────
    for batch in extra_batches:
        try:
            requests.patch(
                f"{NOTION_API}/blocks/{page_id}/children",
                headers=_headers(), json={"children": batch}, timeout=30,
            )
        except Exception as e:
            print(f"  [Notion] 追加内容失败: {e}")

    print(f"  [Notion] 报告已推送 → {page_url}")
