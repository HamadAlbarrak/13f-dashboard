import sys, json, glob, os, io, contextlib, time
sys.path.insert(0, glob.glob("/root/.claude/skills/synced/*/13f-analyzer/scripts")[0])
import edgar_13f as E

os.makedirs("books", exist_ok=True)
st = json.load(open("status.json"))
log = open("pull.log", "a")
for f in st:
    if f["status"] != "FILED":
        continue
    done = glob.glob(f"books/{f['cik']}_2026-09-30.csv")
    if done:
        continue
    t = time.time()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            E.holdings(f["cik"], 2, "books")
        log.write(f"== {f['label']} ({time.time()-t:.0f}s)\n{buf.getvalue()}")
    except Exception as e:
        log.write(f"== {f['label']} ERROR {e}\n{buf.getvalue()}")
    log.flush()
print("done")
