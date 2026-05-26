"""从东方财富（via akshare）抓取 A 股公告数据"""
import re
import time
import requests
from datetime import datetime, timedelta
from html.parser import HTMLParser

import akshare as ak

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
}


def fetch_announcements(code: str, days_back: int = 1) -> list:
    """获取指定股票最近 N 天内的相关公告"""
    today = datetime.now()

    end_date   = today.strftime("%Y%m%d")
    start_date = (today - timedelta(days=days_back)).strftime("%Y%m%d")

    try:
        df = ak.stock_individual_notice_report(
            security=code,
            symbol="全部",
            begin_date=start_date,
            end_date=end_date,
        )
    except KeyError:
        # akshare 已知问题：日期范围内无公告时返回空 DataFrame 却仍访问列，触发 KeyError
        return []
    except Exception as e:
        print(f"    [请求失败] {code}: {e}")
        return []

    results = []
    for _, row in df.iterrows():
        ann_type = str(row.get("公告类型", ""))
        results.append({
            "stock_code": str(row.get("代码", code)),
            "stock_name": str(row.get("名称", "")),
            "category":   ann_type,
            "title":      str(row.get("公告标题", "")).strip(),
            "time":       str(row.get("公告日期", "")),
            "url":        str(row.get("网址", "")),
        })
    return results



class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def try_get_announcement_text(url: str, max_chars: int = 6000) -> str:
    """获取公告正文：优先调用东方财富内容 API，拿不到再降级 HTML 解析"""
    if not url:
        return ""

    # 从 URL 提取 art_code：形如 .../detail/600887/AN202605211822643774.html
    m = re.search(r'/(AN\d+)\.html', url)
    if m:
        text = _fetch_via_content_api(m.group(1), max_chars)
        if text:
            return text

    # 降级：直接抓 HTML（对少数非标准页面兜底）
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200 and len(resp.text) > 500:
            extractor = _TextExtractor()
            extractor.feed(resp.text)
            text = "\n".join(extractor.parts)
            return text[:max_chars]
    except Exception:
        pass
    return ""


def _fetch_via_content_api(art_code: str, max_chars: int) -> str:
    """调用东方财富 np-cnotice API 获取公告 notice_content 正文"""
    try:
        resp = requests.get(
            "https://np-cnotice-stock.eastmoney.com/api/content/ann",
            params={"art_code": art_code, "client_source": "web"},
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return ""
        content = resp.json().get("data", {}).get("notice_content", "")
        if not content:
            return ""
        # 如果含 HTML 标签，先提取纯文字
        if "<" in content:
            extractor = _TextExtractor()
            extractor.feed(content)
            content = "\n".join(extractor.parts)
        return content[:max_chars]
    except Exception:
        return ""
