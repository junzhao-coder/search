"""S2-D 第二批：A→B 货源切换探针 + 真实 CLI 守卫（自身 scope，隔离镜像）。

- 快照 ID 显式固定（env S2D_SNAPSHOT_ID 或指针），先校验清单再创建任何产物。
- 端口检查在创建目录之前；目录独占创建；不删不覆盖既有快照/DB/日志。
- Node 与对照测试副产物只落 _tmp 哈希一致镜像。
- 危险负例在 _tmp 内隔离哨兵工作区执行（S2D_SNAPSHOT_ROOT 覆盖），不动真实 _snapshots。

用法：
    & .\\.venv\\Scripts\\python.exe -X utf8 tests\\acceptance\\run_s2_attempt.py
    仅端口检查：S2D_PORTCHECK_ONLY=1（真实 CLI 退出码用于守卫证明）
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import os
import random
import re
import shutil
import socket
import sqlite3
import string
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _guard as guard  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ACC = ROOT / "tests" / "acceptance"
ATTEMPTS = ACC / "_tmp" / "attempts"
SNAP_ID = os.environ.get("S2D_SNAPSHOT_ID") or "s2d_20261013_fix1"   # 显式固定，不按目录序择新
PORT = int(os.environ.get("S2D_ATTEMPT_PORT", "5096"))
results: list[tuple[str, str, str]] = []
lines: list[str] = []


def log(text: str = "") -> None:
    lines.append(text)
    print(text, flush=True)


def check(cid: str, ok: bool, detail: str) -> None:
    results.append((cid, "PASS" if ok else "FAIL", detail))
    log(f"[{'PASS' if ok else 'FAIL'}] {cid}: {detail}")


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
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerow([row.get(col, "") for col in header])
    return buf.getvalue()


def main() -> int:
    run_id = os.environ.get("S2D_RUN_ID") or "attempt_" + time.strftime("%Y%m%d_%H%M%S") + "_" + \
        "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    try:
        attempt = guard.resolve_under(ATTEMPTS, run_id)
        snap_root = guard.snapshot_root()                             # 统一用 guard 根（env 覆盖仅 _tmp 之下）
        snap = guard.resolve_under(snap_root, script_snapshot_id())
        manifest_file = snap_root / f"{snap.name}.manifest.sha256"
        provenance = guard.preflight(snap, manifest_file)             # 清单完整（非空/无重复/无越界/逐文件哈希）+ 来源合法
        if not guard.port_free(PORT):                                 # 再查端口，最后才建目录
            raise guard.GuardError(f"端口 {PORT} 被占用；不结束他人进程，直接失败")
        if os.environ.get("S2D_PORTCHECK_ONLY") == "1":
            print(f"[PASS] PORTCHECK-ONLY：清单 0 不符、端口 {PORT} 空闲")
            return 0
        guard.exclusive_dir(attempt)                                  # 独占；已存在即失败
    except guard.GuardError as exc:
        print(f"[FAIL] {exc}")
        return 1
    except FileExistsError:
        print(f"[FAIL] attempt 目录已存在，拒绝覆盖：{run_id}")
        return 1

    logpath = attempt / "attempt_log.txt"
    db = attempt / "app.db"
    log(f"# S2-D 第二批补证 {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    log(f"snapshot={snap.name} attempt={attempt.name} port={PORT} "
        f"python={sys.version.split()[0]} sqlite={sqlite3.sqlite_version}")
    check("SNAP-MANIFEST", True, f"{snap.name} 清单逐文件核对：不符=0（{len(manifest_file.read_text(encoding='utf-8').splitlines())} 条）")
    provenance = guard.probe_app(snap)
    check("SNAP-PROVENANCE", provenance.startswith(str(snap)), f"app.__file__={provenance}（PYTHONDONTWRITEBYTECODE=1）")

    # Node 与对照测试镜像（哈希一致，副产物只落 _tmp）
    mirror = attempt / "mirror"
    for rel in ("app/static/ui.js", "tests/ui/ui_behavior.mjs", "tests/ui/__init__.py"):
        src = snap / rel
        if src.exists():
            dst = mirror / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    mirror_ok = all(hashlib.sha256((mirror / rel).read_bytes()).hexdigest()
                    == hashlib.sha256((snap / rel).read_bytes()).hexdigest()
                    for rel in ("app/static/ui.js", "tests/ui/ui_behavior.mjs") if (snap / rel).exists())
    check("MIRROR-HASH", mirror_ok, f"镜像副本与快照逐字节一致（{mirror}）；Node 产物将只落镜像内 _tmp")

    env = {**os.environ, "APP_DB_PATH": str(db), "APP_PORT": str(PORT), "APP_HOST": "127.0.0.1",
           "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    handle = open(attempt / "server.log", "ab")
    proc = subprocess.Popen([sys.executable, "-m", "app"], cwd=str(snap), env=env,
                            stdout=handle, stderr=subprocess.STDOUT)
    health = None
    for _ in range(80):
        time.sleep(0.5)
        try:
            status, payload, _ = http("GET", "/api/health", timeout=2)
            if status == 200:
                health = payload
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
               ("candidate", "demand_signal", "evidence", "supply_offer", "cost_item", "gate_review",
                "review_item", "import_batch", "run_record", "idempotency_key", "draft", "feedback")}
        out["_stamps"] = [r["s"] for r in rows(
            "SELECT (SELECT COUNT(*) FROM gate_review)||'/'||(SELECT COUNT(*) FROM review_item)||'/'||"
            "(SELECT COALESCE(MAX(created_at),'') FROM gate_review) AS s")]
        return out

    try:
        if health is None:
            check("SERVER", False, f"服务未就绪（pid={proc.pid}）")
            return 1
        check("SERVER", True, f"就绪 pid={proc.pid} health={json.dumps(health, ensure_ascii=False)}")

        text = (snap / "docs" / "design" / "CONTRACT.md").read_text(encoding="utf-8")
        blocks = [b for b in re.findall(r"```csv\n(.*?)```", text, re.S)
                  if "title" in b.splitlines()[0] and "data_origin" in b.splitlines()[0]]
        parsed = list(csv.reader(io.StringIO(max(blocks, key=lambda b: len(next(csv.reader(io.StringIO(b.strip()))))).strip())))
        header, base = parsed[0], dict(zip(parsed[0], parsed[1]))
        st, pl, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                         body=(csv_text(header, base)).encode("utf-8"), ctype="text/csv; charset=utf-8")
        cand = next(r["id"] for r in (pl or {}).get("rows", [{}])[0].get("records", []) or [] if r["type"] == "candidate")
        check("IMPORT-38", st == 201 and bool(cand), f"38 列正例 -> {st} candidate={cand}")

        detail = http("GET", f"/api/candidates/{cand}")[1]
        demand_ev = next(e["id"] for e in detail["evidences"] if e["evidence_type"] == "demand")
        supply_a = detail["supplies"][0]
        a_id, a_lic = supply_a["id"], supply_a["license_evidence_id"]
        st_g1, _, _ = jpost(f"/api/candidates/{cand}/gates/demand", {"status": "verified", "evidence_id": demand_ev})
        st_g2a, _, _ = jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                             {"status": "verified", "supply_offer_id": a_id, "evidence_id": a_lic})
        st_g3a_no, pl_g3a_no, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})
        codes = []
        for row in rows("SELECT id,value_kind,money_minor,rate_bp,minutes,hourly_rate_minor,period FROM cost_item "
                        "WHERE candidate_id=? AND is_active=1", (cand,)):
            payload = {"assumption_note": "D 补证:假设说明"}
            for key in ("value_kind", "money_minor", "rate_bp", "minutes", "hourly_rate_minor", "period"):
                if row[key] is not None:
                    payload[key] = row[key]
            codes.append(jpost(f"/api/cost-items/{row['id']}/supersede", payload)[0])
        st_g3, _, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})
        _, pl_ev, _ = jpost(f"/api/candidates/{cand}/evidences",
                            {"evidence_type": "platform_policy", "source_url": "https://example.com/policy/d-1",
                             "excerpt": "D 补证:平台条件摘录", "fact_kind": "fact"})
        policy_ev = (pl_ev or {}).get("id")
        st_g4, _, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                            {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                             "applies_to_version": supply_a["format_version"]})
        detail = http("GET", f"/api/candidates/{cand}")[1]
        sc = http("GET", f"/api/candidates/{cand}/scenario?variant=base")[1]
        check("A-testable", st_g1 == st_g2a == st_g3 == st_g4 == 200 and detail["derived_status"] == "testable"
              and (sc or {}).get("contribution_per_order_minor") == 190,
              f"expected 4×200 + testable + 190；actual {st_g1}/{st_g2a}/{st_g3}/{st_g4} derived={detail['derived_status']} "
              f"contribution={(sc or {}).get('contribution_per_order_minor')}")
        check("ASSERT-G3-no-note", st_g3a_no == 422,
              f"expected 422；actual={st_g3a_no} details={json.dumps((pl_g3a_no or {}).get('error', {}).get('details'), ensure_ascii=False)[:80]} 取代码={codes}")

        # B：新条款证据 + 不同版本；切换探针用显式 evidence_id（契约支持路径）
        ev_expires = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3 * 86400))
        _, pl_ev_b, _ = jpost(f"/api/candidates/{cand}/evidences",
                              {"evidence_type": "supply_distribution", "source_url": "https://example.com/supply/3001/license",
                               "excerpt": "D 补证:B 新条款摘录", "fact_kind": "fact", "expires_at": ev_expires})
        ev_b = (pl_ev_b or {}).get("id")
        st_sup_b, pl_sup_b, _ = jpost(f"/api/candidates/{cand}/supplies",
                                      {"provider_name": "D-货源B", "provider_url": "https://example.com/supply/3001",
                                       "commercial_allowed": "yes", "redistribute_allowed": "yes", "resale_allowed": "yes",
                                       "sample_checked": "partial", "sample_note": "D 补证:抽样", "format_version": "v2",
                                       "license_evidence_url": "https://example.com/supply/3001/license"})
        b_id = (pl_sup_b or {}).get("id")
        ev_b_persisted = rows("SELECT expires_at FROM evidence WHERE id=?", (ev_b,))
        ev_b_expires = ev_b_persisted[0]["expires_at"] if ev_b_persisted else None
        log(f"INFO POST /supplies -> {st_sup_b} body={json.dumps(pl_sup_b, ensure_ascii=False)[:100]}"
            f"（该接口 INSERT 不含 license_evidence_id，省略证据的默认关联需用导入路径货源）")
        st_g2b, pl_g2b, _ = jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                                  {"status": "verified", "supply_offer_id": b_id, "evidence_id": ev_b})
        g2_row = rows("SELECT seq, status, supply_offer_id, evidence_id, expires_at FROM gate_review WHERE candidate_id=? "
                      "AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1", (cand,))[0]
        switch_ok = st_g2b == 200 and g2_row["supply_offer_id"] == b_id and g2_row["evidence_id"] == ev_b
        check("ASSERT-G2-switch-A2B", switch_ok,
              f"expected 显式证据核验 B 得 200 且当前行指向 B/A 证据换成 B 条款；actual={st_g2b} "
              f"行={json.dumps(g2_row, ensure_ascii=False)} b_id={b_id} ev_b={ev_b}")
        check("ASSERT-G2-TTL-equals-evidence", switch_ok and g2_row["expires_at"] == ev_b_expires and ev_b_expires is not None,
              f"expected 核验行 expires_at 精确等于所用证据有效期；actual 行={g2_row['expires_at']} 证据={ev_b_expires}")

        # 省略 evidence_id 的默认关联 + 精确 TTL：用与正例同构的导入行（其货源带 license_evidence_id）
        ttl_row = dict(base, title="D-默认关联", demand_url="https://example.com/demand/d-ttl",
                       demand_excerpt="D 补证:默认关联")
        _, pl_ttl, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                            body=csv_text(header, ttl_row).encode("utf-8"), ctype="text/csv; charset=utf-8")
        ttl_cand = next(r["id"] for r in (pl_ttl or {}).get("rows", [{}])[0].get("records", []) or [] if r["type"] == "candidate")
        ttl_supply = http("GET", f"/api/candidates/{ttl_cand}")[1]["supplies"][0]
        st_g2_default, _, _ = jpost(f"/api/candidates/{ttl_cand}/gates/supply_distribution",
                                    {"status": "verified", "supply_offer_id": ttl_supply["id"]})
        ttl_gate = rows("SELECT evidence_id, expires_at, verified_at FROM gate_review WHERE candidate_id=? "
                        "AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1", (ttl_cand,))[0]
        ttl_ev = rows("SELECT expires_at FROM evidence WHERE id=?", (ttl_supply["license_evidence_id"],))
        ttl_ev_expires = ttl_ev[0]["expires_at"] if ttl_ev else None
        expect_expiry = ttl_ev_expires or (datetime.datetime.strptime(ttl_gate["verified_at"], "%Y-%m-%dT%H:%M:%SZ")
                                          + datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        check("ASSERT-G2-omitted-evidence-TTL",
              st_g2_default == 200 and ttl_gate["evidence_id"] == ttl_supply["license_evidence_id"]
              and ttl_gate["expires_at"] == expect_expiry,
              f"expected 200 + 默认关联条款证据 {ttl_supply['license_evidence_id']} + expires_at 精确等于 min(证据,verified+30d)="
              f"{expect_expiry}；actual={st_g2_default} 行 evidence={ttl_gate['evidence_id']} expires={ttl_gate['expires_at']} "
              f"（证据有效期={ttl_ev_expires}）")

        before = counts()
        detail_b = http("GET", f"/api/candidates/{cand}")[1]
        sc_b = http("GET", f"/api/candidates/{cand}/scenario?variant=base")[1]
        after = counts()
        cost_plat = rows("SELECT gate, seq, status, supply_offer_id FROM gate_review WHERE candidate_id=? "
                         "AND gate IN ('cost','platform_policy') ORDER BY gate", (cand,))
        check("B-no-impersonation", detail_b["gates"].get("supply_distribution") == "verified"
              and detail_b["derived_status"] != "testable",
              f"expected 当前 G2=B 且 derived≠testable；actual derived={detail_b['derived_status']} gates={detail_b['gates']} "
              f"scenario={(sc_b or {}).get('contribution_per_order_minor')} cost/platform={json.dumps(cost_plat, ensure_ascii=False)}")
        check("ASSERT-GET-zero-write", before == after,
              f"expected 两次 GET 前后全部计数与时间戳一致；actual before={json.dumps(before, ensure_ascii=False)}")

        # G3/G4 显式异货源 / 跨候选
        st_g3_a, pl_g3_a, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified", "supply_offer_id": a_id})
        st_g4_a, _, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                              {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                               "applies_to_version": supply_a["format_version"], "supply_offer_id": a_id})
        other = dict(base, title="D-跨候选", demand_url="https://example.com/demand/d-cross", demand_excerpt="D 补证:跨候选")
        _, pl_o, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=csv_text(header, other).encode("utf-8"),
                          ctype="text/csv; charset=utf-8")
        other_cand = next(r["id"] for r in (pl_o or {}).get("rows", [{}])[0].get("records", []) or [] if r["type"] == "candidate")
        other_supply = http("GET", f"/api/candidates/{other_cand}")[1]["supplies"][0]["id"]
        st_g3_cross, _, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified", "supply_offer_id": other_supply})
        st_g4_cross, _, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                                  {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                                   "applies_to_version": "v2", "supply_offer_id": other_supply})
        check("ASSERT-G3-foreign", switch_ok and st_g3_a == 422,
              f"前置=切换成功({switch_ok})；expected 当前 G2=B 时 G3 用旧 A 货源 422；actual={st_g3_a} "
              f"details={json.dumps((pl_g3_a or {}).get('error', {}).get('details'), ensure_ascii=False)[:80]}")
        check("ASSERT-G4-foreign", switch_ok and st_g4_a == 422 and st_g4_cross == 422,
              f"前置=切换成功({switch_ok})；expected G4 异货源/跨候选均 422；actual={st_g4_a}/{st_g4_cross}")
        check("ASSERT-G3-cross-candidate", st_g3_cross == 422, f"expected 422；actual={st_g3_cross}")

        # 最新 G2 失败不回退
        st_inv, _, _ = jpost(f"/api/evidences/{ev_b}/invalidate", {"invalid_reason": "D 补证:B 条款失效"})
        detail_c = http("GET", f"/api/candidates/{cand}")[1]
        g2_now = rows("SELECT seq, status, supply_offer_id FROM gate_review WHERE candidate_id=? AND gate='supply_distribution' "
                      "ORDER BY seq DESC LIMIT 1", (cand,))[0]
        check("ASSERT-G2-no-fallback", switch_ok and st_inv == 200 and detail_c["gates"].get("supply_distribution") != "verified"
              and g2_now["supply_offer_id"] == b_id,
              f"前置=切换成功({switch_ok})；expected 失效后非 verified 且当前行仍=B；actual={detail_c['gates'].get('supply_distribution')} "
              f"行={json.dumps(g2_now, ensure_ascii=False)}")

        # recurring 422 零写 / per_order 200 新值 NULL
        rec = rows("SELECT id FROM cost_item WHERE candidate_id=? AND basis='recurring' AND is_active=1", (cand,))
        if rec:
            b_rows = rows("SELECT id,is_active,value_kind,money_minor,period FROM cost_item WHERE candidate_id=? ORDER BY id", (cand,))
            st_rec, pl_rec, _ = jpost(f"/api/cost-items/{rec[0]['id']}/supersede", {"assumption_note": "D 补证:只改说明"})
            a_rows = rows("SELECT id,is_active,value_kind,money_minor,period FROM cost_item WHERE candidate_id=? ORDER BY id", (cand,))
            check("ASSERT-recurring-422-zerowrite", st_rec == 422 and b_rows == a_rows,
                  f"expected 422 且前后行完全一致；actual={st_rec} 一致={b_rows == a_rows} details={json.dumps((pl_rec or {}).get('error', {}).get('details'), ensure_ascii=False)[:70]}")
        per = rows("SELECT id FROM cost_item WHERE candidate_id=? AND role='acquisition' AND is_active=1", (cand,))
        if per:
            st_per, _, _ = jpost(f"/api/cost-items/{per[0]['id']}/supersede", {"assumption_note": "D 补证:仅改说明"})
            new_row = rows("SELECT value_kind,money_minor,assumption_note FROM cost_item WHERE candidate_id=? AND role='acquisition' "
                           "ORDER BY created_at DESC LIMIT 1", (cand,))[0]
            old = rows("SELECT is_active FROM cost_item WHERE id=?", (per[0]["id"],))[0]
            check("ASSERT-per_order-note-only", st_per == 200 and new_row["value_kind"] is None and new_row["money_minor"] is None
                  and old["is_active"] == 0,
                  f"expected 200 + 旧行停用 + 新行值 NULL；actual={st_per} 新行={json.dumps(new_row, ensure_ascii=False)} 旧行={json.dumps(old)}")

        # ---------- 真实 CLI 守卫（隔离哨兵工作区；前后哨兵/树哈希证明） ----------
        sentinel_root = attempt / "guard_snapshots"
        sentinel_root.mkdir(parents=True, exist_ok=True)
        snap_tree_before, snap_hash_before = guard.manifest(snap)
        manifest_before = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
        instance_db = ROOT / "instance" / "app.db"
        instance_before = hashlib.sha256(instance_db.read_bytes()).hexdigest() if instance_db.exists() else None
        env_guard = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
                     "S2D_SNAPSHOT_ROOT": str(sentinel_root),
                     "S2D_POINTER": str(attempt / "guard_pointer.txt")}
        freeze = str(Path(__file__).resolve().parent / "freeze_snapshot.py")
        bad_results = {}
        for label, bad in (("absolute", str(ROOT / "evil")), ("separator", "a/b"), ("dotdot", "..")):
            proc_bad = subprocess.run([sys.executable, "-X", "utf8", freeze, bad], cwd=str(ROOT), env=env_guard,
                                      capture_output=True, text=True, encoding="utf-8", errors="replace")
            bad_results[label] = (proc_bad.returncode, "非法 RUN_ID" in (proc_bad.stdout + proc_bad.stderr))
        check("GUARD-CLI-illegal-id",
              all(code != 0 and flagged for code, flagged in bad_results.values())
              and len(list(sentinel_root.iterdir())) == 0,
              f"expected 三个非法 ID 均 exit≠0、提示非法、哨兵工作区仍为空（不比较 '..' 这类指向父目录的路径存在性）；"
              f"actual={bad_results} 目录={[p.name for p in sentinel_root.iterdir()]}")
        ok_id = "guard_dup_" + run_id
        first = subprocess.run([sys.executable, "-X", "utf8", freeze, ok_id], cwd=str(ROOT), env=env_guard,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        second = subprocess.run([sys.executable, "-X", "utf8", freeze, ok_id], cwd=str(ROOT), env=env_guard,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        dup_dir = sentinel_root / ok_id
        dup_hash = guard.manifest(dup_dir)[1] if dup_dir.exists() else None
        check("GUARD-CLI-duplicate-id", first.returncode == 0 and second.returncode != 0 and dup_hash is not None
              and "已存在" in (second.stdout + second.stderr),
              f"expected 首次 exit=0、重复 exit≠0 且既有快照未被覆盖；actual first={first.returncode} second={second.returncode} "
              f"hash={dup_hash} 提示={'已存在' in (second.stdout + second.stderr)}")
        with socket.socket() as hold:
            hold.bind(("127.0.0.1", PORT + 1))
            hold.listen(1)
            busy = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--portcheck-only"],
                                  cwd=str(ROOT), env={**env_guard, "S2D_ATTEMPT_PORT": str(PORT + 1),
                                                      "S2D_PORTCHECK_ONLY": "1", "S2D_RUN_ID": "guard_busy_" + run_id},
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
        check("GUARD-CLI-port-busy", busy.returncode != 0 and "被占用" in (busy.stdout + busy.stderr),
              f"expected 占用端口时 exit≠0 且提示占用；actual={busy.returncode} 输出={(busy.stdout + busy.stderr).strip()[:80]}")
        snap_tree_after, snap_hash_after = guard.manifest(snap)
        instance_after = hashlib.sha256(instance_db.read_bytes()).hexdigest() if instance_db.exists() else None
        check("GUARD-no-side-effects",
              snap_hash_before == snap_hash_after and manifest_before == hashlib.sha256(manifest_file.read_bytes()).hexdigest()
              and instance_before == instance_after,
              f"expected 固定快照/清单/业务库前后不变；actual snap {snap_hash_before[:12]}→{snap_hash_after[:12]} "
              f"instance_unchanged={instance_before == instance_after}")

        # ---------- Node 镜像 + 对照测试镜像（副产物只落 _tmp） ----------
        node = shutil.which("node")
        if node:
            proc_n = subprocess.run([node, str(mirror / "tests" / "ui" / "ui_behavior.mjs")], cwd=str(mirror),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            artifact = mirror / "tests" / "ui" / "_tmp" / "feedback_payloads.json"
            check("NODE-MIRROR-HARNESS", proc_n.returncode == 0 and artifact.exists(),
                  f"镜像内 node exit={proc_n.returncode} 产物={artifact.exists()}（快照内未生成副产物）")
            capture = json.loads(artifact.read_text(encoding="utf-8")) if artifact.exists() else {}
            refund = (capture.get("refund") or {}).get("payload") or {}
            adapted = dict(refund)
            adapted.update({"related_feedback_id": rows("SELECT id FROM feedback ORDER BY created_at LIMIT 1")[0]["id"]
                            if rows("SELECT id FROM feedback") else None, "order_ref": None, "refund_state": "pending"})
            log(f"INFO Node 捕获退款载荷键={sorted(refund.keys())}（桥接时保留 amount_minor，仅适配关联 ID/order_ref/refund_state，非原样字节提交）")
        else:
            check("NODE-MIRROR-HARNESS", False, "未找到 node：JS 行为用例无法运行（不得跳过计数为成功）")

        log("")
        for cid, state, _ in results:
            log(f"{state}\t{cid}")
        fails = [r for r in results if r[1] == "FAIL"]
        log(f"合计 {len(results)} 项：PASS {sum(1 for r in results if r[1] == 'PASS')} / FAIL {len(fails)}")
        return 0 if not fails else 1
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            code = proc.wait(timeout=10)
        except Exception:
            proc.kill()
            code = proc.wait(timeout=10)
        log(f"服务已停止 pid={proc.pid} exit={code}（只停自启 PID）")
        logpath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def script_snapshot_id() -> str:
    if os.environ.get("S2D_SNAPSHOT_ID"):
        return guard.safe_id(os.environ["S2D_SNAPSHOT_ID"])
    pointer = guard.pointer_path()                            # 规范指针（含链接核对 _tmp 边界）
    if pointer.exists():
        return guard.read_pointer(pointer)
    return guard.safe_id(SNAP_ID)


if __name__ == "__main__":
    sys.exit(main())
