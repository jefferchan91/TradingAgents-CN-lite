# 每日股票简报 · 自动化搭建指南

每晚美东 8:15 自动生成 7 只关注股票的【技术分析 + 最新新闻】简报，并存入 Gmail
草稿箱（你在草稿箱阅读，或一键发送）。本文档把整套方案的可复用资产集中在一处。

> 交付方式：**默认只存草稿箱**（最简、无需额外配置）。如果日后想让草稿每天
> **自动发送到收件箱**，再按可选的「附录·Apps Script」接上即可。

关注标的：豪威集团/韦尔股份(603501)、凯盛新材(301069)、Tesla(TSLA)、
上汽集团(600104)、爱尔眼科(300015)、恒瑞医药(600276)、海螺水泥(600585)。

---

## 架构总览

```
  ┌───────────────────────────┐     ┌────────────────┐   （可选）  ┌───────────┐
  │ claude.ai Routine          │     │  Gmail 草稿箱   │  Apps Script │  收件箱   │
  │ 每天 20:15 ET 触发          │ ──▶ │  排版好的简报   │ ┄┄┄┄┄┄┄▶ │  自动送达 │
  │ 取实时价→写简报→建 Gmail 草稿│     │ （读/一键发送） │            │           │
  └───────────────────────────┘     └────────────────┘            └───────────┘
```

Claude 的 Gmail 连接器**只能建草稿、不能发送**，所以默认交付即「存草稿箱」。
虚线部分（Apps Script 每天自动把草稿发出去）是**可选**的，见文末附录。

---

## 一、价格数据源（核心：保证“最新且有效”）

本环境的出网策略拦截了所有免费行情 API（Yahoo/新浪/东财/腾讯均 403），网页搜索
的 A 股价格新鲜度不可控。要保证价格最新有效，二选一（或都配）：

### 方案 A（推荐）：升级 FMP，作为价格/指标主源
- 将 FMP 订阅升到 **Starter 或以上**。
- 在 claude.ai 建 Routine 时**勾选 FMP 连接器**。
- Routine 用 `quote`（现价/涨跌幅）与 `technicalIndicators`（RSI、20/50/200 日均线）
  取权威数据；A 股在美东晚间已收盘，取到的即当日有效收盘价。

### 方案 B（免费）：放行行情域名 + 本仓库脚本（双源兜底）
- `scripts/fetch_quotes.py` 采用**双源**：优先新浪财经批量取数，单只缺失时自动
  切换东方财富补齐。两个源只要有一个放行且可用即有数据。
- 在环境网络策略里放行（至少其一，建议都放行以获得冗余）：
  - **`hq.sinajs.cn`** — 主源（新浪，单次批量覆盖 A 股 + 美股）
  - **`push2.eastmoney.com`** — 兜底源（东财，逐只补取）
- Routine 里执行 `python scripts/fetch_quotes.py --json` 即可，带时间戳与来源标注。
- 未放行的源返回 403 属预期，脚本会自动尝试另一个源。

> 两种都可作为主源；WebSearch 仅用于**新闻**与价格**兜底**。

---

## 二、Routine 提示词（在 claude.ai UI 新建 Routine，整段粘贴）

- 每天运行，时间 **8:15 PM（America/New_York）**；若界面按 UTC 存储，夏令时=
  `00:15 UTC`，冬令时（11 月初起）改 `01:15 UTC`。
- **必须勾选连接器：Gmail**（建草稿）+ **FMP**（若走方案 A）。

