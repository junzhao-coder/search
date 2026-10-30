"""D1：synthetic 单从选品走到复盘的全链路走查 + 守卫实测（隔离库、真实 HTTP、每步落 JSON）。

只读产品代码，不改它；所有写操作都在系统临时库。失败只记录实际值，不修改断言。
"""

from __future__ import annotations

import csv
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

D1 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\d1")
LOGS = D1 / "logs"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="d1-walk-"))
DB, SECRET = TMP / "w.db", TMP / "s"
PORT, BASE = 5025, "http://127.0.0.1:5025"
PY = pathlib.Path(r"D:\桌面\two\.venv\Scripts\python.exe")
ROOT = pathlib.Path(r"D:\桌面\two")
SAMPLE = "docs/validation/product-workflow/b7/sample-study-planner-v1.xlsx"
NAME = "[SYNTHETIC] D1 学习计划模板"
steps: list[dict] = []
guards: list[dict] = []


def rec(step: str, ok: bool | None, **extra) -> None:
    steps.append({"step": step, "ok": ok, **extra})
    print(json.dumps({"step": step, "ok": ok, **{k: v for k, v in extra.items() if k in ("status", "note")}},
                     ensure_ascii=True))


def guard(name: str, ok: bool, **extra) -> None:
    guards.append({"guard": name, "ok": ok, **extra})
    print(json.dumps({"guard": name, "ok": ok, **{k: v for k, v in extra.items() if k in ("status", "actual")}},
                     ensure_ascii=True))


def start() -> subprocess.Popen:
    env = dict(os.environ)
    env.update({"WORKBENCH_WORKFLOW_DB": str(DB), "WORKBENCH_SECRET_FILE": str(SECRET),
                "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    p = subprocess.Popen([str(PY), "-X", "utf8", "tools/workbench/run.py", "--port", str(PORT), "--no-browser"],
                         cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        time.sleep(0.3)
        try:
            with urllib.request.urlopen(BASE + "/healthz", timeout=2):
                return p
        except Exception:
            continue
    raise RuntimeError("server did not start")


class C:
    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self, method: str, path: str, data: dict | None = None):
        body = urllib.parse.urlencode(data).encode() if data else None
        r = urllib.request.Request(BASE + path, data=body, method=method)
        if body:
            r.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.op.open(r, timeout=20) as resp:
                return resp.status, resp.read().decode("utf-8", "replace"), dict(resp.headers), resp.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), dict(e.headers), e.geturl()

    def csrf(self, html: str) -> str:
        m = re.search(r'name="csrf" value="([^"]+)"', html)
        return m.group(1) if m else ""

    def rev(self, html: str) -> str:
        m = re.search(r'name="revision" value="(\d+)"', html)
        return m.group(1) if m else "1"


