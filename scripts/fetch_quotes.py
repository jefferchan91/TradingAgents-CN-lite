#!/usr/bin/env python3
"""
每日简报——实时行情抓取（新浪财经 + 东方财富 双源兜底）

用途：为每日股票简报提供【最新且带时间戳】的价格数据，替代新鲜度不可控的
网页搜索。一次批量请求覆盖 A 股与美股；单只取不到时自动切换备用源补齐。

取数策略：
    1) 优先：新浪财经 hq.sinajs.cn（单次批量请求，需 Referer 头）
    2) 兜底：东方财富 push2.eastmoney.com（对新浪缺失的标的逐只补取）
    两个源只要有一个放行且可用，就能拿到数据；都放行则冗余更稳。

前置条件（环境出网白名单，至少放行其一，建议都放行）：
    hq.sinajs.cn          # 主源
    push2.eastmoney.com   # 兜底源
    未放行的源会返回 403（属预期），脚本会自动尝试另一个源。

用法：
    python scripts/fetch_quotes.py            # 打印人类可读表格
    python scripts/fetch_quotes.py --json     # 输出 JSON，便于程序消费
"""
import sys
import json
import datetime as dt

try:
    import requests
except ImportError:
    sys.exit("需要 requests：pip install requests")

# (显示名, 新浪代码, 东财secid)
#   新浪：沪 shxxxxxx / 深 szxxxxxx / 美股 gb_代码
#   东财：沪 1.xxxxxx / 深 0.xxxxxx / 纳斯达克 105.XXX / 纽交所 106.XXX
WATCHLIST = [
    ("豪威集团/韦尔股份", "sh603501", "1.603501"),
    ("凯盛新材",          "sz301069", "0.301069"),
    ("Tesla 特斯拉",      "gb_tsla",  "105.TSLA"),
    ("上汽集团",          "sh600104", "1.600104"),
    ("爱尔眼科",          "sz300015", "0.300015"),
    ("恒瑞医药",          "sh600276", "1.600276"),
    ("海螺水泥",          "sh600585", "1.600585"),
]

SINA_API = "https://hq.sinajs.cn/list="
SINA_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}

EM_API = "https://push2.eastmoney.com/api/qt/stock/get"
EM_FIELDS = "f43,f57,f58,f59,f60,f86,f169,f170"
EM_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ---------- 新浪 ----------
def _sina_parse_cn(code, f):
    price, prev = _num(f[3]), _num(f[2])
    if not price:
        raise ValueError("无有效价格（可能停牌）")
    return {
        "name": f[0], "code": code, "price": round(price, 2),
        "prev_close": round(prev, 2) if prev else None,
        "change": round(price - prev, 2) if prev else None,
        "pct": round((price - prev) / prev * 100, 2) if prev else None,
        "asof": (f"{f[30]} {f[31]}" if len(f) > 31 else "未知"), "source": "新浪",
    }


def _sina_parse_us(code, f):
    price = _num(f[1])
    if not price:
        raise ValueError("无有效价格")
    change = _num(f[4]) if len(f) > 4 else None
    return {
        "name": f[0], "code": code, "price": round(price, 2),
        "prev_close": round(price - change, 2) if change is not None else None,
        "change": change, "pct": round(_num(f[2]), 2) if _num(f[2]) is not None else None,
        "asof": (f[3] + "（美东）" if len(f) > 3 and f[3] else "未知"), "source": "新浪",
    }


def fetch_sina(timeout: int = 20) -> dict:
    """一次批量取全部；返回 {sina_code: parsed}（失败的键缺省）。"""
    codes = ",".join(c for _, c, _ in WATCHLIST)
    r = requests.get(SINA_API + codes, headers=SINA_HEADERS, timeout=timeout)
    r.raise_for_status()
    r.encoding = "gbk"
    out = {}
    for line in r.text.splitlines():
        if "hq_str_" not in line or '="' not in line:
            continue
        key = line.split("hq_str_", 1)[1].split("=", 1)[0]
        val = line.split('="', 1)[1].rstrip('";')
        f = val.split(",")
        if not val or len(f) < 4:
            continue
        try:
            out[key] = _sina_parse_us(key, f) if key.startswith("gb_") \
                else _sina_parse_cn(key, f)
        except Exception:
            pass
    return out


# ---------- 东方财富 ----------
def fetch_em_one(secid: str, timeout: int = 15) -> dict:
    r = requests.get(EM_API, params={"secid": secid, "fields": EM_FIELDS},
                     headers=EM_HEADERS, timeout=timeout)
    r.raise_for_status()
    data = (r.json() or {}).get("data")
    if not data or data.get("f43") in (None, "-"):
        raise ValueError("无有效价格")
    dec = data.get("f59") or 2
    div = 10 ** dec
    ts = data.get("f86")
    return {
        "name": data.get("f58"), "code": data.get("f57"),
        "price": round(data["f43"] / div, dec),
        "prev_close": round((data.get("f60") or 0) / div, dec),
        "change": round((data.get("f169") or 0) / div, dec),
        "pct": round((data.get("f170") or 0) / 100, 2),
        "asof": (dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "未知"),
        "source": "东财",
    }


# ---------- 主流程 ----------
def collect() -> list:
    try:
        sina = fetch_sina()
    except Exception:
        sina = {}  # 新浪整体不可用（未放行/网络），全部走东财兜底

    results = []
    for label, sina_code, em_secid in WATCHLIST:
        row = {"label": label}
        got = sina.get(sina_code)
        if got:
            row.update(got); row["ok"] = True
        else:
            try:
                row.update(fetch_em_one(em_secid)); row["ok"] = True
            except Exception as e:
                row.update({"ok": False, "code": sina_code,
                            "error": f"新浪与东财均取数失败：{e}"})
        results.append(row)
    return results


def main() -> int:
    as_json = "--json" in sys.argv
    results = collect()

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if any(r["ok"] for r in results) else 1

    fetched_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"实时行情（抓取时间 {fetched_at}，主源新浪 / 兜底东财）")
    print("-" * 80)
    print(f"{'名称':<16}{'现价':>10}{'涨跌幅':>10}{'源':>6}{'截至':>26}")
    print("-" * 80)
    for r in results:
        if r["ok"]:
            pct = r.get("pct")
            sign = "+" if (pct or 0) >= 0 else ""
            pcts = f"{sign}{pct}%" if pct is not None else "  -"
            print(f"{r['label']:<16}{r['price']:>10}{pcts:>10}{r.get('source',''):>6}{r['asof']:>26}")
        else:
            print(f"{r['label']:<16}{'取数失败':>10}   {r['error']}")
    print("-" * 80)
    print("注：A股为交易时段/收盘价，美股为最新成交价；请以标注的“截至”时间为准。")
    return 0 if any(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
