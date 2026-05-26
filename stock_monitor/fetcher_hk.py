"""从东方财富抓取港股公告数据（ann_type=H）"""
import time
import requests
from datetime import datetime, timedelta

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}


def _pad_code(code: str) -> str:
    """港股代码统一补全为5位，如 551 → 00551"""
    return code.strip().zfill(5)


def fetch_hk_announcements(code: str, days_back: int = 1) -> list:
    """获取指定港股最近 N 天内的相关公告"""
    today = datetime.now()

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
