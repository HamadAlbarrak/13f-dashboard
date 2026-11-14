"""Export the Q3 2026 13F universe datasets for the dashboard.
Pipeline: status.py (EDGAR submissions, 82 core CIKs) -> pull.py (13f-analyzer holdings parser, Q3+Q2 info tables)
-> analyze.py (implied prices, split + CUSIP-change adjustment, per-fund stats, holdings-based return)
-> aggregate.py (accumulation breadth, net flows, stock-picker consensus, OpenFIGI tickers) -> this file."""
import json, re, os

st = json.load(open("status.json"))
a = json.load(open("analysis.json"))
g = json.load(open("aggregate.json"))
tick = json.load(open("tickers.json"))
MANUAL = {"SEAGATE": "STX", "LINDE": "LIN", "TRANE": "TT", "GATES": "GTES", "ACCENTURE": "ACN", "MEDTRONIC": "MDT",
          "CHUBB": "CB", "EATON": "ETN", "AON": "AON", "JOHNSON CTLS": "JCI", "TE CONNECTIVITY": "TEL", "STERIS": "STE",
          "WILLIS TOWERS": "WTW", "ARCH CAP": "ACGL", "NXP": "NXPI", "FLEX": "FLEX", "GARMIN": "GRMN", "SPOTIFY": "SPOT",
          "CHECK POINT": "CHKP", "MARVELL": "MRVL", "APTIV": "APTV", "ALCON": "ALC", "CRH": "CRH", "FERGUSON": "FERG", "ROYAL CARIBBEAN": "RCL", "ASML": "ASML", "AXALTA": "AXTA", "LIBERTY GLOBAL": "LBTYK", "NEBIUS": "NBIS", "NORWEGIAN CRUISE": "NCLH", "SHARKNINJA": "SN", "TECHNIPFMC": "FTI", "ASTRAZENECA": "AZN", "JFROG": "FROG", "JOHNSON CONTROLS": "JCI", "NU HOLDINGS": "NU", "TEVA": "TEVA"}
GROUP = {"P": "Stock-picker", "G": "Index / AM giant", "Q": "Quant / multistrat"}
CODE = "".join(open(f).read() + "\n\n" for f in ("status.py", "pull.py", "analyze.py", "aggregate.py", "export.py"))

def tk(c, issuer=""):
    t = (tick.get(c) or "").replace("*", "")
    t = re.sub(r"(EUR|GBP)$", "", t) if len(t) > 4 else t
    if not t:
        up = issuer.upper()
        for k, v in MANUAL.items():
            if up.startswith(k): return v
    return t

def meta(extra):
    return [{"label": "Source", "value": "SEC EDGAR Form 13F-HR information tables, periods 2026-06-30 and 2026-09-30, pulled 14 Nov 2026"},
            *extra, {"label": "pipeline.py", "value": CODE, "type": "code", "lang": "python"}]

os.makedirs("out", exist_ok=True)
def dump(name, rows, extra):
    json.dump({"rows": rows, "meta": meta(extra)}, open(f"out/{name}.json", "w"))
    print(name, len(rows))

# 1 status of all 82
rows = []
for f in st:
    s = f["status"]
    if f["cik"] == 1374170 and s == "FILED":
        s = "TABLE"
    lab = {"FILED": "Filed", "NT": "NT - notice only", "NA": "NA - not yet filed", "TABLE": "Filed - holdings table blank"}[s]
    rows.append(dict(fund=f["label"], cik=f["cik"], group=GROUP[f["g"]], status=lab,
                     filed=(f.get("q3") or {}).get("filed", ""), latest_period=f.get("latest_period") or ""))
rows.sort(key=lambda r: (r["status"] != "Filed", r["status"], r["fund"]))
dump("status", rows, [{"label": "Rule", "value": "Filed = 13F-HR or 13F-HR/A with report date 2026-09-30. NT = only a 13F-NT notice. Norges Bank's Q3 filing has a 1-row placeholder table ($0) while its cover page states 1,490 entries / $1.011T."}])

