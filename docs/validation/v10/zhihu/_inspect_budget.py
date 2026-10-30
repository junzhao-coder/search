"""Read-only: inspect runtime_live2 budget ledger (no writes, no network)."""
import json
import sqlite3

DB = r"D:\桌面\two\docs\validation\v10\zhihu\runtime_live2\budget.sqlite3"
conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables", tables)
for row in conn.execute("SELECT * FROM budget"):
    data = dict(row)
    keys = [k for k in ("batch_id", "calls", "calls_max", "records", "locked",
                        "lock_reason", "lock_source", "polls") if k in data]
    print("budget", json.dumps({k: data[k] for k in keys}, ensure_ascii=False))
if "ledger" in tables:
    rows = [dict(r) for r in conn.execute("SELECT kind, detail FROM ledger ORDER BY rowid")]
    print("ledger_count", len(rows))
    for r in rows:
        print("ledger", r["kind"], str(r["detail"])[:160])
conn.close()
