#!/usr/bin/env python3
"""
每日简报——实时行情抓取（东方财富免费接口）

用途：为每日股票简报提供【最新且带时间戳】的价格数据，替代新鲜度不可控的
网页搜索。覆盖 A 股与美股。

前置条件：
    运行环境的出网策略需放行 push2.eastmoney.com（HTTPS）。
    在被沙箱/代理拦截的环境中会返回 403，属预期——放行后即可用。

用法：
    python scripts/fetch_quotes.py            # 打印人类可读表格
    python scripts/fetch_quotes.py --json     # 输出 JSON，便于程序消费

字段说明：eastmoney push2 接口
    f43 现价, f169 涨跌额, f170 涨跌幅(%), f57 代码, f58 名称,
    f60 昨收, f59 价格精度(小数位), f86 更新时间戳(秒)
"""
import sys
import json
import time
import datetime as dt

try:
    import requests
except ImportError:
    sys.exit("需要 requests：pip install requests")

# 关注标的 -> 东方财富 secid
#   A股沪市 = 1.xxxxxx  A股深市 = 0.xxxxxx  纳斯达克 = 105.XXX  纽交所 = 106.XXX
WATCHLIST = [
    ("豪威集团/韦尔股份", "1.603501"),
    ("凯盛新材",          "0.301069"),
    ("Tesla 特斯拉",      "105.TSLA"),
    ("上汽集团",          "1.600104"),
    ("爱尔眼科",          "0.300015"),
    ("恒瑞医药",          "1.600276"),
    ("海螺水泥",          "1.600585"),
]

API = "https://push2.eastmoney.com/api/qt/stock/get"
FIELDS = "f43,f57,f58,f59,f60,f86,f169,f170"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


def fetch_one(secid: str, timeout: int = 15) -> dict:
    r = requests.get(
        API,
        params={"secid": secid, "fields": FIELDS},
        headers=HEADERS,
        timeout=timeout,
    )
    r.raise_for_status()
    data = (r.json() or {}).get("data")
    if not data or data.get("f43") in (None, "-"):
        raise ValueError("接口未返回有效价格（可能停牌/代码错误/接口变动）")

    dec = data.get("f59") or 2          # 小数位
    div = 10 ** dec
    price = data["f43"] / div
    prev = (data.get("f60") or 0) / div
    change = (data.get("f169") or 0) / div
    pct = (data.get("f170") or 0) / 100  # 涨跌幅按 百分比×100 返回
    ts = data.get("f86")
    asof = (
        dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        if ts else "未知"
    )
    return {
        "name": data.get("f58"),
        "code": data.get("f57"),
        "price": round(price, dec),
        "prev_close": round(prev, dec),
        "change": round(change, dec),
        "pct": round(pct, 2),
        "asof": asof,
    }


def main() -> int:
    as_json = "--json" in sys.argv
    results = []
    for label, secid in WATCHLIST:
        row = {"label": label, "secid": secid}
        try:
            row.update(fetch_one(secid))
            row["ok"] = True
        except Exception as e:  # 单只失败不影响整体
            row["ok"] = False
            row["error"] = str(e)
        results.append(row)
        time.sleep(0.3)  # 轻微限速，友好访问

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    fetched_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"实时行情（抓取时间 {fetched_at}，数据源：东方财富）")
    print("-" * 68)
    print(f"{'名称':<16}{'现价':>10}{'涨跌幅':>10}{'截至':>20}")
    print("-" * 68)
    for r in results:
        if r["ok"]:
            sign = "+" if r["pct"] >= 0 else ""
            print(f"{r['label']:<16}{r['price']:>10}{sign}{r['pct']:>8}%{r['asof']:>20}")
        else:
            print(f"{r['label']:<16}{'取数失败':>10}   {r['error']}")
    print("-" * 68)
    print("注：A股为交易时段/收盘价，美股为最新成交价；请以标注的“截至”时间为准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
