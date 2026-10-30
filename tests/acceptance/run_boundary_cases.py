"""S2-D 业务边界批（固定新快照 s2d_20261013_fix1；独立 HTTP + SQLite 复核）。

覆盖：三档采购同值转 B 其余 A → G3 422（当前缺口）；全部 10 行同值改绑/supersedes/唯一活跃/重放无增殖；
用户重核 G3/G4 + 复核处理 → testable；legacy G3/G4 NULL、G4 `v1→v2` 与 `*`、最新 G2 failed/expired 不回退；
GET 行与时间戳零写、recompute 首次物化/二次 0 变化、resolve/dismiss 不回生；默认省略 evidence_id + expires 非 None
精确 min（SQL 仅用于时间/legacy 夹具，明标）；异供给/跨候选各 422。

用法：& .\\.venv\\Scripts\\python.exe -X utf8 tests\\acceptance\\run_boundary_cases.py
"""

from __future__ import annotations

import csv
import datetime
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
SNAP_ID = os.environ.get("S2D_SNAPSHOT_ID") or "s2d_20261013_fix1"   # 固定新快照，不再新冻 app
PORT = int(os.environ.get("S2D_BOUNDARY_PORT", "5097"))
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
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerow([row.get(col, "") for col in header])
    return buf.getvalue()


