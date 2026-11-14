import sys, json, glob
sys.path.insert(0, glob.glob("/root/.claude/skills/synced/*/13f-analyzer/scripts")[0])
import edgar_13f as E

funds = []
for item in open("funds.txt").read().split(";"):
    item = item.strip()
    if not item:
        continue
    lab, rest = item.rsplit("=", 1)
    funds.append(dict(label=lab, cik=int(rest[:-1]), g=rest[-1]))

out = []
for f in funds:
    try:
        js = E.get(f"https://data.sec.gov/submissions/CIK{f['cik']:010d}.json")
        r = js["filings"]["recent"]
        rows = [dict(form=a, acc=b, filed=c, period=d) for a, b, c, d in
                zip(r["form"], r["accessionNumber"], r["filingDate"], r["reportDate"]) if a.startswith("13F")]
        f["name"] = js.get("name")
        f["rows"] = rows
    except Exception as e:
        try:
            js = E.get(f"https://data.sec.gov/submissions/CIK{f['cik']:010d}.json")
            r = js["filings"]["recent"]
            f["rows"] = [dict(form=a, acc=b, filed=c, period=d) for a, b, c, d in
                         zip(r["form"], r["accessionNumber"], r["filingDate"], r["reportDate"]) if a.startswith("13F")]
            f["name"] = js.get("name")
        except Exception as e2:
            f["err"] = str(e2)
    out.append(f)

def pick(rows, period):
    hr = [x for x in rows if x["period"] == period and x["form"] in ("13F-HR", "13F-HR/A")]
    if not hr:
        return None
    # prefer latest filed (amendments) -- but amendments may be partial; keep both, choose original 13F-HR unless only /A
    orig = [x for x in hr if x["form"] == "13F-HR"]
    return (orig or hr)[0], hr

for f in out:
    if "err" in f:
        f["status"] = "ERR"; continue
    q3 = pick(f["rows"], "2026-09-30")
    q2 = pick(f["rows"], "2026-06-30")
    nt = [x for x in f["rows"] if x["period"] == "2026-09-30" and x["form"].startswith("13F-NT")]
    if q3:
        f["status"] = "FILED"; f["q3"] = q3[0]; f["q3_all"] = q3[1]
    elif nt:
        f["status"] = "NT"; f["q3"] = nt[0]
    else:
        f["status"] = "NA"
    f["q2"] = q2[0] if q2 else None
    latest = next((x for x in f["rows"] if x["form"] in ("13F-HR", "13F-HR/A")), None)
    f["latest_period"] = latest["period"] if latest else None

json.dump(out, open("status.json", "w"), indent=1)
from collections import Counter
print(Counter(f["status"] for f in out))
for s in ("FILED", "NT", "NA", "ERR"):
    print(s, [f["label"] for f in out if f["status"] == s])
