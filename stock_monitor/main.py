"""A股自选股公告监控主程序"""
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from collections import defaultdict
from datetime import datetime

import config
from fetcher          import fetch_announcements, try_get_announcement_text
from fetcher_hk       import fetch_hk_announcements
from fetcher_us       import fetch_us_announcements
from analyzer         import analyze
from notifier_notion  import push_to_notion


def run():
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*54}")
    print(f"  自选股公告监控  {today_str}")
    print(f"  A股 {len(config.STOCK_CODES)} 只 | 港股 {len(config.HK_STOCK_CODES)} 只 | 美股 {len(config.US_STOCK_CODES)} 只")
    print(f"{'='*54}\n")

    if not config.DEEPSEEK_API_KEY:
        print("⚠  未检测到 DEEPSEEK_API_KEY。")
        print("   本地运行：在 config.py 中直接填写 Key")
        print("   GitHub Actions：在仓库 Secrets 中添加 DEEPSEEK_API_KEY\n")
        sys.exit(1)

    all_announcements = []

    for code in config.STOCK_CODES:
        print(f"▶ {code}", end="  ", flush=True)

        announcements = fetch_announcements(code, config.DAYS_BACK)
        if not announcements:
            print("近期无相关公告")
            continue

        name = announcements[0]["stock_name"] if announcements else code
        print(f"{name}  →  找到 {len(announcements)} 条，分析中...")

        for ann in announcements:
            content = try_get_announcement_text(ann["url"])
            ann["summary"] = analyze(ann["title"], ann["category"], content)
            all_announcements.append(ann)
            time.sleep(0.3)

        print()
        time.sleep(0.5)

    # ── 港股 ──────────────────────────────────────────
    print("\n[ 港股 ]")
    for code in config.HK_STOCK_CODES:
        print(f"▶ {code.zfill(5)}", end="  ", flush=True)
        announcements = fetch_hk_announcements(code, config.DAYS_BACK)
        if not announcements:
            print("近期无相关公告")
            continue
        name = announcements[0]["stock_name"]
        print(f"{name}  →  找到 {len(announcements)} 条，分析中...")
        for ann in announcements:
            content = try_get_announcement_text(ann["url"])
            ann["summary"] = analyze(ann["title"], ann["category"], content)
            all_announcements.append(ann)
            time.sleep(0.3)
        print()
        time.sleep(0.5)

    # ── 美股 ──────────────────────────────────────────
    print("\n[ 美股 ]")
    for stock in config.US_STOCK_CODES:
        print(f"▶ {stock['ticker']}", end="  ", flush=True)
        announcements = fetch_us_announcements(
            stock["cik"], stock["ticker"], stock["name"], config.DAYS_BACK
        )
        if not announcements:
            print("近期无相关公告")
            continue
        print(f"{stock['name']}  →  找到 {len(announcements)} 条，分析中...")
        for ann in announcements:
            content = try_get_announcement_text(ann["url"])
            ann["summary"] = analyze(ann["title"], ann["category"], content)
            all_announcements.append(ann)
            time.sleep(0.3)
        print()
        time.sleep(0.5)

    _write_report(all_announcements, today_str)

    # 推送到 Notion
    print("\n正在推送到 Notion...")
    push_to_notion(all_announcements, today_str)


def _write_report(announcements: list, date_str: str):
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    path = os.path.join(config.REPORT_DIR, f"report_{date_str}.md")

    total = len(config.STOCK_CODES) + len(config.HK_STOCK_CODES) + len(config.US_STOCK_CODES)
    lines = [
        f"# 自选股公告摘要 — {date_str}\n",
        f"> A股 {len(config.STOCK_CODES)} 只 | 港股 {len(config.HK_STOCK_CODES)} 只 | 美股 {len(config.US_STOCK_CODES)} 只，本期 **{len(announcements)}** 条相关公告\n",
        "---\n",
    ]

    if not announcements:
        lines.append("**今日自选股无重要公告。**\n")
    else:
        grouped = defaultdict(list)
        for ann in announcements:
            grouped[f"{ann['stock_name']}（{ann['stock_code']}）"].append(ann)

        for stock_label, anns in grouped.items():
            lines.append(f"## {stock_label}\n")
            for ann in anns:
                lines.append(f"### [{ann['category']}] {ann['title']}")
                lines.append(f"*{ann['time']}*\n")
                lines.append(f"{ann['summary']}\n")
                if ann["url"]:
                    lines.append(f"[查看原文]({ann['url']})\n")
                lines.append("---\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 终端摘要
    print(f"\n{'='*54}")
    print(f"报告已保存：{path}")
    print(f"{'='*54}")
    if announcements:
        for ann in announcements:
            print(f"\n[{ann['stock_name']}] [{ann['category']}]")
            print(f"  标题：{ann['title']}")
            summary_preview = ann["summary"][:120].replace("\n", " ")
            print(f"  摘要：{summary_preview}…")
    else:
        print("今日无相关公告。")
    print()


if __name__ == "__main__":
    run()
