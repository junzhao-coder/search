"""版本 / `*` / latest failed 三个分离 case（固定 s2d_20261013_fix1；独立 HTTP + SQLite，全 API 变更）。

规则依据（已读源码）：
- supplies.update_supply：format_version 或条款变化 → 写时对 supply_distribution 追加降级行；
- state._follows_current_g2（只读）：platform_policy 还比 format_version（或 `*`），cost 因 G2 失效/绑定不一致而失效；
- reviews 同规则在 recompute 时物化（gate_expired）。

用法：& .\\.venv\\Scripts\\python.exe -X utf8 tests\\acceptance\\run_version_cases.py
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
PORT = int(os.environ.get("S2D_VERSION_PORT", "5099"))
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


def jpatch(path: str, obj: dict):
    return http("PATCH", path, body=json.dumps(obj).encode("utf-8"), ctype="application/json; charset=utf-8")


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
        print(f"[FAIL] 端口 {PORT} 被占用")
        return 1
    attempt = guard.attempt_dir(ATTEMPTS, guard.new_attempt_name("version"))
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
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()

    text = (snap / "docs" / "design" / "CONTRACT.md").read_text(encoding="utf-8")
    blocks = [b for b in re.findall(r"```csv\n(.*?)```", text, re.S)
              if "title" in b.splitlines()[0] and "data_origin" in b.splitlines()[0]]
    parsed = list(csv.reader(io.StringIO(max(blocks, key=lambda b: len(next(csv.reader(io.StringIO(b.strip()))))).strip())))
    header, base = parsed[0], dict(zip(parsed[0], parsed[1]))

    try:
        if not ready:
            check("SERVER", False, f"服务未就绪（pid={proc.pid}）")
            return 1
        check("SERVER", True, f"就绪 pid={proc.pid} 快照={snap.name}")

        def make_candidate(tag: str) -> dict:
            row = dict(base, title=f"D-版本case-{tag}", demand_url=f"https://example.com/demand/d-v-{tag}")
            _, pl, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=csv_text(header, row).encode("utf-8"),
                            ctype="text/csv; charset=utf-8")
            cand = next(r["id"] for r in (pl or {}).get("rows", [{}])[0].get("records", []) or [] if r["type"] == "candidate")
            detail = http("GET", f"/api/candidates/{cand}")[1]
            dem = next(e["id"] for e in detail["evidences"] if e["evidence_type"] == "demand")
            sup = detail["supplies"][0]
            jpost(f"/api/candidates/{cand}/gates/demand", {"status": "verified", "evidence_id": dem})
            jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                  {"status": "verified", "supply_offer_id": sup["id"], "evidence_id": sup["license_evidence_id"]})
            for r in rows("SELECT id,value_kind,money_minor,rate_bp,minutes,hourly_rate_minor,period FROM cost_item "
                          "WHERE candidate_id=? AND is_active=1", (cand,)):
                payload = {"assumption_note": "D 版本case：假设说明"}
                for k in ("value_kind", "money_minor", "rate_bp", "minutes", "hourly_rate_minor", "period"):
                    if r[k] is not None:
                        payload[k] = r[k]
                jpost(f"/api/cost-items/{r['id']}/supersede", payload)
            g3 = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})[0]
            _, pl_ev, _ = jpost(f"/api/candidates/{cand}/evidences",
                                {"evidence_type": "platform_policy", "source_url": f"https://example.com/policy/{tag}",
                                 "excerpt": f"D 版本case {tag}：平台条件", "fact_kind": "fact"})
            return {"cand": cand, "sup": sup, "policy_ev": (pl_ev or {}).get("id"), "g3": g3}

        def gate_state(cand: str) -> dict:
            return http("GET", f"/api/candidates/{cand}")[1]["gates"]

        def snapshot(cand: str) -> dict:
            return {"cand": rows("SELECT * FROM candidate WHERE id=?", (cand,)),
                    "gates": rows("SELECT * FROM gate_review WHERE candidate_id=? ORDER BY gate,seq", (cand,)),
                    "rev": rows("SELECT * FROM review_item WHERE ref_id=? OR ref_id IN "
                                "(SELECT id FROM supply_offer WHERE candidate_id=?) ORDER BY id", (cand, cand)),
                    "runs": rows("SELECT COUNT(*) n FROM run_record")[0]["n"]}

        # ---------- Case 1：G4=v1 → 同货源 PATCH=v2 ----------
        c1 = make_candidate("v")
        st_g4_1 = jpost(f"/api/candidates/{c1['cand']}/gates/platform_policy",
                        {"status": "verified", "evidence_id": c1["policy_ev"], "applies_to_platform": "xianyu",
                         "applies_to_version": "v1"})[0]
        d1 = http("GET", f"/api/candidates/{c1['cand']}")[1]["derived_status"]
        st_patch, pl_patch, _ = jpatch(f"/api/supplies/{c1['sup']['id']}", {"format_version": "v2"})
        before = snapshot(c1["cand"])
        http("GET", f"/api/candidates/{c1['cand']}")
        http("GET", f"/api/candidates/{c1['cand']}/scenario?variant=base")
        after = snapshot(c1["cand"])
        gs = gate_state(c1["cand"])
        rc1 = jpost("/api/runs/recompute")
        sys1 = rows("SELECT * FROM gate_review WHERE candidate_id=? AND verified_by='system_rule' ORDER BY gate, seq",
                    (c1["cand"],))
        blk1 = rows("SELECT * FROM review_item WHERE ref_id=? AND blocking=1 ORDER BY id", (c1["cand"],))
        mid = snapshot(c1["cand"])
        rc2 = jpost("/api/runs/recompute")
        end = snapshot(c1["cand"])
        (attempt / "version_materialized_c1.json").write_text(
            json.dumps({"system_rule_rows": sys1, "blocking_rows": blk1}, ensure_ascii=False, indent=2), encoding="utf-8")
        check("V1-patch-writes-degrade-and-reads-expired",
              st_g4_1 == 200 and d1 == "testable" and st_patch == 200 and gs["supply_distribution"] == "expired"
              and gs["cost"] == "expired" and gs["platform_policy"] == "expired" and before == after
              and rc1[0] == 200 and isinstance((rc1[1] or {}).get("downgraded"), int) and (rc1[1] or {}).get("downgraded") >= 2
              and len(sys1) >= 2 and all(r["status"] == "expired" for r in sys1) and len(blk1) >= 2
              and rc2[0] == 200 and (rc2[1] or {}).get("downgraded") == 0
              and mid["gates"] == end["gates"] and mid["rev"] == end["rev"] and end["runs"] - mid["runs"] == 1,
              f"G4(v1)={st_g4_1} 起点testable={d1 == 'testable'} PATCH={st_patch} 失效后gates={gs} GET零写={before == after} "
              f"首recompute payload downgraded={(rc1[1] or {}).get('downgraded')}(>=2) 首新增system_rule行={len(sys1)} "
              f"blocking=1复核={len(blk1)}（完整行→version_materialized_c1.json）二次 payload downgraded="
              f"{(rc2[1] or {}).get('downgraded')}(=0) 二次行一致={mid['gates'] == end['gates'] and mid['rev'] == end['rev']} "
              f"run_record+{end['runs'] - mid['runs']}")

        st_g2_re, _, _ = jpost(f"/api/candidates/{c1['cand']}/gates/supply_distribution",
                               {"status": "verified", "supply_offer_id": c1["sup"]["id"],
                                "evidence_id": c1["sup"]["license_evidence_id"]})
        st_g4_re = jpost(f"/api/candidates/{c1['cand']}/gates/platform_policy",
                         {"status": "verified", "evidence_id": c1["policy_ev"], "applies_to_platform": "xianyu",
                          "applies_to_version": "v2"})[0]
        st_g3_re = jpost(f"/api/candidates/{c1['cand']}/gates/cost", {"status": "verified", "supply_offer_id": c1["sup"]["id"]})[0]
        queue = (http("GET", "/api/review-items?status=open")[1] or {}).get("items", [])
        qcodes = [jpost(f"/api/review-items/{it['id']}/resolve",
                        {"status": "resolved_recheck", "note": "D 版本case：处理"})[0] for it in queue]
        d1_end = http("GET", f"/api/candidates/{c1['cand']}")[1]["derived_status"]
        check("V1-recheck-new-version-recovers", st_g2_re == 200 and st_g4_re == 200 and st_g3_re == 200
              and all(c == 200 for c in qcodes) and d1_end == "testable",
              f"expected 新版本重核 G2/G3/G4=200 + 队列处理全 200 → testable；actual {st_g2_re}/{st_g3_re}/{st_g4_re} "
              f"队列={len(queue)} 码={qcodes} derived={d1_end}")

        # ---------- Case 2：G4=`*` 与同货源版本变化 ----------
        c2 = make_candidate("star")
        st_g4_star = jpost(f"/api/candidates/{c2['cand']}/gates/platform_policy",
                           {"status": "verified", "evidence_id": c2["policy_ev"], "applies_to_platform": "xianyu",
                            "applies_to_version": "*"})[0]
        d2 = http("GET", f"/api/candidates/{c2['cand']}")[1]["derived_status"]
        star_row = rows("SELECT id,seq,status FROM gate_review WHERE candidate_id=? AND gate='platform_policy' "
                        "ORDER BY seq DESC LIMIT 1", (c2["cand"],))[0]
        st_patch2, _, _ = jpatch(f"/api/supplies/{c2['sup']['id']}", {"format_version": "v9"})
        gs2_before_recompute = gate_state(c2["cand"])     # 关键：先不 recompute
        st_g4_attempt, pl_g4_attempt, _ = jpost(f"/api/candidates/{c2['cand']}/gates/platform_policy",
                                                {"status": "verified", "evidence_id": c2["policy_ev"],
                                                 "applies_to_platform": "xianyu", "applies_to_version": "*",
                                                 "supply_offer_id": c2["sup"]["id"]})
        check("STAR-invalid-G2-makes-star-expired",
              st_g4_star == 200 and d2 == "testable" and st_patch2 == 200
              and gs2_before_recompute["supply_distribution"] == "expired"
              and gs2_before_recompute["platform_policy"] == "expired" and st_g4_attempt == 422,
              f"G4(*)=200 起点={d2} PATCH={st_patch2}；**未 recompute 时** gates={gs2_before_recompute}"
              f"（`*` 在 G2 失效时不得算 verified；G4 再提交={st_g4_attempt}（expected 422）明细="
              f"{json.dumps((pl_g4_attempt or {}).get('error', {}).get('details'), ensure_ascii=False)[:90]}）")

        st_g2_re2 = jpost(f"/api/candidates/{c2['cand']}/gates/supply_distribution",
                          {"status": "verified", "supply_offer_id": c2["sup"]["id"],
                           "evidence_id": c2["sup"]["license_evidence_id"]})[0]
        gs2_after = gate_state(c2["cand"])
        star_after_g2 = rows("SELECT id,seq,status FROM gate_review WHERE candidate_id=? AND gate='platform_policy' "
                             "ORDER BY seq DESC LIMIT 1", (c2["cand"],))[0]   # 重核 G2 后、POST 新 G4 之前读原行
        st_g4_final, _, _ = jpost(f"/api/candidates/{c2['cand']}/gates/platform_policy",
                                  {"status": "verified", "evidence_id": c2["policy_ev"], "applies_to_platform": "xianyu",
                                   "applies_to_version": "*", "supply_offer_id": c2["sup"]["id"]})
        st_g3_2 = jpost(f"/api/candidates/{c2['cand']}/gates/cost", {"status": "verified", "supply_offer_id": c2["sup"]["id"]})[0]
        queue2 = (http("GET", "/api/review-items?status=open")[1] or {}).get("items", [])
        qcodes2 = [jpost(f"/api/review-items/{it['id']}/resolve",
                         {"status": "resolved_recheck", "note": "D 版本case"})[0] for it in queue2]
        d2_end = http("GET", f"/api/candidates/{c2['cand']}")[1]["derived_status"]
        star_now = rows("SELECT id,seq,status FROM gate_review WHERE candidate_id=? AND gate='platform_policy' "
                        "ORDER BY seq DESC LIMIT 1", (c2["cand"],))[0]
        check("STAR-recheck-G2-then-star-valid", st_g2_re2 == 200 and st_g4_final == 200 and st_g3_2 == 200
              and gs2_after["platform_policy"] == "verified" and star_after_g2["id"] == star_row["id"]
              and star_after_g2["seq"] == star_row["seq"] and star_after_g2["status"] == "verified"
              and all(c == 200 for c in qcodes2) and d2_end == "testable",
              f"expected 重核 G2 同货源后**立即**读原 `*` 行：同 ID/seq 且有效 verified（不新增行）→ 再 POST 新 G4=200、队列逐项 200 → testable；"
              f"actual G2重核={st_g2_re2} 重核后 platform={gs2_after.get('platform_policy')} 原*行={star_row} "
              f"重核后立即读={star_after_g2} 新G4={st_g4_final} G3={st_g3_2} 队列={len(queue2)} 码={qcodes2} derived={d2_end}")

        # ---------- Case 3：latest G2 = failed（显式同货源） ----------
        c3 = make_candidate("fail")
        st_g4_3 = jpost(f"/api/candidates/{c3['cand']}/gates/platform_policy",
                        {"status": "verified", "evidence_id": c3["policy_ev"], "applies_to_platform": "xianyu",
                         "applies_to_version": c3["sup"]["format_version"]})[0]
        d3 = http("GET", f"/api/candidates/{c3['cand']}")[1]["derived_status"]
        st_failed, _, _ = jpost(f"/api/candidates/{c3['cand']}/gates/supply_distribution",
                                {"status": "failed", "supply_offer_id": c3["sup"]["id"],
                                 "evidence_id": c3["sup"]["license_evidence_id"], "note": "D 版本case：真实失败"})
        before3 = snapshot(c3["cand"])
        http("GET", f"/api/candidates/{c3['cand']}")
        after3 = snapshot(c3["cand"])
        gs3 = gate_state(c3["cand"])
        st_g3_adm = jpost(f"/api/candidates/{c3['cand']}/gates/cost", {"status": "verified", "supply_offer_id": c3["sup"]["id"]})[0]
        st_g4_adm = jpost(f"/api/candidates/{c3['cand']}/gates/platform_policy",
                          {"status": "verified", "evidence_id": c3["policy_ev"], "applies_to_platform": "xianyu",
                           "applies_to_version": c3["sup"]["format_version"], "supply_offer_id": c3["sup"]["id"]})[0]
        rc31 = jpost("/api/runs/recompute")
        sys3 = rows("SELECT * FROM gate_review WHERE candidate_id=? AND verified_by='system_rule' ORDER BY gate, seq",
                    (c3["cand"],))
        blk3 = rows("SELECT * FROM review_item WHERE ref_id=? AND blocking=1 ORDER BY id", (c3["cand"],))
        mid3 = snapshot(c3["cand"])
        rc32 = jpost("/api/runs/recompute")
        end3 = snapshot(c3["cand"])
        (attempt / "version_materialized_c3.json").write_text(
            json.dumps({"system_rule_rows": sys3, "blocking_rows": blk3}, ensure_ascii=False, indent=2), encoding="utf-8")
        check("FAILED-latest-g2-blocks-admission-zero-write",
              st_g4_3 == 200 and d3 == "testable" and st_failed == 200 and gs3["supply_distribution"] == "failed"
              and gs3["cost"] == "expired" and gs3["platform_policy"] == "expired" and before3 == after3
              and st_g3_adm == 422 and st_g4_adm == 422
              and rc31[0] == 200 and isinstance((rc31[1] or {}).get("downgraded"), int)
              and (rc31[1] or {}).get("downgraded") >= 2 and len(sys3) >= 2 and len(blk3) >= 1
              and rc32[0] == 200 and (rc32[1] or {}).get("downgraded") == 0
              and mid3["gates"] == end3["gates"] and mid3["rev"] == end3["rev"],
              f"起点={d3} status=failed 提交={st_failed} gates={gs3} GET零写={before3 == after3} "
              f"G3/G4 准入={st_g3_adm}/{st_g4_adm} 首recompute downgraded={(rc31[1] or {}).get('downgraded')}(>=2) "
              f"首新增system_rule行={len(sys3)} blocking=1复核={len(blk3)}（完整行→version_materialized_c3.json）"
              f"二次 downgraded={(rc32[1] or {}).get('downgraded')}(=0) 二次行一致={mid3['gates'] == end3['gates']}")

        st_g2_3 = jpost(f"/api/candidates/{c3['cand']}/gates/supply_distribution",
                        {"status": "verified", "supply_offer_id": c3["sup"]["id"],
                         "evidence_id": c3["sup"]["license_evidence_id"]})[0]
        st_g3_3 = jpost(f"/api/candidates/{c3['cand']}/gates/cost", {"status": "verified", "supply_offer_id": c3["sup"]["id"]})[0]
        st_g4_3b = jpost(f"/api/candidates/{c3['cand']}/gates/platform_policy",
                         {"status": "verified", "evidence_id": c3["policy_ev"], "applies_to_platform": "xianyu",
                          "applies_to_version": c3["sup"]["format_version"], "supply_offer_id": c3["sup"]["id"]})[0]
        queue3 = (http("GET", "/api/review-items?status=open")[1] or {}).get("items", [])
        qcodes3 = [jpost(f"/api/review-items/{it['id']}/resolve",
                         {"status": "resolved_recheck", "note": "D 版本case"})[0] for it in queue3]
        d3_end = http("GET", f"/api/candidates/{c3['cand']}")[1]["derived_status"]
        newborn3 = [r for r in rows("SELECT gate,status,verified_by FROM gate_review WHERE candidate_id=? "
                                    "AND verified_by='system_rule' AND status='verified'", (c3["cand"],))]
        check("FAILED-recheck-recovers", st_g2_3 == 200 and st_g3_3 == 200 and st_g4_3b == 200
              and all(c == 200 for c in qcodes3) and not newborn3 and d3_end == "testable",
              f"expected 实际 G2+G3+G4 重核 + 队列处理 → testable 且无回生；actual {st_g2_3}/{st_g3_3}/{st_g4_3b} "
              f"队列={len(queue3)} 码={qcodes3} 回生={newborn3} derived={d3_end}")

        required = ["SERVER", "V1-patch-writes-degrade-and-reads-expired", "V1-recheck-new-version-recovers",
                    "STAR-invalid-G2-makes-star-expired", "STAR-recheck-G2-then-star-valid",
                    "FAILED-latest-g2-blocks-admission-zero-write", "FAILED-recheck-recovers"]
        executed = {r["id"] for r in results}
        missing = [i for i in required if i not in executed]
        check("SELF-COVERAGE", not missing, f"expected 必测 ID 全部执行；actual 缺失={missing or 'none'}（缺任一不得 exit 0）")

        (attempt / "version_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
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
        (attempt / "version_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
