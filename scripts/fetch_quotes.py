#!/usr/bin/env python3
"""
每日简报——实时行情抓取（新浪财经免费接口）

用途：为每日股票简报提供【最新且带时间戳】的价格数据，替代新鲜度不可控的
网页搜索。一次批量请求覆盖 A 股与美股。

前置条件：
    运行环境的出网策略需放行 hq.sinajs.cn（HTTPS）。
    新浪接口还要求带 Referer 头，脚本已内置。
    在被沙箱/代理拦截的环境中会返回 403，属预期——放行后即可用。

用法：
    python scripts/fetch_quotes.py            # 打印人类可读表格
    python scripts/fetch_quotes.py --json     # 输出 JSON，便于程序消费

接口返回示例：
    var hq_str_sh603501="韦尔股份,今开,昨收,现价,最高,最低,...,日期,时间,...";
    var hq_str_gb_tsla="TESLA,现价,涨跌幅,美东时间,涨跌额,开,高,低,...";
"""
import sys
import json
import datetime as dt

try:
    import requests
except ImportError:
    sys.exit("需要 requests：pip install requests")

# 关注标的 -> 新浪代码（沪市 shxxxxxx / 深市 szxxxxxx / 美股 gb_代码）
WATCHLIST = [
    ("豪威集团/韦尔股份", "sh603501"),
    ("凯盛新材",          "sz301069"),
    ("Tesla 特斯拉",      "gb_tsla"),
    ("上汽集团",          "sh600104"),
    ("爱尔眼科",          "sz300015"),
    ("恒瑞医药",          "sh600276"),
    ("海螺水泥",          "sh600585"),
]

API = "https://hq.sinajs.cn/list="
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://finance.sina.com.cn/",  # 新浪要求，否则 403
}


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_cn(label, code, fields):
    """A 股：现价=f[3] 昨收=f[2] 日期=f[30] 时间=f[31]"""
    price = _num(fields[3])
    prev = _num(fields[2])
    if not price:  # 0 或空 => 停牌/无数据
        raise ValueError("无有效价格（可能停牌）")
    pct = round((price - prev) / prev * 100, 2) if prev else None
    asof = f"{fields[30]} {fields[31]}" if len(fields) > 31 else "未知"
    return {
        "name": fields[0], "code": code, "price": round(price, 2),
        "prev_close": round(prev, 2) if prev else None,
        "change": round(price - prev, 2) if prev else None,
        "pct": pct, "asof": asof,
    }


def parse_us(label, code, fields):
    """美股：现价=f[1] 涨跌幅=f[2] 美东时间=f[3] 涨跌额=f[4]"""
    price = _num(fields[1])
    if not price:
        raise ValueError("无有效价格")
    pct = _num(fields[2])
    change = _num(fields[4]) if len(fields) > 4 else None
    prev = round(price - change, 2) if change is not None else None
    asof = fields[3] if len(fields) > 3 and fields[3] else "未知"
    return {
        "name": fields[0], "code": code, "price": round(price, 2),
        "prev_close": prev, "change": change,
        "pct": round(pct, 2) if pct is not None else None,
        "asof": asof + "（美东）",
    }


def fetch_all(timeout: int = 20) -> list:
    codes = ",".join(c for _, c in WATCHLIST)
    r = requests.get(API + codes, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    r.encoding = "gbk"  # 新浪返回 GBK 编码
    # 按代码建行 -> 原始字符串
    raw = {}
    for line in r.text.splitlines():
        if "hq_str_" not in line or '="' not in line:
            continue
        key = line.split("hq_str_", 1)[1].split("=", 1)[0]
        val = line.split('="', 1)[1].rstrip('";')
        raw[key] = val

    results = []
    for label, code in WATCHLIST:
        row = {"label": label, "code": code}
        try:
            s = raw.get(code, "")
            fields = s.split(",")
            if not s or len(fields) < 4:
                raise ValueError("接口未返回该代码数据")
            parsed = parse_us(label, code, fields) if code.startswith("gb_") \
                else parse_cn(label, code, fields)
            row.update(parsed)
            row["ok"] = True
        except Exception as e:  # 单只失败不影响整体
            row["ok"] = False
            row["error"] = str(e)
        results.append(row)
    return results


def main() -> int:
    as_json = "--json" in sys.argv
    try:
        results = fetch_all()
    except Exception as e:
        msg = f"批量取数失败：{e}"
        print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False)
              if as_json else msg)
        return 1

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    fetched_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"实时行情（抓取时间 {fetched_at}，数据源：新浪财经）")
    print("-" * 72)
    print(f"{'名称':<16}{'现价':>10}{'涨跌幅':>10}{'截至':>26}")
    print("-" * 72)
    for r in results:
        if r["ok"]:
            pct = r["pct"]
            sign = "+" if (pct or 0) >= 0 else ""
            pcts = f"{sign}{pct}%" if pct is not None else "  -"
            print(f"{r['label']:<16}{r['price']:>10}{pcts:>10}{r['asof']:>26}")
        else:
            print(f"{r['label']:<16}{'取数失败':>10}   {r['error']}")
    print("-" * 72)
    print("注：A股为交易时段/收盘价，美股为最新成交价；请以标注的“截至”时间为准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
