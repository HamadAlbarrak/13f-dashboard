import csv, json, glob, statistics, collections, math

Q3, Q2 = "2026-09-30", "2026-06-30"
st = json.load(open("status.json"))
EXCLUDE_BOOK = {1374170: "Norges Bank filed a placeholder information table (1 row, $0); cover page reports 1,490 entries / $1.011T with confidential treatment requested"}

def load(cik, p):
    fn = f"books/{cik}_{p}.csv"
    try:
        rows = list(csv.DictReader(open(fn)))
    except FileNotFoundError:
        return None
    for r in rows:
        r["value_usd"] = float(r["value_usd"]); r["shares"] = float(r["shares"])
    return rows

books = {}
for f in st:
    if f["status"] != "FILED" or f["cik"] in EXCLUDE_BOOK:
        continue
    q3 = load(f["cik"], Q3); q2 = load(f["cik"], Q2)
    books[f["cik"]] = dict(meta=f, q3=q3, q2=q2)

def eq(rows):  # long equity common rows (SH, no options)
    return {r["cusip"]: r for r in rows if r["sh_prn"] == "SH" and not r["put_call"] and r["shares"] > 0}

# --- identifier changes (re-domiciles, holdco reorgs): exit in old CUSIP + new in new CUSIP, same funds, similar value
def _eqv(rows): return {r["cusip"]: r for r in rows if r["sh_prn"] == "SH" and not r["put_call"] and r["shares"] > 0}
exits = collections.defaultdict(dict); news = collections.defaultdict(dict)
for cik, b in books.items():
    if not b["q2"]: continue
    e3_, e2_ = _eqv(b["q3"]), _eqv(b["q2"])
    for c in set(e2_) - set(e3_): exits[c][cik] = e2_[c]
    for c in set(e3_) - set(e2_): news[c][cik] = e3_[c]
import re as _re
def _key(cusip, rowmap):
    n = next(iter(rowmap.values()))["issuer"].upper()
    n = _re.sub(r"[^A-Z]", "", _re.sub(r"^THE ", "", n))
    return n[:5]
