"""legacy G3/G4 supply_offer_id=NULL 独立 case（固定 s2d_20261013_fix1；独立 HTTP + SQLite）。

步骤：四门槛 testable → 【SQL 夹具，明标：只把当前 G3/G4 行 supply_offer_id 置 NULL】
→ GET 两次前后整行/时间不变且 NULL 不回填 → 首次 recompute（payload downgraded>=2、新 system_rule expired、阻断 review）
→ 第二次 recompute（downgraded=0、gate/review 整行完全一致；run_record 另计）→ resolve/dismiss 不回生
→ 实际 API 用户重核 G3/G4 + 队列处理 → testable。字段一律按 PRAGMA 读取，不猜列名。

用法：& .\\.venv\\Scripts\\python.exe -X utf8 tests\\acceptance\\run_legacy_null_case.py
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _guard as guard  # noqa: E402

ACC = Path(__file__).resolve().parent
ATTEMPTS = ACC / "_tmp" / "attempts"
SNAP_ID = os.environ.get("S2D_SNAPSHOT_ID") or "s2d_20261013_fix1"
PORT = int(os.environ.get("S2D_LEGACY_PORT", "5098"))
results: list[dict] = []


def check(cid: str, ok: bool, detail: str) -> None:
    results.append({"id": cid, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}", flush=True)


def http(method: str, path: str, body: bytes | None = None, ctype: str | None = None, timeout: int = 25):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=body, method=method)
    if ctype:
        req.add_header("Content-Type", ctype)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw, status = resp.read(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        payload = None
    return status, payload, raw


def jpost(path: str, obj: dict | None = None):
    return http("POST", path, body=json.dumps(obj or {}).encode("utf-8"), ctype="application/json; charset=utf-8")


def csv_text(header: list[str], row: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerow([row.get(c, "") for c in header])
    return buf.getvalue()


def main() -> int:
    snap_root = guard.snapshot_root()
    snap = guard.resolve_under(snap_root, SNAP_ID)
    provenance = guard.preflight(snap, snap_root / f"{snap.name}.manifest.sha256")
    if not guard.port_free(PORT):
        print(f"[FAIL] 端口 {PORT} 被占用（不结束他人进程）")
        return 1
    attempt = guard.attempt_dir(ATTEMPTS, guard.new_attempt_name("legacy"))
    db = attempt / "app.db"
    print(f"snapshot={snap.name} attempt={attempt.name} port={PORT} provenance={provenance}", flush=True)
    env = {**os.environ, "APP_DB_PATH": str(db), "APP_PORT": str(PORT), "APP_HOST": "127.0.0.1",
           "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    handle = open(attempt / "server.log", "ab")
    proc = subprocess.Popen([sys.executable, "-m", "app"], cwd=str(snap), env=env,
                            stdout=handle, stderr=subprocess.STDOUT)
    ready = False
    for _ in range(80):
        time.sleep(0.5)
        try:
            if http("GET", "/api/health", timeout=2)[0] == 200:
                ready = True
                break
        except Exception:
            pass

    def rows(sql: str, params: tuple = ()) -> list[dict]:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        try:
            got = [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()
        return got

    def schema(table: str) -> list[str]:
        return [r["name"] for r in rows(f"PRAGMA table_info({table})")]

    def snapshot_rows(cid: str) -> dict:
        return {
            "candidate": rows("SELECT * FROM candidate WHERE id=?", (cid,)),
            "gates": rows("SELECT * FROM gate_review WHERE candidate_id=? ORDER BY gate, seq", (cid,)),
            "reviews": rows("SELECT * FROM review_item WHERE ref_id=? OR ref_id IN "
                            "(SELECT id FROM supply_offer WHERE candidate_id=?) ORDER BY id", (cid, cid)),
            "runs": rows("SELECT COUNT(*) n FROM run_record")[0]["n"],
        }

    def current_row(gate: str) -> dict | None:
        """按 candidate+gate 各取当前行（避免跨 gate 的 LIMIT 误取同 gate 两行）。"""
        got = rows("SELECT * FROM gate_review WHERE candidate_id=? AND gate=? ORDER BY seq DESC LIMIT 1", (cand, gate))
        return got[0] if got else None

    try:
        if not ready:
            check("SERVER", False, f"服务未就绪（pid={proc.pid}）")
            return 1
        check("SERVER", True, f"就绪 pid={proc.pid}；gate_review 列={schema('gate_review')}；"
                              f"review_item 列={schema('review_item')}；run_record 列={schema('run_record')}")

        text = (snap / "docs" / "design" / "CONTRACT.md").read_text(encoding="utf-8")
        blocks = [b for b in re.findall(r"```csv\n(.*?)```", text, re.S)
                  if "title" in b.splitlines()[0] and "data_origin" in b.splitlines()[0]]
        parsed = list(csv.reader(io.StringIO(max(blocks, key=lambda b: len(next(csv.reader(io.StringIO(b.strip()))))).strip())))
        header, base = parsed[0], dict(zip(parsed[0], parsed[1]))
        _, pl, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=csv_text(header, base).encode("utf-8"),
                        ctype="text/csv; charset=utf-8")
        cand = next(r["id"] for r in (pl or {}).get("rows", [{}])[0].get("records", []) or [] if r["type"] == "candidate")
        detail = http("GET", f"/api/candidates/{cand}")[1]
        demand_ev = next(e["id"] for e in detail["evidences"] if e["evidence_type"] == "demand")
        supply = detail["supplies"][0]
        jpost(f"/api/candidates/{cand}/gates/demand", {"status": "verified", "evidence_id": demand_ev})
        jpost(f"/api/candidates/{cand}/gates/supply_distribution",
              {"status": "verified", "supply_offer_id": supply["id"], "evidence_id": supply["license_evidence_id"]})
        for row in rows("SELECT id,value_kind,money_minor,rate_bp,minutes,hourly_rate_minor,period FROM cost_item "
                        "WHERE candidate_id=? AND is_active=1", (cand,)):
            payload = {"assumption_note": "D legacy case：假设说明"}
            for key in ("value_kind", "money_minor", "rate_bp", "minutes", "hourly_rate_minor", "period"):
                if row[key] is not None:
                    payload[key] = row[key]
            jpost(f"/api/cost-items/{row['id']}/supersede", payload)
        st_g3 = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})[0]
        _, pl_ev, _ = jpost(f"/api/candidates/{cand}/evidences",
                            {"evidence_type": "platform_policy", "source_url": "https://example.com/policy/d-legacy",
                             "excerpt": "D legacy case：平台条件摘录", "fact_kind": "fact"})
        st_g4 = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                      {"status": "verified", "evidence_id": (pl_ev or {}).get("id"), "applies_to_platform": "xianyu",
                       "applies_to_version": supply["format_version"]})[0]
        derived0 = http("GET", f"/api/candidates/{cand}")[1]["derived_status"]
        g0_cost, g0_plat = current_row("cost"), current_row("platform_policy")
        check("G0-testable-with-bound-gates", st_g3 == 200 and st_g4 == 200 and derived0 == "testable"
              and g0_cost and g0_plat and g0_cost["supply_offer_id"] and g0_plat["supply_offer_id"],
              f"expected G3/G4=200、testable 且 cost/platform 当前行各自已绑定货源；actual {st_g3}/{st_g4} derived={derived0} "
              f"cost行={json.dumps(g0_cost, ensure_ascii=False)[:110]} platform行={json.dumps(g0_plat, ensure_ascii=False)[:110]}")

        # 【SQL 夹具，明标】只把当前 G3/G4 的 supply_offer_id 置 NULL（模拟修复前 legacy 行）
        con = sqlite3.connect(db)
        affected = 0
        for gate in ("cost", "platform_policy"):
            cur = con.execute("SELECT id FROM gate_review WHERE candidate_id=? AND gate=? ORDER BY seq DESC LIMIT 1",
                              (cand, gate)).fetchone()
            if cur:
                con.execute("UPDATE gate_review SET supply_offer_id=NULL WHERE id=?", (cur[0],))
                affected += 1
        con.commit()
        con.close()
        legacy_cost, legacy_plat = current_row("cost"), current_row("platform_policy")
        check("FIXTURE-legacy-null", affected == 2 and legacy_cost and legacy_plat
              and legacy_cost["supply_offer_id"] is None and legacy_plat["supply_offer_id"] is None,
              f"SQL 夹具（明标，仅置 supply_offer_id=NULL）影响={affected} 行；cost行={json.dumps(legacy_cost, ensure_ascii=False)[:110]} "
              f"platform行={json.dumps(legacy_plat, ensure_ascii=False)[:110]}")

        before = snapshot_rows(cand)
        http("GET", f"/api/candidates/{cand}")
        http("GET", f"/api/candidates/{cand}/scenario?variant=base")
        after = snapshot_rows(cand)
        still_null = [current_row("cost")["supply_offer_id"], current_row("platform_policy")["supply_offer_id"]]
        check("LEGACY-get-no-backfill", before == after and all(v is None for v in still_null),
              f"expected 两次 GET 前后 candidate/gate_review/review_item 整行与时间字段完全一致且 NULL 不回填；"
              f"actual 一致={before == after} 当前行 supply_offer_id={still_null}")

        st_rc1, pl_rc1, _ = jpost("/api/runs/recompute")
        down1 = (pl_rc1 or {}).get("downgraded")
        sys_rows = rows("SELECT gate,status,verified_by,created_at FROM gate_review WHERE candidate_id=? AND "
                        "verified_by='system_rule' ORDER BY gate, seq", (cand,))
        blocking = rows("SELECT * FROM review_item WHERE status='open' ORDER BY id")
        check("LEGACY-recompute-first-materialize", st_rc1 == 200 and isinstance(down1, int) and down1 >= 2
              and {r["gate"] for r in sys_rows} >= {"cost", "platform_policy"}
              and all(r["status"] == "expired" for r in sys_rows) and len(blocking) >= 2,
              f"expected recompute 200 且 payload downgraded>=2、新增 system_rule expired（cost+platform）且阻断 review>=2；"
              f"actual 码={st_rc1} downgraded={down1} system行={json.dumps(sys_rows, ensure_ascii=False)[:160]} 开复核={len(blocking)}")

        before2 = snapshot_rows(cand)
        st_rc2, pl_rc2, _ = jpost("/api/runs/recompute")
        after2 = snapshot_rows(cand)
        runs_delta = after2["runs"] - before2["runs"]
        same_gates = before2["gates"] == after2["gates"]
        same_reviews = before2["reviews"] == after2["reviews"]
        check("LEGACY-recompute-second-idempotent", st_rc2 == 200 and (pl_rc2 or {}).get("downgraded") == 0
              and same_gates and same_reviews and runs_delta == 1,
              f"expected 二次 recompute downgraded=0、gate/review 整行（含 created/resolved 字段）完全一致、"
              f"run_record 另计 +1；actual 码={st_rc2} downgraded={(pl_rc2 or {}).get('downgraded')} "
              f"gate一致={same_gates} review一致={same_reviews} run_record +{runs_delta}")

        # resolve / dismiss 不回生（分别用真实允许状态）
        open_items = rows("SELECT * FROM review_item WHERE status='open' ORDER BY id")
        status_field = "status"
        resolved_code = dismissed_code = None
        if open_items:
            resolved_code = jpost(f"/api/review-items/{open_items[0]['id']}/resolve",
                                  {"status": "resolved_recheck", "note": "D legacy：重核完成"})[0]
        if len(open_items) >= 2:
            dismissed_code = jpost(f"/api/review-items/{open_items[-1]['id']}/resolve",
                                   {"status": "dismissed", "note": "D legacy：不予恢复"})[0]
        gates_after = rows("SELECT gate,status,verified_by,seq,supply_offer_id FROM gate_review WHERE candidate_id=? "
                           "AND gate IN ('cost','platform_policy') ORDER BY gate, seq", (cand,))
        newborn = [r for r in gates_after if r["verified_by"] == "system_rule" and r["status"] == "verified"]
        derived_after = http("GET", f"/api/candidates/{cand}")[1]["derived_status"]
        check("LEGACY-resolve-dismiss-no-rebirth",
              resolved_code == 200 and dismissed_code == 200 and not newborn and derived_after != "testable",
              f"expected resolve/dismiss 均 200 且失效门槛不回生（无 system_rule verified 行）、仍非 testable；"
              f"actual resolve={resolved_code} dismiss={dismissed_code} 回生={newborn} derived={derived_after} 字段={status_field}")

        # 实际 API 用户重核 + 正确队列处理 → testable
        supply_id = http("GET", f"/api/candidates/{cand}")[1]["supplies"][0]["id"]
        st_g3_again = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified", "supply_offer_id": supply_id})[0]
        st_g4_again = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                            {"status": "verified", "evidence_id": (pl_ev or {}).get("id"), "applies_to_platform": "xianyu",
                             "applies_to_version": supply["format_version"], "supply_offer_id": supply_id})[0]
        queue = (http("GET", "/api/review-items?status=open")[1] or {}).get("items", [])
        q_codes = [jpost(f"/api/review-items/{it['id']}/resolve",
                         {"status": "resolved_recheck", "note": "D legacy：队列处理"})[0] for it in queue]
        derived_end = http("GET", f"/api/candidates/{cand}")[1]["derived_status"]
        g2_cur = current_row("supply_distribution")
        expected_sup = (g2_cur or {}).get("supply_offer_id")
        rebound = {"cost": current_row("cost"), "platform_policy": current_row("platform_policy")}
        check("LEGACY-user-recheck-recovers", st_g3_again == 200 and st_g4_again == 200
              and all(c == 200 for c in q_codes) and derived_end == "testable"
              and expected_sup and all(r and r["supply_offer_id"] == expected_sup for r in rebound.values())
              and all(r["status"] == "verified" for r in rebound.values()),
              f"expected 用户 API 重核 G3/G4=200、队列处理全 200、derived=testable 且 cost/platform 当前行均绑定最新 G2 货源"
              f"({expected_sup}) 且 status=verified；actual {st_g3_again}/{st_g4_again} 队列={len(queue)} 码={q_codes} "
              f"derived={derived_end} cost行={json.dumps(rebound['cost'], ensure_ascii=False)[:110]} "
              f"platform行={json.dumps(rebound['platform_policy'], ensure_ascii=False)[:110]}")

        (attempt / "legacy_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        fails = [r["id"] for r in results if not r["ok"]]
        print(f"合计 {len(results)} 项：PASS {sum(1 for r in results if r['ok'])} / FAIL {len(fails)}；证据={attempt.name}", flush=True)
        return 0 if not fails else 1
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            code = proc.wait(timeout=10)
        except Exception:
            proc.kill()
            code = proc.wait(timeout=10)
        print(f"服务已停止 pid={proc.pid} exit={code}（只停自启 PID）", flush=True)
        (attempt / "legacy_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
