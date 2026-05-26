"""从 SEC EDGAR 抓取美股（外国私人发行人）公告数据"""
import requests
from datetime import datetime, timedelta

# SEC 要求 User-Agent 包含联系信息
HEADERS = {"User-Agent": "stock-monitor contact@example.com"}

# 关注的表格类型
RELEVANT_FORMS = {
    "20-F":  "年度报告",
    "6-K":   "重要公告",     # 等同于 A 股的临时公告
    "20-F/A":"年度报告修订",
    "6-K/A": "重要公告修订",
}


def fetch_us_announcements(cik: str, ticker: str, name: str, days_back: int = 1) -> list:
    """
    从 SEC EDGAR 获取指定公司最近 N 天的重要公告
    cik:    10位补零的CIK，如 "0001737806"
    ticker: 股票代码，如 "PDD"
    name:   公司名称
    """
    today = datetime.now()

    cutoff = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")

    results = []
    try:
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"    [美股获取失败] {ticker}: HTTP {resp.status_code}")
            return []

        data     = resp.json()
        filings  = data.get("filings", {}).get("recent", {})
        forms    = filings.get("form", [])
        dates    = filings.get("filingDate", [])
        accnos   = filings.get("accessionNumber", [])
        docs     = filings.get("primaryDocument", [])
        descs    = filings.get("primaryDocDescription", [])

        for form, date, accno, doc, desc in zip(forms, dates, accnos, docs, descs):
            if date < cutoff:
                break          # 已按时间倒序，可提前退出
            if form not in RELEVANT_FORMS:
                continue
            title = desc or doc or form

            # 构建 SEC 原文链接
            accno_clean = accno.replace("-", "")
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{int(cik)}/{accno_clean}/{doc}")

            results.append({
                "stock_code": ticker,
                "stock_name": name,
                "market":     "US",
                "category":   RELEVANT_FORMS[form],
                "title":      f"{ticker}: {title or form}",
                "time":       date,
                "url":        url,
            })

    except Exception as e:
        print(f"    [美股获取失败] {ticker}: {e}")

    return results