remap = {}
cand_new = {c: v for c, v in news.items() if len(v) >= 3}
for old, ev in exits.items():
    if len(ev) < 3: continue
    best = None
    for new, nv in cand_new.items():
        if _key(old, ev) != _key(new, nv): continue
        common = set(ev) & set(nv)
        if len(common) < 0.6 * len(ev): continue
        ok = [k for k in common if 0.5 < nv[k]["value_usd"] / max(ev[k]["value_usd"], 1) < 2.0]
        if len(ok) >= 0.6 * len(ev):
            ratios_ = sorted(nv[k]["shares"] / ev[k]["shares"] for k in ok)
            med = ratios_[len(ratios_) // 2]
            tight = sum(abs(x / med - 1) < 0.03 for x in ratios_) / len(ratios_)
            if tight >= 0.0 and (best is None or len(ok) > best[1]):
                best = (new, len(ok), med)
    if best: remap[old] = (best[0], best[2])
for cik, b in books.items():
    for r in b["q2"] or []:
        if r["cusip"] in remap and r["sh_prn"] == "SH" and not r["put_call"]:
            new, ratio = remap[r["cusip"]]
            r["old_cusip"] = r["cusip"]; r["cusip"] = new; r["shares"] *= ratio
json.dump({k: v for k, v in remap.items()}, open("remap.json", "w"))

# implied prices: median value/shares across filers, per cusip, per quarter
px = {Q3: collections.defaultdict(list), Q2: collections.defaultdict(list)}
for b in books.values():
    for p, rows in ((Q3, b["q3"]), (Q2, b["q2"])):
        if not rows: continue
        for c, r in eq(rows).items():
            if r["value_usd"] > 0:
                px[p][c].append(r["value_usd"] / r["shares"])
price = {p: {c: statistics.median(v) for c, v in d.items()} for p, d in px.items()}

# split detection: median share ratio s3/s2 across funds holding in both quarters
ratios = collections.defaultdict(list)
for b in books.values():
    if not b["q2"]: continue
    e3_, e2_ = eq(b["q3"]), eq(b["q2"])
    for c in set(e3_) & set(e2_):
        ratios[c].append(e3_[c]["shares"] / e2_[c]["shares"])
split = {}
for c, v in ratios.items():
    if len(v) < 3 or c not in price[Q3] or c not in price[Q2]: continue
    sr = statistics.median(v); pr = price[Q3][c] / price[Q2][c]
    for k in (2, 3, 4, 5, 6, 8, 10, 20, 1/2, 1/3, 1/4, 1/5, 1/8, 1/10, 1/20, 1/25, 1/50):
        tight = sum(abs(r / k - 1) < 0.15 for r in v) / len(v)
        if abs(sr / k - 1) < 0.12 and tight >= 0.5 and 0.6 < pr * k < 1.6:
            split[c] = k; break
json.dump(split, open("splits.json", "w"))

issuer = {}
for b in books.values():
    for rows in (b["q3"], b["q2"]):
        for r in rows or []:
            issuer.setdefault(r["cusip"], r["issuer"])

funds = []
flows = collections.defaultdict(lambda: dict(new=0, add=0, trim=0, exit=0, hold=0, holders_q3=0, net_usd=0.0,
                                             grp=collections.Counter(), pk_new=0, pk_add=0, pk_trim=0, pk_exit=0))
for cik, b in books.items():
    m = b["meta"]; q3 = b["q3"]; q2 = b["q2"] or []
    tot3 = sum(r["value_usd"] for r in q3); tot2 = sum(r["value_usd"] for r in q2)
    e3, e2 = eq(q3), eq(q2)
    eqtot3 = sum(r["value_usd"] for r in e3.values())
    w = sorted((r["value_usd"] / tot3 for r in q3), reverse=True) if tot3 else []
    hhi = sum((x * 100) ** 2 for x in w)
    opt3 = sum(r["value_usd"] for r in q3 if r["put_call"])
    # holdings-based Q3 return of the Q2 equity book
    num = den = 0.0
    for c, r in e2.items():
        if c in price[Q3] and c in price[Q2] and price[Q2][c] > 0:
            ret = price[Q3][c] * split.get(c, 1) / price[Q2][c] - 1
            if abs(ret) > 3: continue  # guard against split/unit mismatch
            num += r["value_usd"] * ret; den += r["value_usd"]
    tot2eq = sum(r["value_usd"] for r in e2.values())
    ret = num / den if den else None
    cov = den / tot2eq if tot2eq else 0
    # changes
    moves = []
    for c in set(e3) | set(e2):
        s3 = e3[c]["shares"] if c in e3 else 0; s2 = (e2[c]["shares"] if c in e2 else 0) * split.get(c, 1)
        p3 = price[Q3].get(c) or price[Q2].get(c) or 0
        d_usd = (s3 - s2) * p3
        if s2 == 0: kind = "new"
        elif s3 == 0: kind = "exit"
        elif s3 > s2 * 1.10: kind = "add"
        elif s3 < s2 * 0.90: kind = "trim"
        else: kind = "hold"
        moves.append(dict(cusip=c, issuer=issuer.get(c, ""), kind=kind, s2=s2, s3=s3, d_usd=d_usd,
                          w3=(e3[c]["value_usd"] / tot3 * 100 if c in e3 and tot3 else 0)))
        fl = flows[c]
        fl[kind] += 1; fl["net_usd"] += d_usd
        if c in e3: fl["holders_q3"] += 1; fl["grp"][m["g"]] += 1
        if m["g"] == "P" and kind != "hold": fl["pk_" + kind] += 1
    traded = sum(abs(x["d_usd"]) for x in moves)
    turnover = traded / 2 / ((eqtot3 + tot2eq) / 2) * 100 if (eqtot3 + tot2eq) else 0
    top = sorted(q3, key=lambda r: -r["value_usd"])[:10]
    funds.append(dict(
        cik=cik, label=m["label"], name=m.get("name"), group=m["g"], filed=m["q3"]["filed"], acc=m["q3"]["acc"],
        aum3=tot3, aum2=tot2, aum_chg=(tot3 / tot2 - 1) * 100 if tot2 else None,
        n3=len(q3), n2=len(q2), top10=sum(w[:10]) * 100, hhi=round(hhi), opt_pct=opt3 / tot3 * 100 if tot3 else 0,
        ret=ret * 100 if ret is not None else None, ret_cov=cov * 100, turnover=turnover,
        new=sum(x["kind"] == "new" for x in moves), add=sum(x["kind"] == "add" for x in moves),
        trim=sum(x["kind"] == "trim" for x in moves), exit=sum(x["kind"] == "exit" for x in moves),
        top=[dict(issuer=r["issuer"], cusip=r["cusip"], pc=r["put_call"], v=r["value_usd"], w=r["value_usd"] / tot3 * 100) for r in top],
        buys=sorted([x for x in moves if x["d_usd"] > 0], key=lambda x: -x["d_usd"])[:8],
        sells=sorted([x for x in moves if x["d_usd"] < 0], key=lambda x: x["d_usd"])[:8],
    ))

json.dump(dict(funds=funds, flows={c: dict(v, grp=dict(v["grp"])) for c, v in flows.items()},
               issuer=issuer, split=split, price={p: dict(d) for p, d in price.items()}),
          open("analysis.json", "w"))
for f in sorted(funds, key=lambda f: -(f["ret"] or -999)):
    print(f"{f['label'][:28]:28} {f['group']} ret {f['ret'] if f['ret'] is None else round(f['ret'],1):>6} cov {f['ret_cov']:5.1f}% top10 {f['top10']:5.1f} n {f['n3']}")
