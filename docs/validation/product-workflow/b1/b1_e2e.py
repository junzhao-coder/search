"""B1 端到端验证（隔离测试库）：URL 表单建单 → 列表 → 编辑 → 重启后仍在 → 幂等/冲突/越级/CSRF 拒绝。

不使用浏览器（urllib + cookie），浏览器截图由 shot_b1.py 负责。
所有写入都落在 docs/validation/product-workflow/b1/tmp 下的隔离库与密钥，不碰用户生产工作单。
"""

from __future__ import annotations

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

B1 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b1")
B1.mkdir(parents=True, exist_ok=True)
# 测试库与密钥都放在系统临时目录，跑完即清理；不动 tools/workbench/runtime/
TMP = pathlib.Path(tempfile.mkdtemp(prefix="b1-e2e-"))
DB = TMP / "workflow_e2e.sqlite3"
SECRET = TMP / "secret_e2e"
PORT = 5017
BASE = f"http://127.0.0.1:{PORT}"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")


def env() -> dict:
    e = dict(os.environ)
    e.update({"WORKBENCH_WORKFLOW_DB": str(DB), "WORKBENCH_SECRET_FILE": str(SECRET),
              "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    return e


def start() -> subprocess.Popen:
    proc = subprocess.Popen([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(PORT), "--no-browser"],
                            cwd=str(ROOT), env=env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.3)
        try:
            with urllib.request.urlopen(BASE + "/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return proc
        except Exception:
            continue
    raise RuntimeError("server did not start")


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


class Session:
    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path: str) -> tuple[int, str, str]:
        try:
            with self.opener.open(BASE + path, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8", "replace"), resp.geturl()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), exc.geturl()

    def post(self, path: str, data: dict, headers: dict | None = None) -> tuple[int, str, str]:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(BASE + path, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.status, resp.read().decode("utf-8", "replace"), resp.geturl()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), exc.geturl()


def db_snapshot() -> dict:
    if not DB.exists():
        return {}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM workorder").fetchall()
        return {"count": len(rows), "rows": [dict(r) for r in rows]}
    except sqlite3.OperationalError:
        return {"count": 0, "rows": []}
    finally:
        conn.close()


def pick_form(html: str, index: int = 0) -> dict:
    forms = re.findall(r'<form method="post" action="/worksheet/new" class="pick">(.*?)</form>', html, re.S)
    if not forms:
        raise AssertionError("no pick form on opportunities page")
    block = forms[index]
    inputs = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', block))
    return inputs


def main() -> int:
    ev: dict = {"port": PORT, "db": str(DB), "steps": []}
    if DB.exists():
        DB.unlink()
    proc = start()
    s = Session()
    try:
        status, opp, _ = s.get("/opportunities")
        ev["steps"].append({"step": "GET /opportunities", "status": status})
        form = pick_form(opp)
        ev["csrf_present"] = bool(form.get("csrf"))
        ev["pick"] = {k: ("***redacted***" if k == "csrf" else v) for k, v in form.items()}
        ev["credentials"] = "测试凭据已脱敏（csrf 不落盘）；测试密钥在系统临时目录，跑完即删；未触碰生产 runtime/secret_key"

        status, detail, url = s.post("/worksheet/new", form)
        ev["steps"].append({"step": "POST create", "status": status, "url": url})
        wid = url.rsplit("/", 1)[-1].split("?")[0]
        ev["workorder_id"] = wid
        after_create = db_snapshot()
        ev["db_after_create"] = {"count": after_create["count"],
                                "fields": {k: after_create["rows"][0][k] for k in
                                           ("workorder_id", "status", "selected_supply_id", "gate_demand",
                                            "gate_supply_distribution", "gate_cost", "gate_platform_policy",
                                            "revision", "name", "source_group", "source_item_id")}
                                if after_create.get("rows") else {}}

        # 幂等：同键同内容
        status, _body, url2 = s.post("/worksheet/new", form)
        ev["steps"].append({"step": "POST create duplicate", "status": status, "url": url2})
        ev["idempotent_count"] = db_snapshot()["count"]

        # 会话内 CSRF：从编辑页取 token
        status, edit_html, _ = s.get(f"/worksheet/{wid}/edit")
        csrf = re.search(r'name="csrf" value="([^"]+)"', edit_html).group(1)
        rev = re.search(r'name="revision" value="(\d+)"', edit_html).group(1)

        payload = {"csrf": csrf, "revision": rev, "name": "改名后的工作单", "use_case": "学习笔记整理",
                   "target_buyer": "学生", "deliverable": "Notion 页面模板", "fmt": "Notion",
                   "language": "中文", "version": "v2", "includes": "模板本体", "excludes": "不含素材",
                   "target_platform": "xianyu", "status": "in_review"}
        status, _b, url3 = s.post(f"/worksheet/{wid}/edit", payload)
        db_edit = db_snapshot()["rows"][0]
        ev["steps"].append({"step": "POST edit ok", "status": status, "url": url3})
        ev["db_after_edit"] = {k: db_edit[k] for k in ("name", "status", "revision")}

        status, stale_body, _ = s.post(f"/worksheet/{wid}/edit", {**payload, "revision": "1", "name": "过期改名"})
        db_stale = db_snapshot()["rows"][0]
        ev["steps"].append({"step": "POST stale revision", "status": status})
        ev["db_after_stale"] = {k: db_stale[k] for k in ("name", "revision")}

        status, _b2, _u = s.post(f"/worksheet/{wid}/edit", {**payload, "revision": str(db_stale["revision"]),
                                                            "status": "ready"})
        db_ready = db_snapshot()["rows"][0]
        ev["steps"].append({"step": "POST escalate status=ready", "status": status})
        ev["db_after_escalate"] = {"status": db_ready["status"], "revision": db_ready["revision"]}

        status, _b3, _u = s.post(f"/worksheet/{wid}/edit", {**payload, "revision": str(db_ready["revision"]),
                                                            "csrf": "wrong"})
        ev["steps"].append({"step": "POST bad csrf", "status": status})

        status, _b4, _u = s.post("/worksheet/new", {**form, "status": "verified"})
        ev["steps"].append({"step": "POST create status=verified", "status": status})
        ev["count_after_forgeries"] = db_snapshot()["count"]
    finally:
        stop(proc)

    # 重启后持久化
    proc = start()
    try:
        s2 = Session()
        status, body, _ = s2.get(f"/worksheet/{wid}")
        ev["steps"].append({"step": "after restart GET detail", "status": status,
                            "contains_name": "改名后的工作单" in body})
        status, listing, _ = s2.get("/worksheet")
        ev["after_restart"] = {"count": db_snapshot()["count"], "list_has_id": wid in listing}
    finally:
        stop(proc)

    (B1 / "e2e_evidence.json").write_bytes(json.dumps(ev, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()          # 清理测试密钥
    print(json.dumps({k: ev[k] for k in ("workorder_id", "idempotent_count", "count_after_forgeries",
                                         "after_restart", "csrf_present")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
