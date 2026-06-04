"""追踪止盈监控

逻辑：
1. 读取 watchlist.yaml（自选股配置）和 state.yaml（持久化状态）
2. 对每只标的拉取最新价（akshare）
3. 价格 < activate_at → 待机，仅记录
4. 价格 ≥ activate_at → 进入追踪态，更新峰值；止盈线 = 峰值 × (1 - trail_pct%)
5. 当前价 ≤ 止盈线 → 触发卖出邮件提醒（每日去重，避免重复发）
6. 可转债额外检查强赎区间（≥125 预警，≥130 警报）
7. 写入快照报告（Markdown）+ 更新 state.yaml

环境变量：
  GMAIL_ADDRESS         发件/收件邮箱（默认 shichengzhus@gmail.com）
  GMAIL_APP_PASSWORD    Gmail 应用专用密码（必需，否则只打印不发邮件）
"""
from __future__ import annotations

import os
import smtplib
import sys
import traceback
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak
import yaml

ROOT = Path(__file__).parent
WATCHLIST_FILE = ROOT / "watchlist.yaml"
STATE_FILE = ROOT / "state.yaml"
REPORT_DIR = ROOT / "reports"

DEFAULT_EMAIL = "shichengzhus@gmail.com"
BOND_FORCE_REDEEM_WARN = 125.0
BOND_FORCE_REDEEM_TRIGGER = 130.0


# ── 文件读写 ──────────────────────────────────────────────

def load_yaml(path: Path, default):
    if not path.exists():
        return default
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if data is not None else default


def save_yaml(path: Path, data):
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


# ── 行情获取 ──────────────────────────────────────────────

_stock_cache = None  # (source, df)
_bond_cache = None


def _stock_spot():
    """优先东方财富（快），失败回退新浪（稳）。返回 (source, df)。"""
    global _stock_cache
    if _stock_cache is not None:
        return _stock_cache
    try:
        df = ak.stock_zh_a_spot_em()
        _stock_cache = ("em", df)
        return _stock_cache
    except Exception as e:
        print(f"  [fetch] 东方财富不可用 ({e})，回退新浪…")
    try:
        df = ak.stock_zh_a_spot()
        _stock_cache = ("sina", df)
        return _stock_cache
    except Exception as e:
        print(f"  [fetch] 新浪也不可用 ({e})")
        _stock_cache = ("none", None)
        return _stock_cache


def _bond_spot():
    """优先东方财富，失败回退新浪。"""
    global _bond_cache
    if _bond_cache is not None:
        return _bond_cache
    try:
        df = ak.bond_zh_hs_cov_spot()  # 新浪源，稳定且包含全市场
        _bond_cache = ("sina", df)
        return _bond_cache
    except Exception as e:
        print(f"  [fetch] 转债行情获取失败: {e}")
        _bond_cache = ("none", None)
        return _bond_cache


def _extract_price_stock(df, source: str, code: str) -> float | None:
    """从股票行情表中按代码取最新价。"""
    if source == "em":
        # 东方财富：代码列 "代码"（6 位纯数字），价格列 "最新价"
        row = df[df["代码"].astype(str).str.zfill(6) == code]
        if row.empty:
            return None
        return float(row.iloc[0]["最新价"])
    if source == "sina":
        # 新浪：代码列 "代码"（含 sh/sz/bj 前缀），价格列 "最新价"
        row = df[df["代码"].astype(str).str.endswith(code)]
        if row.empty:
            return None
        return float(row.iloc[0]["最新价"])
    return None


def _extract_price_bond(df, source: str, code: str) -> float | None:
    """从转债行情表中按代码取最新价。"""
    # sina: code (6 位数字) + trade
    # em (备用): 代码 + 最新价
    if "code" in df.columns:
        row = df[df["code"].astype(str).str.zfill(6) == code]
        if row.empty:
            return None
        return float(row.iloc[0]["trade"])
    if "代码" in df.columns:
        row = df[df["代码"].astype(str).str.zfill(6) == code]
        if row.empty:
            return None
        return float(row.iloc[0]["最新价"])
    return None


def fetch_price(item: dict) -> float | None:
    code = str(item["code"]).zfill(6)
    kind = item.get("type", "stock")
    try:
        if kind == "bond":
            source, df = _bond_spot()
            if df is None:
                return None
            price = _extract_price_bond(df, source, code)
        else:
            source, df = _stock_spot()
            if df is None:
                return None
            price = _extract_price_stock(df, source, code)
        return price if (price is not None and price > 0) else None
    except Exception as e:
        print(f"  [ERROR] 获取 {code} 价格失败: {e}")
        return None


