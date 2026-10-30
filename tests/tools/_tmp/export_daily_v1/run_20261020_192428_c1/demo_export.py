import contextlib, importlib.util, io, json, pathlib, sys
run = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
from app import create_app
from tests.api import b2_helpers as b2
spec = importlib.util.spec_from_file_location("export_daily_tool", ROOT / "tools" / "export_daily.py")
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
db = run / "db" / "demo.db"
client = create_app({"db_path": str(db)}).test_client()
cid, sid = b2.seed_full(client, title="示例-导出演示")
b2.add_default_costs(client, cid, sid)
b2.verify_all_gates(client, cid, sid)
out = run / "reports"
as_of = "2026-10-20T12:00:00Z"
result = tool.export(db_path=str(db), as_of=as_of, limit=3, out_dir=str(out))
digest = result["digest"]
csv_path = out / f"daily-{digest['digest_date']}.csv"
lines = [
  "manual_export_ok json=%s csv=%s" % (result["json_path"].name, result["csv_path"].name),
  "as_of=%s digest_date=%s daily_limit=%s counts=%s" % (digest["as_of"], digest["digest_date"], digest["daily_limit"], json.dumps(digest["counts"], ensure_ascii=False)),
  "csv_rows=%d" % (len([x for x in csv_path.read_text(encoding="utf-8").splitlines() if x]) - 1),
  "kind=%s source=%s" % (digest["kind"], digest["source"]),
]
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
    code = tool.main(["--db", str(db), "--as-of", as_of, "--limit", "3", "--out-dir", str(run/"reports2")])
lines.append("cli_exit=%s stdout=%s" % (code, buf.getvalue().strip()))
rejects = []
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    for argv in (["--db", str(ROOT/"instance"/"app.db"), "--as-of", as_of, "--out-dir", str(run/"reports3")],
                 ["--db", str(db), "--as-of", "2026/10/20", "--out-dir", str(run/"reports3")]):
        rejects.append(tool.main(argv))
lines.append("reject_exits=%s instance_dir_created=%s" % (rejects, (run/"reports3").exists()))
(run / "20_manual_demo.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))
