import json, collections, time, urllib.request

a = json.load(open("analysis.json"))
funds, flows, iss = a["funds"], a["flows"], a["issuer"]
Q3 = "2026-09-30"

# accumulation: among funds that held in Q2 or Q3
import csv as _csv, glob as _glob
aggv = collections.Counter()
for _fn in _glob.glob("books/*_2026-09-30.csv"):
    for _r in _csv.DictReader(open(_fn)):
        if not _r["put_call"]: aggv[_r["cusip"]] += float(_r["value_usd"])
acc = []; corp = []
for c, f in flows.items():
    n = f["new"] + f["add"] + f["trim"] + f["exit"] + f["hold"]
    if n < 15 or aggv[c] < 25e9:
        continue
    score = (f["new"] + f["add"] - f["trim"] - f["exit"]) / n
    ca = "new" if f["new"] >= 0.9 * n else ("exit" if f["exit"] >= 0.9 * n else "")
    (corp if ca else acc).append(dict(cusip=c, issuer=iss.get(c, ""), n=n, holders=f["holders_q3"], new=f["new"], add=f["add"],
                    trim=f["trim"], exit=f["exit"], score=round(score * 100, 1), net_usd=f["net_usd"], aggv=aggv[c], ca=f["new"] >= 0.9 * n and "new" or (f["exit"] >= 0.9 * n and "exit" or "")))
acc_top = sorted(acc, key=lambda x: (-x["score"], -x["net_usd"]))[:25]
acc_bot = sorted(acc, key=lambda x: (x["score"], x["net_usd"]))[:25]
net_buy = sorted(acc, key=lambda x: -x["net_usd"])[:20]
net_sell = sorted(acc, key=lambda x: x["net_usd"])[:20]

# stock-picker consensus
P = [f for f in funds if f["group"] == "P"]
pk = collections.defaultdict(lambda: dict(n=0, usd=0.0, funds=[]))
import csv
for f in P:
    rows = [r for r in csv.DictReader(open(f"books/{f['cik']}_{Q3}.csv")) if not r["put_call"]]
    tot = sum(float(r["value_usd"]) for r in csv.DictReader(open(f"books/{f['cik']}_{Q3}.csv")))
    for r in rows:
        w = float(r["value_usd"]) / tot * 100
        if w >= 1.0:  # meaningful position
            d = pk[r["cusip"]]; d["n"] += 1; d["usd"] += float(r["value_usd"]); d["funds"].append(f"{f['label']} ({w:.1f}%)")
consensus_p = sorted(({"cusip": c, "issuer": iss.get(c, ""), **v} for c, v in pk.items()), key=lambda x: (-x["n"], -x["usd"]))[:20]

# all-fund top-10 frequency
t10 = collections.Counter()
for f in funds:
    for t in f["top"]:
        if not t["pc"]:
            t10[t["cusip"]] += 1
top10_freq = [dict(cusip=c, issuer=iss.get(c, ""), n=n) for c, n in t10.most_common(20)]

# stock-picker moves (P funds, notable size)
pk_moves = []
for f in P:
    for kind in ("buys", "sells"):
        for m in f[kind][:5]:
            pk_moves.append(dict(fund=f["label"], **m))

# collect cusips to map
need = set()
for lst in (acc_top, acc_bot, net_buy, net_sell, consensus_p, top10_freq, pk_moves):
    need |= {x["cusip"] for x in lst}
need |= {x["cusip"] for x in corp}
for f in funds:
    need |= {t["cusip"] for t in f["top"]} | {m["cusip"] for m in f["buys"]} | {m["cusip"] for m in f["sells"]}

try:
    tick = json.load(open("tickers.json"))
except FileNotFoundError:
    tick = {}
todo = [c for c in sorted(need) if c not in tick]
for i in range(0, len(todo), 10):
    chunk = todo[i:i + 10]
    body = json.dumps([{"idType": "ID_CUSIP", "idValue": c} for c in chunk]).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request("https://api.openfigi.com/v3/mapping", data=body, headers={"Content-Type": "application/json"})
            res = json.load(urllib.request.urlopen(req, timeout=30))
            break
        except Exception as e:
            time.sleep(20)
    else:
        continue
    for c, r in zip(chunk, res):
        d = r.get("data") or []
        us = [x for x in d if x.get("exchCode") == "US"] or d
        tick[c] = us[0]["ticker"] if us else ""
    json.dump(tick, open("tickers.json", "w"))
    time.sleep(2.6)

json.dump(dict(acc_top=acc_top, acc_bot=acc_bot, net_buy=net_buy, net_sell=net_sell, consensus_p=consensus_p,
               top10_freq=top10_freq, pk_moves=pk_moves, corp=sorted(corp, key=lambda x: -abs(x["net_usd"]))[:30]), open("aggregate.json", "w"))
print(len(need), "cusips;", sum(1 for c in need if tick.get(c)), "mapped")
for x in acc_top[:10]: print("ACC", tick.get(x["cusip"]), x["issuer"], x["score"], x["n"])
for x in acc_bot[:10]: print("DIS", tick.get(x["cusip"]), x["issuer"], x["score"], x["n"])
for x in consensus_p[:10]: print("CON", tick.get(x["cusip"]), x["issuer"], x["n"])
for x in net_buy[:8]: print("BUY$", tick.get(x["cusip"]), x["issuer"], round(x["net_usd"]/1e9, 2))
for x in net_sell[:8]: print("SELL$", tick.get(x["cusip"]), x["issuer"], round(x["net_usd"]/1e9, 2))
