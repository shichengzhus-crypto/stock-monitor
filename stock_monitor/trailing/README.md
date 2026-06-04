# 追踪止盈监控 (Trailing Stop Monitor)

每个交易日收盘后自动检查自选股是否触发追踪止盈条件，触发时发邮件提醒。

## 工作原理

```
峰值 = max(历史最高价)          ← 价格创新高就更新，否则不变
止盈线 = 峰值 × (1 - trail_pct%)  ← 永远只上移，不下调
当 当前价 ≤ 止盈线 → 发邮件提醒卖出
```

价格未达到 `activate_at` 之前不启用追踪（避免在低位被噪声触发）。

## 文件说明

| 文件 | 用途 |
|---|---|
| `watchlist.yaml` | 自选股配置（人工维护） |
| `state.yaml` | 持久化状态：每只股的峰值、止盈线、是否已激活、上次警报日期（自动维护，每次运行后由 GitHub Actions 自动 commit） |
| `monitor.py` | 主脚本 |
| `reports/latest.md` | 最新一次运行的快照报告（覆盖式） |
| `reports/snapshot_YYYY-MM-DD.md` | 按日归档报告 |

## 修改自选股

编辑 `watchlist.yaml`，每只标的需要：

```yaml
- code: "600690"        # 6 位代码（注意加引号，避免 000xxx 前导零丢失）
  name: 海尔智家
  type: stock           # stock 或 bond
  cost: 24              # 你的买入成本（仅用于展示）
  activate_at: 30       # 价格涨到此值才开始追踪
  trail_pct: 10         # 从峰值回撤多少 % 触发提醒
```

**删除一只股票时**：从 `watchlist.yaml` 删除条目，并手动从 `state.yaml` 删掉对应的 code 键。

## 可转债强赎提醒

对 `type: bond` 的标的额外做：
- 价格 ≥ 125：发"接近强赎线"预警邮件（一次性）
- 价格 ≥ 130：发"强赎触发区"警报邮件（一次性）
- 价格跌回 125 以下：重置预警状态，下次再进入会再次提醒

> 严格的强赎触发要求"15/30 个交易日满足条件"，本工具用价格阈值做近似，作为关注信号即可，最终以公司公告为准。

## 配置 GitHub Secrets

在仓库 → Settings → Secrets and variables → Actions 添加：

| Secret 名称 | 值 | 必需 |
|---|---|---|
| `GMAIL_APP_PASSWORD` | Gmail 应用专用密码（16 位，无空格） | ✅ |
| `GMAIL_ADDRESS` | 收件邮箱（缺省用 shichengzhus@gmail.com） | 可选 |

Gmail 应用专用密码获取：
1. 账号需开启两步验证
2. 访问 https://myaccount.google.com/apppasswords 创建一个名为 "stock-monitor" 的密码
3. 粘贴到 GitHub Secret，去掉空格连成一个字符串

## 调度时间

`.github/workflows/trailing_stop.yml`：

```yaml
- cron: '30 7 * * 1-5'    # 北京时间周一至周五 15:30（A股收盘后）
```

GitHub Actions 的 cron 可能有 5-15 分钟延迟，属正常。

## 本地手动跑一次

```powershell
cd stock_monitor\trailing
pip install -r ..\requirements.txt
$env:GMAIL_APP_PASSWORD = "你的应用密码"     # 不设置则只打印不发邮件
python monitor.py
```

不设置 `GMAIL_APP_PASSWORD` 时脚本仍会运行并打印警报内容，方便调试。

## 触发首次运行

代码 push 之后，去 GitHub 仓库 → Actions → "trailing-stop-monitor" → Run workflow，手动跑一次验证。

## 添加新股票后

下一次运行会自动添加到 `state.yaml`，无需任何手工操作。