def main() -> int:
    snap_root = guard.snapshot_root()
    snap = guard.resolve_under(snap_root, SNAP_ID)
    manifest_file = snap_root / f"{snap.name}.manifest.sha256"
    provenance = guard.preflight(snap, manifest_file)      # 先清单+来源，再端口，最后建目录
    if not guard.port_free(PORT):
        print(f"[FAIL] 端口 {PORT} 被占用（不结束他人进程）")
        return 1
    attempt = guard.attempt_dir(ATTEMPTS, guard.new_attempt_name("boundary"))
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
        got = [dict(r) for r in con.execute(sql, params).fetchall()]
        con.close()
        return got

    def counts() -> dict:
        out = {t: rows(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in
               ("candidate", "evidence", "supply_offer", "cost_item", "gate_review", "review_item", "run_record")}
        out["_stamps"] = [r["s"] for r in rows(
            "SELECT (SELECT COUNT(*) FROM gate_review)||'/'||(SELECT COUNT(*) FROM review_item)||'/'||"
            "(SELECT COALESCE(MAX(created_at),'') FROM gate_review)||'/'||"
            "(SELECT COALESCE(MAX(updated_at),'') FROM candidate) AS s")]
        return out

    try:
        if not ready:
            check("SERVER", False, f"服务未就绪（pid={proc.pid}）")
            return 1
        check("SERVER", True, f"就绪 pid={proc.pid} 快照={snap.name}")

        text = (snap / "docs" / "design" / "CONTRACT.md").read_text(encoding="utf-8")
        blocks = [b for b in re.findall(r"```csv\n(.*?)```", text, re.S)
                  if "title" in b.splitlines()[0] and "data_origin" in b.splitlines()[0]]
        parsed = list(csv.reader(io.StringIO(max(blocks, key=lambda b: len(next(csv.reader(io.StringIO(b.strip()))))).strip())))
        header, base = parsed[0], dict(zip(parsed[0], parsed[1]))
        st, pl, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=csv_text(header, base).encode("utf-8"),
                         ctype="text/csv; charset=utf-8")
        cand = next(r["id"] for r in (pl or {}).get("rows", [{}])[0].get("records", []) or [] if r["type"] == "candidate")
        detail = http("GET", f"/api/candidates/{cand}")[1]
        demand_ev = next(e["id"] for e in detail["evidences"] if e["evidence_type"] == "demand")
        supply_a = detail["supplies"][0]
        a_id, a_lic = supply_a["id"], supply_a["license_evidence_id"]

        def supersede_all(target_supply: str | None = None, only_roles: set[str] | None = None) -> list[int]:
            codes = []
            for row in rows("SELECT id,role,basis,value_kind,money_minor,rate_bp,minutes,hourly_rate_minor,period "
                            "FROM cost_item WHERE candidate_id=? AND is_active=1", (cand,)):
                if only_roles is not None and (row["role"] != "procurement" or row["basis"] not in only_roles):
                    continue
                payload = {"assumption_note": "D 边界批：假设说明"}
                for key in ("value_kind", "money_minor", "rate_bp", "minutes", "hourly_rate_minor", "period"):
                    if row[key] is not None:
                        payload[key] = row[key]
                if target_supply:
                    payload["supply_offer_id"] = target_supply
                codes.append(jpost(f"/api/cost-items/{row['id']}/supersede", payload)[0])
            return codes

        # A：四门槛 → testable
        jpost(f"/api/candidates/{cand}/gates/demand", {"status": "verified", "evidence_id": demand_ev})
        jpost(f"/api/candidates/{cand}/gates/supply_distribution",
              {"status": "verified", "supply_offer_id": a_id, "evidence_id": a_lic})
        supersede_all()
        st_g3a = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})[0]
        _, pl_ev, _ = jpost(f"/api/candidates/{cand}/evidences",
                            {"evidence_type": "platform_policy", "source_url": "https://example.com/policy/d-b1",
                             "excerpt": "D 边界批：平台条件摘录", "fact_kind": "fact"})
        policy_ev = (pl_ev or {}).get("id")
        st_g4a = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                       {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                        "applies_to_version": supply_a["format_version"]})[0]
        derived_a = http("GET", f"/api/candidates/{cand}")[1]["derived_status"]
        check("A-testable", st_g3a == 200 and st_g4a == 200 and derived_a == "testable",
              f"expected G3/G4=200 且 testable；actual {st_g3a}/{st_g4a} derived={derived_a}")

        # B：新条款 + v2，切 G2
        ev_exp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 2 * 86400))
        _, pl_evb, _ = jpost(f"/api/candidates/{cand}/evidences",
                             {"evidence_type": "supply_distribution", "source_url": "https://example.com/supply/5001/license",
                              "excerpt": "D 边界批：B 条款（+2 日有效）", "fact_kind": "fact", "expires_at": ev_exp})
        ev_b = (pl_evb or {}).get("id")
        _, pl_sb, _ = jpost(f"/api/candidates/{cand}/supplies",
                            {"provider_name": "D-边界B", "provider_url": "https://example.com/supply/5001",
                             "commercial_allowed": "yes", "redistribute_allowed": "yes", "resale_allowed": "yes",
                             "sample_checked": "partial", "sample_note": "D 边界批抽样", "format_version": "v2"})
        b_id = (pl_sb or {}).get("id")
        st_sw = jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                      {"status": "verified", "supply_offer_id": b_id, "evidence_id": ev_b})[0] if b_id else 0
        g2_row = rows("SELECT seq,status,supply_offer_id,evidence_id,expires_at FROM gate_review WHERE candidate_id=? "
                      "AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1", (cand,))[0]
        check("B-switch", st_sw == 200 and g2_row["supply_offer_id"] == b_id and g2_row["expires_at"] == ev_exp,
              f"expected 200 且当前行=B 且 expires 精确={ev_exp}；actual {st_sw} 行={json.dumps(g2_row, ensure_ascii=False)}")

        # 1) 仅三档采购同值转 B，其余仍 A → G3 应 422 并指出当前缺口
        codes_partial = supersede_all(target_supply=b_id, only_roles={"per_order", "one_time", "recurring"})
        st_g3_partial, pl_g3_partial, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})
        fields = [d.get("field") for d in ((pl_g3_partial or {}).get("error", {}) or {}).get("details", []) or []]
        check("PARTIAL-rebind-G3-422", st_g3_partial == 422 and "platform_fee" in fields and "manual_labor" in fields,
              f"expected 422 且缺口含 platform_fee/manual_labor；actual={st_g3_partial} 取代码={codes_partial} 缺口字段={fields[:8]}")

        # 2) 全部活跃行同值改绑 B：按“本阶段实际语义改变的行”计，不硬填总数；重放窗口单独比前后行/时间戳
        baseline = rows("SELECT id,role,basis,supply_offer_id FROM cost_item WHERE candidate_id=? AND is_active=1", (cand,))
        to_change = [r for r in baseline if r["supply_offer_id"] != b_id]
        rows_before = rows("SELECT COUNT(*) n FROM cost_item WHERE candidate_id=?", (cand,))[0]["n"]
        codes_all = supersede_all(target_supply=b_id)
        rows_after = rows("SELECT COUNT(*) n FROM cost_item WHERE candidate_id=?", (cand,))[0]["n"]
        active_b = rows("SELECT role,basis,COUNT(*) n FROM cost_item WHERE candidate_id=? AND is_active=1 AND supply_offer_id=? "
                        "GROUP BY role,basis", (cand, b_id))
        active_other = rows("SELECT COUNT(*) n FROM cost_item WHERE candidate_id=? AND is_active=1 AND "
                            "supply_offer_id IS NOT NULL AND supply_offer_id <> ?", (cand, b_id))[0]["n"]
        chained = rows("SELECT COUNT(*) n FROM cost_item WHERE candidate_id=? AND supersedes_id IS NOT NULL", (cand,))[0]["n"]
        before_replay = rows("SELECT id,is_active,supply_offer_id,created_at FROM cost_item WHERE candidate_id=? ORDER BY id", (cand,))
        replay_codes = supersede_all(target_supply=b_id)          # 重放：已无 A 绑定活跃行 → 应 all 200 且零新增
        after_replay = rows("SELECT id,is_active,supply_offer_id,created_at FROM cost_item WHERE candidate_id=? ORDER BY id", (cand,))
        check("REBIND-all-rows", all(c == 200 for c in codes_all) and all(r["n"] == 1 for r in active_b)
              and len(active_b) == 10 and rows_after == rows_before + len(to_change) and active_other == 0
              and chained >= len(to_change) + 3,
              f"本阶段待改绑={len(to_change)} 取代码={codes_all} 唯一活跃(B)={[(r['role'], r['basis'], r['n']) for r in active_b]} "
              f"行数 {rows_before}→{rows_after}（期望 +{len(to_change)}）非B活跃={active_other} supersedes链={chained}")
        check("REPLAY-no-growth", all(c == 200 for c in replay_codes) and before_replay == after_replay,
              f"expected 重放 all 200 且行/绑定/时间戳完全一致；actual 重放码={replay_codes} 完全一致={before_replay == after_replay}")

        # 3) 用户重核 G3/G4 + 复核处理 → testable
        st_g3b, pl_g3b, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})
        st_g4_bad_v1, pl_g4_bad_v1, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                                              {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                                               "applies_to_version": "v1"})
        st_g4_star, _, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                                 {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                                  "applies_to_version": "*"})
        st_g4_v2, _, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                               {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                                "applies_to_version": "v2"})
        legacy = rows("SELECT gate,seq,status,supply_offer_id FROM gate_review WHERE candidate_id=? AND seq=1 ORDER BY gate", (cand,))
        open_reviews = (http("GET", "/api/review-items?status=open")[1] or {}).get("items", [])
        review_codes = [jpost(f"/api/review-items/{item['id']}/resolve",
                              {"status": "resolved_recheck", "note": "D 边界批：复核处理"})[0] for item in open_reviews]
        derived_b = http("GET", f"/api/candidates/{cand}")[1]
        check("USER-recheck-testable", st_g3b == 200 and st_g4_v2 == 200 and st_g4_bad_v1 == 422 and st_g4_star == 200
              and len(open_reviews) >= 2 and all(c == 200 for c in review_codes)
              and derived_b["derived_status"] == "testable",
              f"G3={st_g3b} G4(v1)={st_g4_bad_v1} G4(*)={st_g4_star} G4(v2)={st_g4_v2} "
              f"legacy seq1={json.dumps(legacy, ensure_ascii=False)} derived={derived_b['derived_status']} "
              f"处理复核={len(open_reviews)} 项")

        # 4) 默认省略 evidence_id + expires 非 None 精确 min（SQL 仅用于夹具：绑定 license_evidence_id）
        _, pl_sb2, _ = jpost(f"/api/candidates/{cand}/supplies",
                             {"provider_name": "D-边界B2", "provider_url": "https://example.com/supply/5002",
                              "commercial_allowed": "yes", "redistribute_allowed": "yes", "resale_allowed": "yes",
                              "sample_checked": "partial", "sample_note": "D 边界批抽样2", "format_version": "v2"})
        b2 = (pl_sb2 or {}).get("id")
        ev2_exp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 2 * 86400))
        _, pl_ev2, _ = jpost(f"/api/candidates/{cand}/evidences",
                             {"evidence_type": "supply_distribution", "source_url": "https://example.com/supply/5002/license",
                              "excerpt": "D 边界批：B2 条款（+2 日）", "fact_kind": "fact", "expires_at": ev2_exp})
        ev2 = (pl_ev2 or {}).get("id")
        if b2 and ev2:                      # MARKER: SQL 夹具（仅时间/关联，不改业务值）
            con = sqlite3.connect(db)
            con.execute("UPDATE supply_offer SET license_evidence_id=? WHERE id=?", (ev2, b2))
            con.commit()
            con.close()
        st_om, _, _ = jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                            {"status": "verified", "supply_offer_id": b2})
        row_om = rows("SELECT evidence_id,expires_at,verified_at FROM gate_review WHERE candidate_id=? "
                      "AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1", (cand,))[0]
        expect = min(ev2_exp, (datetime.datetime.strptime(row_om["verified_at"], "%Y-%m-%dT%H:%M:%SZ")
                               + datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        check("OMITTED-evidence-exact-min", st_om == 200 and row_om["evidence_id"] == ev2 and row_om["expires_at"] == expect
              and ev2_exp, f"expected 200 + 默认关联={ev2} + expires 精确={expect}；actual={st_om} "
              f"行={json.dumps(row_om, ensure_ascii=False)} 证据有效期={ev2_exp}（SQL 夹具仅绑定 license_evidence_id）")

        # 5) 异供给/跨候选 422；最新 G2 failed 不回退
        _, pl_other, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                              body=csv_text(header, dict(base, title="D-边界跨候选",
                                                         demand_url="https://example.com/demand/d-b-cross")).encode("utf-8"),
                              ctype="text/csv; charset=utf-8")
        other = next(r["id"] for r in (pl_other or {}).get("rows", [{}])[0].get("records", []) or [] if r["type"] == "candidate")
        other_supply = http("GET", f"/api/candidates/{other}")[1]["supplies"][0]["id"]
        st_g3_foreign = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified", "supply_offer_id": a_id})[0]
        st_g4_foreign = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                              {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                               "applies_to_version": "v2", "supply_offer_id": a_id})[0]
        st_cross = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified", "supply_offer_id": other_supply})[0]
        jpost(f"/api/evidences/{ev2}/invalidate", {"invalid_reason": "D 边界批：B2 条款失效"})
        gate_now = http("GET", f"/api/candidates/{cand}")[1]["gates"]["supply_distribution"]
        cur = rows("SELECT seq,status,supply_offer_id FROM gate_review WHERE candidate_id=? AND gate='supply_distribution' "
                   "ORDER BY seq DESC LIMIT 1", (cand,))[0]
        check("FOREIGN-and-no-fallback", st_g3_foreign == 422 and st_g4_foreign == 422 and st_cross == 422
              and gate_now != "verified" and cur["supply_offer_id"] == b2,
              f"expected 异供给/跨候选 422 且失效后非 verified、当前行仍=B2；actual {st_g3_foreign}/{st_g4_foreign}/{st_cross} "
              f"gate={gate_now} 行={json.dumps(cur, ensure_ascii=False)}")

        # 6) GET 零写 + recompute 首次物化/二次 0 变化 + resolve/dismiss 不回生
        before = counts()
        http("GET", f"/api/candidates/{cand}")
        http("GET", f"/api/candidates/{cand}/scenario?variant=base")
        after = counts()
        rc1 = jpost("/api/runs/recompute")[0]
        mid = counts()
        rc2 = jpost("/api/runs/recompute")[0]
        end = counts()
        st_dismiss = jpost(f"/api/review-items/{rows('SELECT id FROM review_item ORDER BY created_at DESC LIMIT 1')[0]['id']}/resolve",
                           {"status": "dismissed", "note": "D 边界批：处理"})[0]
        gate_after = http("GET", f"/api/candidates/{cand}")[1]["gates"]["supply_distribution"]
        check("ZEROWRITE-recompute-resolve", before == after and rc1 == 200 and rc2 == 200
              and mid["review_item"] >= end["review_item"] and st_dismiss == 200 and gate_after != "verified",
              f"GET 零写={before == after} recompute={rc1}/{rc2} review_open→{before['review_item']}→{mid['review_item']}→{end['review_item']} "
              f"dismiss={st_dismiss} 失效后 gate={gate_after}")

        (attempt / "boundary_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
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
        (attempt / "boundary_cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
