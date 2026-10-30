"""B6-fix 隔离库探针：GET 导出零写 / POST record 写 1 行（D1 回归实测）。

使用系统临时目录的独立库与密钥，端口 5019；跑完删除密钥。
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

OUT = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b6-fix")
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b6fix-probe-"))
DB, SECRET = TMP / "workflow.sqlite3", TMP / "secret"
PORT = 5019
BASE = f"http://127.0.0.1:{PORT}"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")

EVIDENCE = {
    "selected_supply_id": "sup-mit-1", "supply_version": "v1",
    "supply_license_commercial": "yes", "supply_license_redistribute": "yes", "supply_license_resell": "yes",
    "sample_status": "verified", "sample_ref": "sample://check-1", "cost_minor": "500", "cost_known": "yes",
    "platform_evidence": "policy://xianyu/digital-goods", "copy_status": "final", "copy_version": "copy-v1",
    "selling_points": "覆盖求职全流程", "price_minor": "990",
    "delivery_note": "拍下后 1 小时内发链接", "aftersales_note": "7 天内答疑",
    "faq_json": json.dumps([{"q": "能否商用", "a": "见许可说明"}], ensure_ascii=False),
}


def start():
    env = dict(os.environ)
    env.update({"WORKBENCH_WORKFLOW_DB": str(DB), "WORKBENCH_SECRET_FILE": str(SECRET),
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    proc = subprocess.Popen([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(PORT), "--no-browser"],
                            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.3)
        try:
            with urllib.request.urlopen(BASE + "/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return proc
        except Exception:
            continue
    raise RuntimeError("server did not start")


def state() -> dict:
    sha = hashlib.sha256(DB.read_bytes()).hexdigest() if DB.exists() else None
    count = 0
    if DB.exists():
        conn = sqlite3.connect(DB)
        try:
            count = conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]
        except sqlite3.OperationalError:
            count = 0
        finally:
            conn.close()
    return {"export_rows": int(count), "db_sha256": sha}


def main() -> int:
    ev = {"port": PORT, "db": str(DB), "steps": []}
    proc = start()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        with opener.open(BASE + "/opportunities", timeout=10) as resp:
            html = resp.read().decode("utf-8", "replace")
        form = dict(re.findall(r'name="([^"]+)" value="([^"]*)"',
                               re.findall(r'<form method="post" action="/worksheet/new" class="pick">(.*?)</form>',
                                          html, re.S)[0]))
        body = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(BASE + "/worksheet/new", data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with opener.open(req, timeout=10) as resp:
            wid = resp.geturl().rsplit("/", 1)[-1].split("?")[0]
        ev["workorder_id"] = wid

        # 未就绪：GET 408/409 且零写
        before = state()
        try:
            opener.open(BASE + f"/worksheet/{wid}/export?format=md", timeout=10)
            status = 200
        except urllib.error.HTTPError as exc:
            status = exc.code
        ev["steps"].append({"step": "GET export (not ready)", "status": status, "before": before, "after": state()})

        # 补齐证据
        with opener.open(BASE + f"/worksheet/{wid}", timeout=10) as resp:
            detail = resp.read().decode("utf-8", "replace")
        csrf = re.search(r'name="csrf" value="([^"]+)"', detail).group(1)
        rev = sqlite3.connect(DB).execute("SELECT revision FROM workorder WHERE workorder_id=?", (wid,)).fetchone()[0]
        body = urllib.parse.urlencode({"csrf": csrf, "revision": str(rev), **EVIDENCE}).encode()
        req = urllib.request.Request(BASE + f"/worksheet/{wid}/evidence", data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with opener.open(req, timeout=10) as resp:
            resp.read()

        # 就绪：GET 导出 200 且零写
        before = state()
        with opener.open(BASE + f"/worksheet/{wid}/export?format=md", timeout=10) as resp:
            status = resp.status
            recorded = resp.headers.get("X-WB-Recorded")
            body_md = resp.read().decode("utf-8", "replace")
        after = state()
        ev["steps"].append({"step": "GET export (ready)", "status": status, "recorded_header": recorded,
                            "before": before, "after": after, "content_bytes": len(body_md),
                            "zero_write": before == after})

        # POST record：写 1 行
        before = state()
        body = urllib.parse.urlencode({"csrf": csrf, "format": "md"}).encode()
        req = urllib.request.Request(BASE + f"/worksheet/{wid}/export/record", data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with opener.open(req, timeout=10) as resp:
            status = resp.status
            recorded = resp.headers.get("X-WB-Recorded")
            resp.read()
        after = state()
        ev["steps"].append({"step": "POST export/record", "status": status, "recorded_header": recorded,
                            "before": before, "after": after,
                            "rows_added": after["export_rows"] - before["export_rows"]})
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok = (any(s["step"] == "GET export (ready)" and s.get("zero_write") for s in ev["steps"])
          and any(s["step"] == "POST export/record" and s.get("rows_added") == 1 for s in ev["steps"]))
    ev["verdict"] = {"get_zero_write": ok, "d1_fixed": ok}
    (OUT / "export_probe.json").write_bytes(json.dumps(ev, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps(ev, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