```
你是金融简报助手。为以下 7 只股票生成中文简报（技术分析 + 最新可靠新闻），
并用 Gmail 在 jefferchan91@gmail.com 名下创建一封 HTML 邮件草稿（只建草稿即可）。

标的与代码：豪威集团/韦尔股份 603501.SS、凯盛新材 301069.SZ、Tesla TSLA、
上汽集团 600104.SS、爱尔眼科 300015.SZ、恒瑞医药 600276.SS、海螺水泥 600585.SS

步骤：
1. 【最新价格 · 按优先级依次尝试，越靠前越可靠】
   a) FMP（若已勾选 FMP 连接器）：quote(现价/涨跌幅)、technicalIndicators(RSI14、
      SMA20/50/200)、chart(近60日日线)。
   b) 仓库脚本：若存在则运行 `python scripts/fetch_quotes.py --json`（新浪+东财双源）。
   c) 若上面都拿不到，直接内联抓新浪财经实时行情（需已放行 hq.sinajs.cn），
      在 Bash 里运行下面命令并解析输出（A股 现价=第4字段、昨收=第3字段、
      日期/时间=第31/32字段；美股 gb_ 现价=第2字段、涨跌幅=第3字段、时间=第4字段）：
      python3 - <<'PY'
      import requests
      codes="sh603501,sz301069,gb_tsla,sh600104,sz300015,sh600276,sh600585"
      r=requests.get("https://hq.sinajs.cn/list="+codes,
        headers={"User-Agent":"Mozilla/5.0","Referer":"https://finance.sina.com.cn/"},
        timeout=20); r.encoding="gbk"; print(r.text)
      PY
   d) 以上全部失败，才用 WebSearch 取价，并严格执行下方【价格数据规则】。
2. 每只股票用 WebSearch（有 FMP 时叠加 FMP news）取过去 1-3 天最新可靠新闻 2-4 条，
   优先权威财媒/公司公告/券商研报，附来源与日期，注意甄别可靠性。
3. 整理为结构清晰的中文 HTML：顶部日期标题 + 一句话市场速览 + 价格数据口径说明；
   每股一节含【技术分析】【最新新闻】；用表格展示 现价/涨跌幅/RSI/均线状态；
   结尾免责声明「本简报由 AI 自动生成，仅供参考，不构成投资建议」。
4. 用 Gmail 创建草稿发往 jefferchan91@gmail.com，主题「每日股票简报 — YYYY-MM-DD」
   （美东日期）。只需创建草稿，无需发送。

【价格数据规则 · 必须严格执行】
1. 价格优先级：FMP > 新浪/东财实时接口 > WebSearch。能用前者绝不用搜索价。
2. 每个价格必须紧跟“截至 YYYY-MM-DD HH:MM（数据源）”，如
   “101.27 元（截至 2026-08-01 15:00，新浪）”。
3. 仅能从 WebSearch 取到价格时，必须两次不同来源交叉核对，取最新一条并注明日期。
4. 若某价格距当前已超过 1 个交易日，必须在其后标注“⚠️数据滞后 N 天，非最新”，
   绝不可把旧价当现价陈述。
5. 技术指标仅在有足够历史数据时给数值，否则只做定性趋势描述并注明“指标数据不足”。
6. A 股在美东晚间已收盘，取当日收盘价即可；某项数据缺失标注“数据暂不可用”，
   不要中断整份简报。
```

---

## 附录（可选）、Google Apps Script（把草稿自动发到收件箱）

> **默认方案只存草稿箱，本节非必需。** 仅当你希望草稿每天自动发送、直达收件箱时，
> 再做这一步。不装的话，你就在 Gmail 草稿箱里阅读或手动点发送。

1. 打开 [script.google.com](https://script.google.com) → 新建项目，粘贴并保存：

```javascript
function sendDailyBriefDraft() {
  var MARKER = '每日股票简报';                 // 只发主题以此开头的草稿
  var tz = Session.getScriptTimeZone();
  var today = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
  var drafts = GmailApp.getDrafts();
  var target = null, newest = 0;

  for (var i = 0; i < drafts.length; i++) {
    var msg = drafts[i].getMessage();
    var subj = msg.getSubject() || '';
    if (subj.indexOf(MARKER) === 0) {
      var t = msg.getDate().getTime();
      if (t > newest) { newest = t; target = drafts[i]; }
    }
  }
  if (!target) { Logger.log('未找到匹配草稿'); return; }

  // 仅发送“今天”的草稿，避免 Routine 当天失败时误发旧简报
  var draftDay = Utilities.formatDate(target.getMessage().getDate(), tz, 'yyyy-MM-dd');
  if (draftDay !== today) { Logger.log('最新草稿非今日(' + draftDay + ')，跳过'); return; }

  target.send();
  Logger.log('已发送：' + target.getMessage().getSubject());
}
```

2. 项目设置 → 时区设为 **America/New_York**。
3. 触发器 → 新增：函数 `sendDailyBriefDraft`，时间驱动 → 按日计时器 →
   选 **20:00–21:00** 时段（在 Routine 生成草稿之后）。首次保存会要求授权 Gmail。

---

## 四、时区与维护提醒

- Cron/触发器按 UTC 或所设时区执行，**无法自动适配夏令时**。11 月初美东转冬令时后，
  若 Routine 用 UTC 存储需把 `00:15` 改为 `01:15`；Apps Script 若已设 America/New_York
  则自动跟随，无需改。
- 增删标的：改 Routine 提示词里的代码清单，以及 `scripts/fetch_quotes.py` 的 `WATCHLIST`。

---

## 五、本地测试行情脚本

```bash
python scripts/fetch_quotes.py          # 表格
python scripts/fetch_quotes.py --json   # JSON
```
在两个行情域名(`hq.sinajs.cn` / `push2.eastmoney.com`)都未放行的环境中返回取数失败属正常。
