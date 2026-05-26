"""从东方财富抓取港股公告数据（ann_type=H）"""
import time
import requests
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}

# 关注的公告类型关键词
RELEVANT_KEYWORDS = [
    # 业绩
    "年度业绩", "全年业绩", "末期业绩", "中期业绩", "季度业绩",
    "年报", "中期报告", "业绩公告", "盈利警告", "盈利喜讯",
    # 分红
    "股息", "派息", "分红", "末期息", "特别息", "中期息",
    # 重组并购
    "重组", "合并", "收购", "出售", "分拆", "私有化",
    # 融资
    "供股", "配售", "发行新股", "可换股",
    # 其他重要
    "内幕消息", "须予公告", "关连交易", "主要交易",
]


def _is_relevant(title: str) -> bool:
    return any(kw in title for kw in RELEVANT_KEYWORDS)


def _pad_code(code: str) -> str:
    """港股代码统一补全为5位，如 551 → 00551"""
    return code.strip().zfill(5)


def fetch_hk_announcements(code: str, days_back: int = 1) -> list:
    """获取指定港股最近 N 天内的相关公告"""
    today = datetime.now()
    if today.weekday() == 0:
        days_back = max(days_back, 3)
    elif today.weekday() == 6:
        days_back = max(days_back, 3)
    elif today.weekday() == 5:
        days_back = max(days_back, 2)

    padded = _pad_code(code)
    start_date = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    end_date   = today.strftime("%Y%m%d")

    results = []
    try:
        page = 1
        while True:
            resp = requests.get(
                "https://np-anotice-stock.eastmoney.com/api/security/ann",
                params={
                    "sr": -1, "page_index": page, "page_size": 50,
                    "ann_type": "H",
                    "client_source": "web", "f_node": 0, "s_node": 0,
                    "stock_list": padded,
                    "begin_time": start_date,
                    "end_time":   end_date,
                },
                headers=HEADERS,
                timeout=15,
            )
            data  = resp.json()
            items = data.get("data", {}).get("list") or []
            if not items:
                break

            for item in items:
                # 确认是目标股票的公告
                codes = item.get("codes", [])
                if codes and not any(c.get("stock_code", "") == padded for c in codes):
                    continue

                title = item.get("title", "").strip()
                if not _is_relevant(title):
                    continue

                # 获取股票名称
                stock_name = ""
                if codes:
                    stock_name = codes[0].get("short_name", "")

                notice_date = item.get("notice_date", "")
                if isinstance(notice_date, str):
                    notice_date = notice_date[:10]

                art_code = item.get("art_code", "")
                url = f"https://data.eastmoney.com/notices/detail/{padded}/{art_code}.html" if art_code else ""

                results.append({
                    "stock_code": padded,
                    "stock_name": stock_name or code,
                    "market":     "HK",
                    "category":   _guess_category(title),
                    "title":      title,
                    "time":       notice_date,
                    "url":        url,
                })

            total = data.get("data", {}).get("total_hits", 0)
            if page * 50 >= total:
                break
            page += 1

    except Exception as e:
        print(f"    [港股获取失败] {code}: {e}")

    return results


def _guess_category(title: str) -> str:
    """根据标题猜测公告大类"""
    if any(k in title for k in ["年度业绩", "全年业绩", "末期业绩", "年报"]):
        return "年度业绩"
    if any(k in title for k in ["中期业绩", "中期报告"]):
        return "中期业绩"
    if any(k in title for k in ["盈利警告"]):
        return "盈利警告"
    if any(k in title for k in ["股息", "派息", "分红", "末期息", "特别息"]):
        return "股息分派"
    if any(k in title for k in ["收购", "合并", "私有化", "分拆"]):
        return "收购重组"
    if any(k in title for k in ["供股", "配售", "发行新股"]):
        return "融资配股"
    if any(k in title for k in ["重组", "出售"]):
        return "重大交易"
    return "重要公告"