# 2 funds
rows = []
for f in a["funds"]:
    rows.append(dict(fund=f["label"], group=GROUP[f["group"]], filed=f["filed"],
                     value_bn=round(f["aum3"] / 1e9, 2), value_chg_pct=round(f["aum_chg"], 1) if f["aum_chg"] is not None else None,
                     positions=f["n3"], top10_pct=round(f["top10"], 1), hhi=f["hhi"],
                     est_return_pct=round(f["ret"], 1) if f["ret"] is not None else None, return_coverage_pct=round(f["ret_cov"], 1),
                     turnover_pct=round(f["turnover"], 1), options_pct=round(f["opt_pct"], 1),
                     new=f["new"], added=f["add"], trimmed=f["trim"], exited=f["exit"]))
rows.sort(key=lambda r: -(r["est_return_pct"] if r["est_return_pct"] is not None else -999))
dump("funds", rows, [{"label": "Est. Q3 return", "value": "Return in Q3 of each fund's 30 Jun long-equity book held unchanged, priced at the median value/share across all filers at each quarter end, adjusted for splits. Excludes options, fees, intra-quarter trading. A replication estimate, not reported performance."},
                     {"label": "Turnover", "value": "Half the sum of |share change x Q3 price| over the average equity book."}])

# 3 accumulation
rows = []
for side, lst in (("Accumulated", g["acc_top"][:15]), ("Distributed", g["acc_bot"][:15])):
    for x in lst:
        rows.append(dict(side=side, ticker=tk(x["cusip"], x["issuer"]), issuer=x["issuer"], cusip=x["cusip"], funds_involved=x["n"],
                         holders_q3=x["holders"], new=x["new"], added=x["add"], trimmed=x["trim"], exited=x["exit"],
                         score=x["score"], net_flow_bn=round(x["net_usd"] / 1e9, 2)))
dump("accumulation", rows, [{"label": "Score", "value": "(new + added - trimmed - exited) / funds that held it in Q2 or Q3. Added/trimmed = share count up/down more than 10%. Only names with at least 15 funds involved and $25B+ held across filers. Names where 90%+ of funds moved the same way (spin-offs, listings, acquisitions, CUSIP changes) are excluded."}])

# 4 flows
rows = []
for side, lst in (("Net bought", g["net_buy"][:15]), ("Net sold", g["net_sell"][:15])):
    for x in lst:
        rows.append(dict(side=side, ticker=tk(x["cusip"], x["issuer"]), issuer=x["issuer"], cusip=x["cusip"],
                         net_flow_bn=round(x["net_usd"] / 1e9, 2), buyers=x["new"] + x["add"], sellers=x["trim"] + x["exit"]))
dump("flows", rows, [{"label": "Net flow", "value": "Sum over filers of (Q3 shares - Q2 shares) x Q3 implied price. Dominated by the index and asset-management giants; ETF lines are mostly index rebalancing."}])

# 5 consensus among stock-pickers
rows = [dict(ticker=tk(x["cusip"], x["issuer"]), issuer=x["issuer"], cusip=x["cusip"], pickers=x["n"],
             value_bn=round(x["usd"] / 1e9, 2), held_by="; ".join(x["funds"])) for x in g["consensus_p"][:15]]
dump("consensus", rows, [{"label": "Rule", "value": "Stock-pickers that filed Q3 holding the name at 1% or more of their 13F book (no options)."}])

# 6 stock-picker moves
rows = []
for m in g["pk_moves"]:
    rows.append(dict(fund=m["fund"], ticker=tk(m["cusip"], m["issuer"]), issuer=m["issuer"], move=m["kind"],
                     change_mn=round(m["d_usd"] / 1e6, 1), weight_q3_pct=round(m["w3"], 2),
                     shares_q2=int(m["s2"]), shares_q3=int(m["s3"]), key=f'{m["fund"]}|{m["cusip"]}'))
rows.sort(key=lambda r: -abs(r["change_mn"]))
dump("picker_moves", rows, [{"label": "Rule", "value": "Each stock-picker's 5 largest buys and 5 largest sells by share change x Q3 price."}])

# 7 top holdings per fund
rows = []
for f in a["funds"]:
    for i, t in enumerate(f["top"], 1):
        rows.append(dict(fund=f["label"], rank=i, ticker=tk(t["cusip"], t["issuer"]), issuer=t["issuer"] + (f" ({t['pc']})" if t["pc"] else ""),
                         weight_pct=round(t["w"], 2), value_bn=round(t["v"] / 1e9, 3), key=f'{f["label"]}|{i}'))
dump("top_holdings", rows, [{"label": "Rule", "value": "Top 10 lines of each Q3 13F book by value, options shown as separate lines."}])