def rows(table: str) -> int:
    if not DB.exists():
        return 0
    conn = sqlite3.connect(DB)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "port": PORT,
                 "db": str(DB), "name": NAME, "steps": steps, "guards": guards}
    proc = start()
    try:
        c = C()
        # ① 选品页建单（优先“选这个”，无分组则建自制单）
        s, pick, _, _ = c.req("GET", "/pick")
        form = re.search(r'<form method="post" action="/worksheet/new" class="inline-form">(.*?)</form>', pick, re.S)
        wid = ""
        if form:
            fields = dict(re.findall(r'name="([^"]+)" value="([^"]*)"', form.group(1)))
            s2, _, _, url = c.req("POST", "/worksheet/new", fields)
            wid = url.rsplit("/", 1)[-1].split("?")[0]
            rec("① /pick「选这个」建单", s2 in (200, 303) and bool(wid), status=s2, wo=wid,
                note="来自采集来源分组")
        else:
            s2, page, _, _ = c.req("GET", "/worksheet/new")
            s3, _, _, url = c.req("POST", "/worksheet/new", {
                "csrf": c.csrf(page), "self_made": "1", "submit_key": "d1-walk",
                "name": NAME, "use_case": "学习计划", "deliverable": "Excel .xlsx", "target_platform": "xianyu"})
            wid = url.rsplit("/", 1)[-1].split("?")[0]
            rec("① 自制单建单（/pick 无分组时回退）", s3 in (200, 303), status=s3, wo=wid)
        out["workorder_id"] = wid
        if NAME not in (c.req("GET", f"/copy?wo={wid}")[1] or ""):
            # 采集来源建的单，改成 synthetic 名称以便识别
            page = c.req("GET", f"/copy?wo={wid}")[1]
            c.req("POST", f"/worksheet/{wid}/copy/save",
                  {"csrf": c.csrf(page), "revision": c.rev(page), "name": NAME})

        # ② 候选 + 采用
        page = c.req("GET", f"/source?wo={wid}")[1]
        s, _, _, _ = c.req("POST", f"/worksheet/{wid}/supply/candidates", {
            "csrf": c.csrf(page), "provider": "SELF（自制，synthetic 走查）", "source_url": "self:d1",
            "kind": "同款", "commercial": "yes", "redistribute": "yes", "resale": "yes",
            "license_note": "作者自持（synthetic）"})
        page = c.req("GET", f"/source?wo={wid}")[1]
        cid = re.search(r'name="candidate_id" value="(sc:[0-9a-f]{8})"', page).group(1)
        s2, _, _, _ = c.req("POST", f"/worksheet/{wid}/supply/select",
                            {"csrf": c.csrf(page), "revision": c.rev(page), "candidate_id": cid})
        rec("② /source 新增候选并采用", s in (200, 303) and s2 in (200, 303), status=f"{s}/{s2}", candidate=cid)

        # ③ 样品自检
        page = c.req("GET", f"/source?wo={wid}")[1]
        s, _, _, _ = c.req("POST", f"/worksheet/{wid}/sample/check",
                           {"csrf": c.csrf(page), "revision": c.rev(page), "path": SAMPLE})
        verified = "verified" in c.req("GET", f"/source?wo={wid}")[1]
        rec("③ 样品自检（b7 样品，结构自检）", s in (200, 303) and verified, status=s)

        # ④ /copy 填成本/售价/卖点/FAQ/交付售后（先不填平台）
        page = c.req("GET", f"/copy?wo={wid}")[1]
        s, _, _, _ = c.req("POST", f"/worksheet/{wid}/copy/save", {
            "csrf": c.csrf(page), "revision": c.rev(page),
            "cost_minor": "300", "cost_known": "yes", "price_minor": "1990",
            "selling_points": "5 张表 + 50 公式（synthetic 走查）\n考试倒计时自动算",
            "faq_json": json.dumps([{"q": "需要什么软件", "a": "Excel 或 WPS"}], ensure_ascii=False),
            "delivery_note": "站内文件交付", "aftersales_note": "售后未定（synthetic）",
            "copy_status": "final", "copy_version": "copy-d1"})
        rec("④ /copy 填成本/售价/卖点/FAQ/交付售后", s in (200, 303), status=s)

        # 守卫 G1：此时平台为空 → 6/7，导出 409
        page = c.req("GET", f"/copy?wo={wid}")[1]
        ok_chips = page.count("✅")
        s409, body, _, _ = c.req("GET", f"/worksheet/{wid}/export?format=md")
        guard("未就绪导出 409（平台证据为空）", s409 == 409 and "platform" not in body.lower() or s409 == 409,
              status=s409, actual={"ok_chips": ok_chips})

        # ⑤ 补 synthetic 平台证据 → 7/7
        page = c.req("GET", f"/copy?wo={wid}")[1]
        s, _, _, _ = c.req("POST", f"/worksheet/{wid}/copy/save", {
            "csrf": c.csrf(page), "revision": c.rev(page),
            "platform_evidence": "synthetic://d1/walkthrough-only"})
        page = c.req("GET", f"/copy?wo={wid}")[1]
        ready = "已就绪（服务端判定）" in page
        rec("⑤ 七项就绪 7/7（synthetic 平台证据）", s in (200, 303) and ready, status=s, ready=ready)

        # ⑥ GET 导出 md/json（零写）
        before = rows("workorder_export")
        s_md, md, _, _ = c.req("GET", f"/worksheet/{wid}/export?format=md")
        s_js, js, _, _ = c.req("GET", f"/worksheet/{wid}/export?format=json")
        after = rows("workorder_export")
        payload = json.loads(js) if s_js == 200 else {}
        leaked = [k for k in ("cost_minor", "supply_note", "raw_ref", "snapshot") if k in js]
        rec("⑥ GET 导出 md+json（零写）", s_md == 200 and s_js == 200 and before == after,
            status=f"{s_md}/{s_js}", export_rows=f"{before}->{after}",
            buyer_fields=payload.get("buyer_visible_fields"), internal_leaks=leaked)

        # ⑦ POST 记录导出（1 行；重复 dedup）
        page = c.req("GET", f"/copy?wo={wid}")[1]
        before = rows("workorder_export")
        s1, _, h1, _ = c.req("POST", f"/worksheet/{wid}/export/record",
                             {"csrf": c.csrf(page), "format": "md"})
        mid = rows("workorder_export")
        s2, _, h2, _ = c.req("POST", f"/worksheet/{wid}/export/record",
                             {"csrf": c.csrf(page), "format": "md"})
        after2 = rows("workorder_export")
        rec("⑦ 记录本次导出（1 行；重复去重）", s1 == 200 and mid == before + 1 and after2 == mid,
            status=f"{s1}/{s2}", rows=f"{before}->{mid}->{after2}",
            dedup=h2.get("X-WB-Deduplicated"))
        guard("重复记录导出不新增行（dedup=true）",
              after2 == mid and h2.get("X-WB-Deduplicated") == "true",
              status=s2, actual={"rows": after2, "dedup": h2.get("X-WB-Deduplicated")})

        # ⑧ 发布回填（合法）
        page = c.req("GET", f"/copy?wo={wid}")[1]
        s, _, _, _ = c.req("POST", f"/worksheet/{wid}/publish", {
            "csrf": c.csrf(page), "status": "已发布", "published_url": "https://example.invalid/item/d1",
            "published_at": "2026-10-24T21:40:00Z", "sold_count": "0", "platform_note": "synthetic 走查，未真实发布"})
        pub_page = c.req("GET", f"/copy?wo={wid}")[1]
        rec("⑧ 发布回填（已发布/合法 URL/已售 0）", s in (200, 303) and "已发布" in pub_page, status=s)

        # 守卫 G2：发布非法值
        for payload, label in (
            ({"status": "上架"}, "状态非法"),
            ({"status": "已发布", "published_url": "ftp://x/y"}, "URL 非 http"),
            ({"status": "已发布", "sold_count": "-1"}, "销量负数"),
        ):
            s, _, _, _ = c.req("POST", f"/worksheet/{wid}/publish", {"csrf": c.csrf(pub_page), **payload})
            guard(f"发布非法值被拒（{label}）", s == 400, status=s)

        # 守卫 G3：伪造 ready/verified/gate 与篡改 selected_supply_id（走 /edit 通道）
        page = c.req("GET", f"/worksheet/{wid}/edit")[1]
        before_state = None
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        try:
            before_state = dict(conn.execute("SELECT selected_supply_id, revision, status FROM workorder "
                                             "WHERE workorder_id=?", (wid,)).fetchone())
        finally:
            conn.close()
        for payload, label in (
            ({"status": "ready"}, "status=ready"),
            ({"status": "verified"}, "status=verified"),
            ({"selected_supply_id": "sc:deadbeef"}, "篡改 selected_supply_id"),
        ):
            data = {"csrf": c.csrf(page), "revision": c.rev(page), "name": NAME, "use_case": "学习计划",
                    "deliverable": "Excel .xlsx", "target_platform": "xianyu", **payload}
            s, _, _, _ = c.req("POST", f"/worksheet/{wid}/edit", data)
            guard(f"越权字段被拒（{label}）", 400 <= s < 500, status=s)
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        try:
            after_state = dict(conn.execute("SELECT selected_supply_id, revision, status FROM workorder "
                                            "WHERE workorder_id=?", (wid,)).fetchone())
        finally:
            conn.close()
        guard("越权请求后库未变", before_state == after_state, actual={"before": before_state, "after": after_state})

        # 守卫 G4：改已选候选许可 → 样品/成本失效、readiness 下降、导出 409
        conn = sqlite3.connect(DB)
        try:
            cid = conn.execute("SELECT selected_supply_id FROM workorder WHERE workorder_id=?", (wid,)).fetchone()[0]
        finally:
            conn.close()
        s, _, _, _ = c.req("POST", f"/worksheet/{wid}/supply/candidates/{cid}", {
            "csrf": c.csrf(page), "provider": "SELF（自制，synthetic 走查）", "kind": "同款",
            "commercial": "yes", "redistribute": "yes", "resale": "no"})
        page_after = c.req("GET", f"/copy?wo={wid}")[1]
        degraded = "未就绪" in page_after
        s_exp, _, _, _ = c.req("GET", f"/worksheet/{wid}/export?format=md")
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        try:
            row = dict(conn.execute("SELECT sample_status, sample_ref, cost_minor, supply_license_resell "
                                    "FROM workorder WHERE workorder_id=?", (wid,)).fetchone())
        finally:
            conn.close()
        guard("改已选许可→样品/成本失效、导出 409",
              degraded and s_exp == 409 and row["sample_status"] is None and row["cost_minor"] is None,
              status=f"{s}/{s_exp}", actual=row)

        # ⑨ 反馈 CSV + review.py 四指标（列名与 b25/feedback-log.csv 一致）
        feed = D1 / "feedback-log.csv"
        header = ["日期", "单号", "渠道", "曝光", "询单", "成交", "退款",
                  "实际售价", "到手", "人工耗时分钟", "交付方式", "备注"]
        exists = feed.exists()
        with feed.open("a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            if not exists:
                w.writerow(header)
            w.writerow(["2026-10-24", wid, "xianyu", "na", "0", "0", "0", "19.9", "na", "30",
                        "站内文件", "synthetic 走查，未真实发布，零成交（观察期）"])
        review = ROOT / "docs" / "validation" / "product-workflow" / "b25" / "review.py"
        review_out = {}
        if review.exists():
            r = subprocess.run([str(PY), "-X", "utf8", str(review), str(feed)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            review_out = {"returncode": r.returncode, "stdout": (r.stdout or "")[-1500:],
                          "stderr": (r.stderr or "")[-500:]}
        rec("⑨ 反馈 CSV 一行 + review.py 四指标", feed.exists() and review_out.get("returncode") == 0,
            status=review_out.get("returncode"), review_tail=review_out.get("stdout", "")[-400:])
        out["review"] = review_out
        out["feedback_rows"] = sum(1 for _ in feed.open(encoding="utf-8")) - 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    out["db_counts"] = {t: rows(t) for t in ("workorder", "workorder_event", "workorder_export",
                                             "workorder_supply_candidate", "workorder_copy_version",
                                             "workorder_publish")}
    out["all_ok"] = all(s.get("ok") for s in steps) and all(g.get("ok") for g in guards)
    (D1 / "walkthrough.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    (LOGS / "walkthrough.log").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"wo": out.get("workorder_id"), "steps": len(steps), "guards": len(guards),
                      "all_ok": out["all_ok"], "counts": out["db_counts"]}, ensure_ascii=True))
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