# ── 邮件 ──────────────────────────────────────────────────

def send_email(subject: str, body: str) -> bool:
    addr = os.environ.get("GMAIL_ADDRESS") or DEFAULT_EMAIL
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "")
    print(f"  [邮件] 尝试发送 → 收件人: {addr}, 主题: {subject}")
    if not pwd:
        print(f"  [邮件] 未配置 GMAIL_APP_PASSWORD，跳过发送")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = addr
    msg["To"] = addr
    msg.set_content(body)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
            s.set_debuglevel(1)  # 打印 SMTP 对话细节用于排查
            s.starttls()
            s.login(addr, pwd)
            s.send_message(msg)
        print(f"  [邮件] 已发送：{subject}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"  [邮件] 认证失败 ({subject}): {e}")
        print(f"  [邮件] 这通常意味着应用密码错误，或 Gmail 账号未开启两步验证")
        return False
    except Exception as e:
        print(f"  [邮件] 发送失败 ({subject}): {type(e).__name__}: {e}")
        return False


# ── 核心逻辑 ──────────────────────────────────────────────

def process_item(item: dict, state: dict, today: str, alerts: list, snapshot: list):
    code = str(item["code"]).zfill(6)
    name = item["name"]
    activate_at = float(item["activate_at"])
    trail_pct = float(item.get("trail_pct", 10))
    is_bond = item.get("type") == "bond"

    price = fetch_price(item)
    if price is None:
        print(f"[{code}] {name}: 价格获取失败，跳过")
        snapshot.append({
            "name": name, "code": code, "price": None,
            "cost": item.get("cost"),
            "peak": state.get(code, {}).get("peak"),
            "stop": state.get(code, {}).get("stop"),
            "status": "数据获取失败",
            "is_bond": is_bond,
        })
        return

    s = state.setdefault(code, {
        "peak": None,
        "stop": None,
        "activated": False,
        "last_sell_alert_date": None,
        "last_bond_alert": None,
    })

    # 启用追踪
    just_activated = False
    if not s["activated"] and price >= activate_at:
        s["activated"] = True
        s["peak"] = price
        just_activated = True
        alerts.append((
            f"[启用追踪] {name} @{price}",
            f"{name}({code}) 价格 {price} 已达启用线 {activate_at}，开始追踪止盈。\n"
            f"回撤阈值: {trail_pct}%\n"
            f"初始止盈线: {round(price * (1 - trail_pct/100), 2)}"
        ))

    status = "待机"
    if s["activated"]:
        # 更新峰值
        if s["peak"] is None or price > s["peak"]:
            s["peak"] = price
        s["stop"] = round(s["peak"] * (1 - trail_pct / 100), 2)

        if price <= s["stop"]:
            status = "[!] 触发止盈"
            # 同一天不重复发同一只股票的卖出邮件
            if s.get("last_sell_alert_date") != today:
                s["last_sell_alert_date"] = today
                drawdown = (s["peak"] - price) / s["peak"] * 100
                alerts.append((
                    f"[卖出提醒] {name} 触发止盈 @{price}",
                    f"{name}({code}) 当前价 {price} 已跌破止盈线 {s['stop']}\n\n"
                    f"  峰值价: {s['peak']}\n"
                    f"  止盈线: {s['stop']}（峰值 -{trail_pct}%）\n"
                    f"  当前回撤: {drawdown:.2f}%\n"
                    f"  触发时间: {datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')}"
                ))
        else:
            distance = (price - s["stop"]) / price * 100
            status = f"追踪中 (距止盈 {distance:.1f}%)"

    # 可转债强赎检查
    if is_bond:
        prev_alert = s.get("last_bond_alert")
        if price >= BOND_FORCE_REDEEM_TRIGGER and prev_alert != "trigger":
            s["last_bond_alert"] = "trigger"
            alerts.append((
                f"[强赎警报] {name} @{price}",
                f"{name}({code}) 当前价 {price} 已进入强赎触发区（≥{BOND_FORCE_REDEEM_TRIGGER}）。\n"
                f"提示：连续 15/30 个交易日触及该价位会被强制赎回，赎回价通常 100 元左右，建议尽快卖出或转股。\n"
                f"请关注公司公告。"
            ))
        elif BOND_FORCE_REDEEM_WARN <= price < BOND_FORCE_REDEEM_TRIGGER and prev_alert is None:
            s["last_bond_alert"] = "warn"
            alerts.append((
                f"[强赎预警] {name} 接近强赎线 @{price}",
                f"{name}({code}) 当前价 {price} 已进入强赎预警区（≥{BOND_FORCE_REDEEM_WARN}），距强赎触发区还差 {BOND_FORCE_REDEEM_TRIGGER - price:.2f} 元。\n"
                f"继续上涨请留意公司是否发布强赎公告。"
            ))
        elif price < BOND_FORCE_REDEEM_WARN and prev_alert is not None:
            # 跌回预警区下方时清空，便于下次再进入时再次提醒
            s["last_bond_alert"] = None

    if just_activated:
        status = "[*] 刚启用追踪"

    snapshot.append({
        "name": name, "code": code, "price": price,
        "cost": item.get("cost"),
        "peak": s.get("peak"), "stop": s.get("stop"),
        "activated": s["activated"],
        "status": status,
        "is_bond": is_bond,
    })
    print(f"[{code}] {name}: 当前={price} 峰值={s.get('peak')} 止盈={s.get('stop','-')} 状态={status}")


# ── 报告 ──────────────────────────────────────────────────

def write_report(snapshot: list, today: str, alerts: list):
    REPORT_DIR.mkdir(exist_ok=True)
    lines = []
    lines.append(f"# 追踪止盈日报 — {today}\n")
    lines.append(f"运行时间: {datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')} (Asia/Shanghai)\n")

    if alerts:
        lines.append(f"## 本次警报 ({len(alerts)} 条)\n")
        for subj, _ in alerts:
            lines.append(f"- {subj}")
        lines.append("")

    lines.append("## 持仓快照\n")
    lines.append("| 名称 | 代码 | 类型 | 成本 | 当前价 | 峰值 | 止盈线 | 状态 |")
    lines.append("|------|------|------|------|--------|------|--------|------|")
    for row in snapshot:
        kind = "转债" if row.get("is_bond") else "股票"
        price = row["price"] if row["price"] is not None else "-"
        peak = row["peak"] if row.get("peak") is not None else "-"
        stop = row["stop"] if row.get("stop") is not None else "-"
        cost = row.get("cost") if row.get("cost") is not None else "-"
        lines.append(f"| {row['name']} | {row['code']} | {kind} | {cost} | {price} | {peak} | {stop} | {row['status']} |")

    (REPORT_DIR / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    # 同时按日期归档一份
    (REPORT_DIR / f"snapshot_{today}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入: {REPORT_DIR / 'latest.md'}")


# ── 入口 ──────────────────────────────────────────────────

def main():
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    print(f"=== 追踪止盈监控 {today} ===\n")

    # 启动诊断：检查邮件凭证是否生效（只打印长度，不泄露值）
    pwd_env = os.environ.get("GMAIL_APP_PASSWORD", "")
    addr_env = os.environ.get("GMAIL_ADDRESS", DEFAULT_EMAIL)
    print(f"[诊断] GMAIL_ADDRESS = {addr_env}")
    print(f"[诊断] GMAIL_APP_PASSWORD 长度 = {len(pwd_env)} (期望 16)")
    if pwd_env:
        print(f"[诊断] 密码首位 = '{pwd_env[0]}' 末位 = '{pwd_env[-1]}'（用于核对是否截断）")
    print()

    watchlist = load_yaml(WATCHLIST_FILE, [])
    state = load_yaml(STATE_FILE, {})
    if not watchlist:
        print("watchlist.yaml 为空，退出。")
        return 0

    alerts: list[tuple[str, str]] = []
    snapshot: list[dict] = []

    for item in watchlist:
        try:
            process_item(item, state, today, alerts, snapshot)
        except Exception as e:
            print(f"[ERROR] 处理 {item.get('code')} 时异常: {e}")
            traceback.print_exc()

    write_report(snapshot, today, alerts)

    print(f"\n=== 警报数: {len(alerts)} ===")
    for subj, body in alerts:
        send_email(subj, body)

    save_yaml(STATE_FILE, state)
    print(f"状态已保存到 {STATE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
