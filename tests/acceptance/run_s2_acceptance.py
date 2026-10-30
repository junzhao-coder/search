"""S2-D 整链路独立验收：在冻结快照上跑干净库端到端 + 边界 + UI(HTTP/HTML) 检查。

用法（工作区根目录）：
    $env:PYTHONUTF8='1'
    & .\\.venv\\Scripts\\python.exe -X utf8 tests\\acceptance\\run_s2_acceptance.py

读取 tests/acceptance/_tmp/current_run_id.txt 决定快照与产物目录（由 freeze_snapshot.py 写入）。
只启动/停止自己拉起的进程；只写 tests/acceptance/_tmp/<run_id>/；不触碰 instance/ 与业务库。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _guard  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ACC = ROOT / "tests" / "acceptance"
ATTEMPTS = ACC / "_tmp" / "attempts"
SNAP_ID = os.environ.get("S2D_SNAPSHOT_ID") or "s2d_20261009_231628"   # 显式固定，不按目录序择新
PORT = int(os.environ.get("S2D_PORT", "5095"))
BASE = f"http://127.0.0.1:{PORT}"
# 以下路径在 main() 通过守卫后赋值（前置校验失败即退出，绝不先建目录/删库）
SNAP = Path()
SNAP_CONTRACT = Path()
TMP = Path()
DB = Path()
LOG = Path()
SERVER_LOG = Path()

results: list[tuple[str, str, str]] = []
lines: list[str] = []


def log(text: str = "") -> None:
    lines.append(text)
    print(text, flush=True)


def check(cid: str, ok: bool | None, detail: str) -> None:
    state = "PASS" if ok is True else ("FAIL" if ok is False else "INFO")
    results.append((cid, state, detail))
    log(f"[{state}] {cid}: {detail}")


def http(method: str, path: str, body: bytes | None = None, ctype: str | None = None, timeout: int = 25):
    req = urllib.request.Request(BASE + path, data=body, method=method)
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
    body = json.dumps(obj or {}).encode("utf-8")
    return http("POST", path, body=body, ctype="application/json; charset=utf-8")


def jpatch(path: str, obj: dict):
    body = json.dumps(obj).encode("utf-8")
    return http("PATCH", path, body=body, ctype="application/json; charset=utf-8")


def rows(sql: str, params: tuple = ()) -> list[dict]:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        got = [dict(r) for r in con.execute(sql, params).fetchall()]
    except sqlite3.Error as exc:
        got = [{"__error__": str(exc)}]
    con.close()
    return got


BIZ = ["candidate", "demand_signal", "evidence", "supply_offer", "cost_item", "gate_review", "review_item",
       "import_batch", "run_record", "idempotency_key", "draft", "feedback"]


def counts() -> dict:
    out = {}
    for table in BIZ:
        got = rows(f"SELECT COUNT(*) AS n FROM {table}")
        out[table] = got[0].get("n") if got and "n" in got[0] else None
    return out


def start_server(tag: str):
    env = os.environ.copy()
    env.update({"APP_DB_PATH": str(DB), "APP_PORT": str(PORT), "APP_HOST": "127.0.0.1",
                "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"})
    handle = open(SERVER_LOG, "ab")
    proc = subprocess.Popen([sys.executable, "-m", "app"], cwd=str(SNAP), env=env,
                            stdout=handle, stderr=subprocess.STDOUT)
    for _ in range(80):
        time.sleep(0.5)
        try:
            status, payload, _ = http("GET", "/api/health", timeout=2)
            if status == 200:
                return proc, payload
        except Exception:
            pass
    return proc, None


def stop_server(proc) -> int:
    if proc.poll() is None:
        proc.terminate()
    try:
        return proc.wait(timeout=10)
    except Exception:
        proc.kill()
        return proc.wait(timeout=10)


SNAP_CONTRACT = SNAP / "docs" / "design" / "CONTRACT.md"


def extract_blocks() -> tuple[str, list[str], str, dict]:
    text = SNAP_CONTRACT.read_text(encoding="utf-8")
    csv_blocks = re.findall(r"```csv\n(.*?)```", text, re.S)
    positive, header = None, None
    for block in csv_blocks:
        parsed = list(csv.reader(io.StringIO(block.strip())))
        if parsed and "title" in parsed[0] and "data_origin" in parsed[0]:
            if positive is None or len(parsed[0]) > len(header or []):
                positive, header = block.strip(), parsed[0]
    json_block = None
    for block in re.findall(r"```json\n(.*?)```", text, re.S):
        if "title" in block and "data_origin" in block:
            json_block = block.strip()
            break
    base = dict(zip(header, next(csv.reader(io.StringIO(positive.splitlines()[1])))))
    return positive + "\n", header, json_block, base


def csv_text(header: list[str], row: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerow([row.get(col, "") for col in header])
    return buf.getvalue()


def main() -> int:
    global SNAP, SNAP_CONTRACT, TMP, DB, LOG, SERVER_LOG
    try:
        snap_root = _guard.snapshot_root()                        # 默认 _snapshots；env 覆盖仅 _tmp 之下
        pointer = _guard.pointer_path()
        snap_id = os.environ.get("S2D_SNAPSHOT_ID") or (_guard.read_pointer(pointer) if pointer.exists() else SNAP_ID)
        SNAP = _guard.resolve_under(snap_root, snap_id)           # 显式 ID + 批准根下一层（含链接核对）
        provenance = _guard.preflight(SNAP, snap_root / f"{SNAP.name}.manifest.sha256")
        if not _guard.port_free(PORT):
            raise _guard.GuardError(f"端口 {PORT} 被占用；不结束他人进程，直接失败")
        TMP = _guard.attempt_dir(ATTEMPTS)                        # 独占创建新 attempt，不覆盖既有
    except _guard.GuardError as exc:
        print(f"[FAIL] 前置守卫拒绝，未创建任何产物：{exc}")
        return 1
    except FileExistsError as exc:
        print(f"[FAIL] attempt 目录已存在，拒绝覆盖：{exc}")
        return 1
    DB = TMP / "app.db"                                           # 干净库：新目录内，无 unlink 旧库
    LOG = TMP / "acceptance_log.txt"
    SERVER_LOG = TMP / "server.log"
    SNAP_CONTRACT = SNAP / "docs" / "design" / "CONTRACT.md"
    log(f"# S2-D 整链路独立验收 {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    log(f"snapshot={SNAP.name} attempt={TMP.name} db={DB} port={PORT}")
    log(f"来源探针（PYTHONDONTWRITEBYTECODE=1）= {provenance}")
    log(f"python={sys.version.split()[0]} sqlite={sqlite3.sqlite_version}")

    net = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="replace")
    busy = [ln.strip() for ln in net.stdout.splitlines() if f":{PORT}" in ln and "LISTENING" in ln.upper()]
    if busy:
        check("PORT-FREE", False, f"端口 {PORT} 已被占用（不结束他人进程）：{busy}")
        return 1
    check("PORT-FREE", True, f"端口 {PORT} 空闲")

    positive_csv, header, json_block, base_row = extract_blocks()
    check("FIXTURE", len(header) == 38, f"快照内契约 §4.7 正例列数={len(header)}，JSON 正例存在={bool(json_block)}")

    proc, health = start_server("first")
    if health is None:
        check("SERVER", False, f"服务未就绪，见 {SERVER_LOG}")
        stop_server(proc)
        return 1
    log("服务已启动（cwd=快照目录）")

    try:
        # ---------- 1) 基础 ----------
        check("S2-01-health", sorted(health.keys()) == ["ok", "schema_version", "time"] and health["schema_version"] == 2,
              f"GET /api/health -> {json.dumps(health, ensure_ascii=False)}")
        net2 = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="replace")
        listen = [ln.strip() for ln in net2.stdout.splitlines() if f":{PORT}" in ln and "LISTENING" in ln.upper()]
        check("S2-01-netstat", bool(listen) and all(ln.split()[1].startswith("127.0.0.1") for ln in listen),
              f"本地地址={[ln.split()[1] for ln in listen]}")
        migrations = rows("SELECT version FROM schema_migrations ORDER BY version")
        tables = [r["name"] for r in rows("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        check("S2-01-schema", [m["version"] for m in migrations] == [1, 2] and len(tables) == 15,
              f"migrations={[m['version'] for m in migrations]} 表数={len(tables)}")
        seeds = rows("SELECT name, access_mode FROM source ORDER BY name")
        check("S2-01-seeds", len(seeds) == 4 and all(s["access_mode"] == "manual_import" for s in seeds),
              f"来源种子={json.dumps(seeds, ensure_ascii=False)}")
        st_e, pe, _ = http("GET", "/api/candidates?page=1&page_size=5")
        check("UI-empty0", st_e == 200 and (pe or {}).get("total") == 0 and (pe or {}).get("items") == [],
              f"空库列表 -> {st_e} total={(pe or {}).get('total')} items={(pe or {}).get('items')}")

        # ---------- 2) 导入 ----------
        c0 = counts()
        status, payload, _ = http("POST", f"/api/imports?format=csv&mode=atomic", body=positive_csv.encode("utf-8"),
                                  ctype="text/csv; charset=utf-8")
        records = {r["type"]: r["id"] for r in (payload or {}).get("rows", [{}])[0].get("records", [])}
        cand = records.get("candidate")
        c1 = counts()
        check("S2-03-csv38", status == 201 and cand and all(
            c1[t] == {"candidate": 1, "demand_signal": 1, "evidence": 2, "supply_offer": 1, "cost_item": 10}[t] for t in
            ["candidate", "demand_signal", "evidence", "supply_offer", "cost_item"]),
            f"POST 38 列正例 -> {status} counts={json.dumps((payload or {}).get('counts'), ensure_ascii=False)} "
            f"五表={ {t: c1[t] for t in ['candidate', 'demand_signal', 'evidence', 'supply_offer', 'cost_item']} }")

        st190, sc190, _ = http("GET", f"/api/candidates/{cand}/scenario?variant=base")
        check("S2-03-scenario190", st190 == 200 and (sc190 or {}).get("contribution_per_order_minor") == 190
              and (sc190 or {}).get("complete") is True,
              f"正例情景（任何改动之前）-> {st190} contribution={(sc190 or {}).get('contribution_per_order_minor')} "
              f"net={(sc190 or {}).get('net_per_order_minor')} complete={(sc190 or {}).get('complete')} "
              f"unknown={(sc190 or {}).get('unknown_components')}")

        if json_block:
            jrow = json.loads(json_block)
            status, payload, _ = http("POST", "/api/imports?format=json&mode=atomic",
                                      body=json.dumps(jrow, ensure_ascii=False).encode("utf-8"),
                                      ctype="application/json; charset=utf-8")
            j_cand = None
            for rec in (payload or {}).get("rows", [{}])[0].get("records", []) or []:
                if rec.get("type") == "candidate":
                    j_cand = rec.get("id")
            sale = rows("SELECT money_minor FROM cost_item WHERE candidate_id=? AND role='sale_price'", (j_cand,))
            check("S2-03-json-alias", status == 201 and sale and sale[0]["money_minor"] == 1990,
                  f"JSON 正例（_minor 别名）-> {status} sale_price_minor 落库={sale[0]['money_minor'] if sale else None}")

        c_before = counts()
        status, payload, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=positive_csv.encode("utf-8"),
                                  ctype="text/csv; charset=utf-8")
        c_after = counts()
        five = ["candidate", "demand_signal", "evidence", "supply_offer", "cost_item"]
        five_unchanged = all(c_before[t] == c_after[t] for t in five)
        check("S2-04-reimport", status == 201 and (payload or {}).get("counts", {}).get("duplicate_skipped") == 1
              and five_unchanged,
              f"同文件重导 -> {status} counts={(payload or {}).get('counts')} 五个业务表不变={five_unchanged}"
              f"（首跑该处曾打印全表比较故显示 False，原日志不改写）")

        variant = dict(base_row, demand_excerpt=(base_row.get("demand_excerpt") or "") + "（D 复核修订）")
        status, payload, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                                  body=csv_text(header, variant).encode("utf-8"), ctype="text/csv; charset=utf-8")
        superseded = rows("SELECT COUNT(*) AS n FROM demand_signal WHERE superseded_by IS NOT NULL")[0]["n"]
        check("S2-06-version", status == 201 and (payload or {}).get("counts", {}).get("version_added") == 1 and superseded == 1,
              f"改摘录重导 -> {status} version_added={(payload or {}).get('counts', {}).get('version_added')} superseded={superseded}")

        mini_src = ["title", "data_origin", "demand_source", "demand_url", "demand_excerpt", "demand_kind", "demand_native_id"]
        common = {"data_origin": "synthetic", "demand_excerpt": "D 复核：跨渠道与隔离样例", "demand_kind": "other"}
        s1, _, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                        body=csv_text(mini_src, dict(common, title="D-闲鱼同ID", demand_source="xianyu",
                                                     demand_url="https://example.com/demand/d-xy-1001",
                                                     demand_native_id="1001")).encode("utf-8"),
                        ctype="text/csv; charset=utf-8")
        s2, _, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                        body=csv_text(mini_src, dict(common, title="D-B站同ID", demand_source="bilibili",
                                                     demand_url="https://example.com/demand/d-bl-1001",
                                                     demand_native_id="1001")).encode("utf-8"),
                        ctype="text/csv; charset=utf-8")
        keys = [r["identity_key"] for r in rows("SELECT identity_key FROM candidate WHERE identity_key LIKE 'n:%1001' ORDER BY identity_key")]
        check("S2-05-crosschannel", s1 == 201 and s2 == 201 and keys == ["n:bilibili:1001", "n:xianyu:1001"],
              f"跨渠道同 native_id -> {s1}/{s2} 身份={keys}")

        real_row = dict(common, title="D-real 隔离", demand_source="xianyu", demand_url="https://real-fixture.invalid/demand/1",
                        demand_kind="other")
        real_row["data_origin"] = "real"
        real_row["demand_native_id"] = "1001"
        s3, p3, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                         body=csv_text(mini_src, real_row).encode("utf-8"), ctype="text/csv; charset=utf-8")
        real_keys = [r["identity_key"] for r in rows("SELECT identity_key FROM candidate WHERE identity_key LIKE 'n:xianyu:1001' ORDER BY data_origin")]
        check("S2-08-origin-isolation", s3 == 201 and len(real_keys) == 2,
              f"real/synthetic 同 native_id -> {s3} 同键不同 origin 候选={len(real_keys)}")

        bad = dict(base_row, title="D-原子坏行", demand_url="https://example.com/demand/d-bad-1", sale_price="-9.90")
        good = dict(base_row, title="D-原子好行", demand_url="https://example.com/demand/d-good-1", sale_price="9.90")
        body = csv_text(header, good) + csv_text(header, bad).split("\n", 1)[1]
        c_before = counts()
        status, payload, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=body.encode("utf-8"),
                                  ctype="text/csv; charset=utf-8")
        c_after = counts()
        reasons = [r["reason_code"] for r in rows("SELECT DISTINCT reason_code FROM import_row_result WHERE batch_id=?",
                                                  ((payload or {}).get("batch_id"),))] if payload else []
        biz_unchanged = all(c_before[t] == c_after[t] for t in ["candidate", "demand_signal", "evidence", "supply_offer", "cost_item"])
        check("S2-09-atomic", bool(status == 422 and (payload or {}).get("status") == "rejected" and biz_unchanged and reasons),
              f"atomic 坏行 -> {status} 业务表不变={biz_unchanged} 批次+{c_after['import_batch'] - c_before['import_batch']} 原因={reasons}")

        c_before = counts()
        gbk = ("title,data_origin,demand_source,demand_url,demand_excerpt,demand_kind\n"
               "D-编码核验,synthetic,xianyu,https://example.com/demand/d-gbk,中文摘录,other\n")
        status, payload, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=gbk.encode("gbk"),
                                  ctype="text/csv; charset=gbk")
        c_after = counts()
        check("S2-10-gbk", status == 400 and (payload or {}).get("error", {}).get("code") == "encoding_error"
              and all(c_before[t] == c_after[t] for t in BIZ),
              f"GBK -> {status} code={(payload or {}).get('error', {}).get('code')} 零写入={all(c_before[t] == c_after[t] for t in BIZ)}")

        c_before = counts()
        status, payload, _ = http("POST", "/api/imports?format=csv&mode=validate",
                                  body=csv_text(header, dict(base_row, title="D-validate", demand_url="https://example.com/demand/d-val")).encode("utf-8"),
                                  ctype="text/csv; charset=utf-8")
        c_after = counts()
        zero = all(c_before[t] == c_after[t] for t in BIZ)
        check("S2-29-validate", status == 200 and (payload or {}).get("saved") is False and zero,
              f"validate -> {status} saved={(payload or {}).get('saved')} 零写入（含批次/运行/幂等）={zero}")

        idem_row = dict(common, title="D-幂等", demand_source="xianyu", demand_url="https://example.com/demand/d-idem",
                        demand_kind="other")
        idem_body = csv_text(mini_src, idem_row).encode("utf-8")
        q = "format=csv&mode=atomic&client_ref=d-accept-1"
        i1, p1, _ = http("POST", f"/api/imports?{q}", body=idem_body, ctype="text/csv; charset=utf-8")
        i2, p2, _ = http("POST", f"/api/imports?{q}", body=idem_body, ctype="text/csv; charset=utf-8")
        i3, p3, _ = http("POST", f"/api/imports?{q}", body=csv_text(mini_src, dict(idem_row, demand_excerpt="异载荷")).encode("utf-8"),
                         ctype="text/csv; charset=utf-8")
        check("S2-27-idempotency", i1 == 201 and i2 == 200 and (p2 or {}).get("deduplicated") is True and i3 == 409,
              f"幂等 -> {i1}/{i2}(dedup={(p2 or {}).get('deduplicated')})/{i3}(code={(p3 or {}).get('error', {}).get('code')})")

        # ---------- 3) 四门槛 ----------
        status, detail, _ = http("GET", f"/api/candidates/{cand}")
        gates = (detail or {}).get("gates", {})
        check("S2-13-initial-pending", status == 200 and all(v == "unverified" for v in gates.values())
              and (detail or {}).get("derived_status") == "pending",
              f"初始门槛={gates} derived={(detail or {}).get('derived_status')}")
        evidences = (detail or {}).get("evidences", [])
        supplies = (detail or {}).get("supplies", [])
        demand_ev = next((e["id"] for e in evidences if e["evidence_type"] == "demand"), None)
        supply = supplies[0] if supplies else {}
        supply_id = supply.get("id")
        lic_ev = supply.get("license_evidence_id")

        # 反例 A：卖家宣传 → G1 应 422
        promo = dict(common, title="D-卖家宣传", demand_source="xianyu", demand_url="https://example.com/demand/d-promo",
                     demand_kind="seller_promo", demand_native_id="")
        _, pr_pl, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=csv_text(mini_src, promo).encode("utf-8"),
                           ctype="text/csv; charset=utf-8")
        promo_id = next((r["id"] for r in (pr_pl or {}).get("rows", [{}])[0].get("records", []) or []
                         if r.get("type") == "candidate"), None)
        pr_detail = http("GET", f"/api/candidates/{promo_id}")[1] if promo_id else {}
        promo_ev = next((e["id"] for e in (pr_detail or {}).get("evidences", []) if e["evidence_type"] == "demand"), None)
        st_g1_bad, pl_g1_bad, _ = jpost(f"/api/candidates/{promo_id}/gates/demand",
                                        {"status": "verified", "evidence_id": promo_ev})
        check("S2-14-g1-counterexample", st_g1_bad == 422,
              f"卖家宣传需求证据 -> G1={st_g1_bad} details={json.dumps((pl_g1_bad or {}).get('error', {}).get('details'), ensure_ascii=False)[:140]}")

        # 反例 B：许可 no / unknown / 未抽检 → G2 应 422
        bad_supplies = [
            ("no-resale", {"provider_name": "D-禁止转售", "provider_url": "https://example.com/supply/d-bad-1",
                           "commercial_allowed": "yes", "redistribute_allowed": "yes", "resale_allowed": "no",
                           "sample_checked": "partial", "sample_note": "D 复核抽样"}),
            ("unknown-license", {"provider_name": "D-许可未知", "provider_url": "https://example.com/supply/d-bad-2",
                                 "commercial_allowed": "unknown", "redistribute_allowed": "unknown",
                                 "resale_allowed": "unknown", "sample_checked": "partial", "sample_note": "D 复核抽样"}),
            ("no-sample", {"provider_name": "D-未抽检", "provider_url": "https://example.com/supply/d-bad-3",
                           "commercial_allowed": "yes", "redistribute_allowed": "yes", "resale_allowed": "yes",
                           "sample_checked": "none"}),
        ]
        g2_codes = []
        bad_sids = []
        for tag, sup in bad_supplies:
            sN, pN, _ = jpost(f"/api/candidates/{cand}/supplies", sup)
            sid = (pN or {}).get("id") or (pN or {}).get("supply_offer", {}).get("id")
            bad_sids.append(sid)
            stN, plN, _ = jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                                {"status": "verified", "supply_offer_id": sid, "evidence_id": lic_ev})
            g2_codes.append((tag, sN, stN, json.dumps((plN or {}).get("error", {}).get("details"), ensure_ascii=False)[:80]))
        check("S2-14-g2-counterexamples", all(c[2] == 422 for c in g2_codes), f"G2 反例={g2_codes}")

        # G3 反例（未补说明）+ 正路（按值+说明取代，避免丢值）
        cost_rows = rows("SELECT id, role, basis, value_kind, money_minor, rate_bp, minutes, hourly_rate_minor, period "
                         "FROM cost_item WHERE candidate_id=? AND is_active=1", (cand,))
        st_cost_reject, pl_cost_reject, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})
        fix_codes = []
        for row in cost_rows:
            payload_obj = {"assumption_note": "D 复核：示例域合成假设说明"}
            for key in ("value_kind", "money_minor", "rate_bp", "minutes", "hourly_rate_minor", "period"):
                if row[key] is not None:
                    payload_obj[key] = row[key]
            stf, _, _ = jpost(f"/api/cost-items/{row['id']}/supersede", payload_obj)
            fix_codes.append(stf)
        st_g2_default, pl_g2_default, _ = jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                                                {"status": "verified", "supply_offer_id": supply_id})
        gate_row = rows("SELECT evidence_id, expires_at, verified_by FROM gate_review WHERE candidate_id=? "
                        "AND gate='supply_distribution' ORDER BY seq DESC LIMIT 1", (cand,))
        check("S2-B-G2默认关联", st_g2_default == 200 and gate_row and gate_row[0]["evidence_id"] == lic_ev
              and gate_row[0]["verified_by"] == "user",
              f"G2 省略 evidence_id -> {st_g2_default} 落库 evidence_id={gate_row[0]['evidence_id'] if gate_row else None} "
              f"（条款证据={lic_ev}）expires_at={gate_row[0]['expires_at'] if gate_row else None}")

        st_g2, pl_g2, _ = jpost(f"/api/candidates/{cand}/gates/supply_distribution",
                                {"status": "verified", "supply_offer_id": supply_id, "evidence_id": lic_ev})
        st_g1, pl_g1, _ = jpost(f"/api/candidates/{cand}/gates/demand", {"status": "verified", "evidence_id": demand_ev})
        st_cost, pl_cost, _ = jpost(f"/api/candidates/{cand}/gates/cost", {"status": "verified"})
        st, pl, _ = jpost(f"/api/candidates/{cand}/evidences",
                          {"evidence_type": "platform_policy", "source_url": "https://example.com/policy/d-1",
                           "excerpt": "D 复核：平台虚拟商品发布条件摘录（合成）", "fact_kind": "fact"})
        policy_ev = (pl or {}).get("id") or (pl or {}).get("evidence", {}).get("id")
        st_plat_bad, pl_plat_bad, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                                            {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                                             "applies_to_version": "v9"})
        st_plat, pl_plat, _ = jpost(f"/api/candidates/{cand}/gates/platform_policy",
                                    {"status": "verified", "evidence_id": policy_ev, "applies_to_platform": "xianyu",
                                     "applies_to_version": supply.get("format_version") or "v1"})
        st, detail, _ = http("GET", f"/api/candidates/{cand}")
        check("S2-17-testable", (detail or {}).get("derived_status") == "testable"
              and all(v == "verified" for v in (detail or {}).get("gates", {}).values()),
              f"G1={st_g1} G2={st_g2} G3 无说明={st_cost_reject}(details={json.dumps((pl_cost_reject or {}).get('error', {}).get('details'), ensure_ascii=False)[:80]}) "
              f"G3 补说明={st_cost} 取代={fix_codes} G4 版本不符={st_plat_bad} G4 正确={st_plat} "
              f"derived={(detail or {}).get('derived_status')} gates={(detail or {}).get('gates')}")

        st_foreign, pl_foreign, _ = jpost(f"/api/candidates/{cand}/gates/cost",
                                          {"status": "verified", "supply_offer_id": bad_sids[0] if bad_sids else None})
        check("S2-B-异货源G3G4", st_foreign == 422,
              f"G3 传非当前 G2 货源 -> {st_foreign} details={json.dumps((pl_foreign or {}).get('error', {}).get('details'), ensure_ascii=False)[:120]}")

        # ---------- 4) 情景 ----------
        st, sc, _ = http("GET", f"/api/candidates/{cand}/scenario?variant=base")
        check("S2-03-scenario190-post-gate", st == 200 and (sc or {}).get("contribution_per_order_minor") == 190,
              f"正例情景 -> {st} contribution={(sc or {}).get('contribution_per_order_minor')} "
              f"net={(sc or {}).get('net_per_order_minor')} complete={(sc or {}).get('complete')}")

        def import_scenario(title: str, extra: dict) -> tuple[int, dict | None]:
            row = {"title": title, "data_origin": "synthetic", "demand_source": "xianyu",
                   "demand_url": f"https://example.com/demand/{abs(hash(title)) % 10**8}", "demand_excerpt": "D 情景样例",
                   "demand_kind": "other", "sale_price": "10.00", "platform_fee_bp": "0", "payment_fee_bp": "0",
                   "acquisition_cost": "0", "refund_rate_bp": "0", "procurement_unit_cost": "0",
                   "procurement_cost": "0", "procurement_recurring_cost": "0", "procurement_period": "monthly",
                   "other_cost": "0", "manual_minutes": "0", "manual_hourly_rate": "3000"}
            row.update(extra)
            cols = list(dict.fromkeys(list(row.keys())))
            st, pl, _ = http("POST", "/api/imports?format=csv&mode=atomic", body=csv_text(cols, row).encode("utf-8"),
                             ctype="text/csv; charset=utf-8")
            cid = None
            for rec in (pl or {}).get("rows", [{}])[0].get("records", []) or []:
                if rec.get("type") == "candidate":
                    cid = rec.get("id")
            if not cid:
                return st, None
            st2, sc2, _ = http("GET", f"/api/candidates/{cid}/scenario?variant=base")
            return st2, sc2

        _, s800 = import_scenario("D-情景800", {"procurement_unit_cost": "2.00"})
        check("S2-20-scenario800", (s800 or {}).get("contribution_per_order_minor") == 800
              and (s800 or {}).get("net_per_order_minor") == 800,
              f"逐单采购 200 -> contribution={(s800 or {}).get('contribution_per_order_minor')} net={(s800 or {}).get('net_per_order_minor')}")

        _, sneg = import_scenario("D-情景负", {"procurement_unit_cost": "12.00"})
        check("S2-19-negative", (sneg or {}).get("contribution_per_order_minor") == -200,
              f"逐单成本 1200 -> contribution={(sneg or {}).get('contribution_per_order_minor')}")

        _, sunk = import_scenario("D-情景未知", {"payment_fee_bp": ""})
        check("S2-12-unknown-not-zero", (sunk or {}).get("contribution_per_order_minor") is None
              and "payment_fee" in ((sunk or {}).get("unknown_components") or []),
              f"支付费未知 -> contribution={(sunk or {}).get('contribution_per_order_minor')} "
              f"unknown={(sunk or {}).get('unknown_components')}")

        _, sone = import_scenario("D-情景买断", {"procurement_cost": "20.00"})
        check("S2-21-onetime-gap", (sone or {}).get("net_per_order_minor") is None
              and (sone or {}).get("fixed_cost_gap_minor") == 2000,
              f"一次性 2000 -> net={(sone or {}).get('net_per_order_minor')} gap={(sone or {}).get('fixed_cost_gap_minor')}")

        _, smon_pos = import_scenario("D-情景月度正", {"procurement_recurring_cost": "100.00", "procurement_period": "monthly"})
        _, smon_zero = import_scenario("D-情景月度0", {"procurement_recurring_cost": "0", "procurement_period": "monthly"})
        _, sq_pos = import_scenario("D-情景季度正", {"procurement_recurring_cost": "300.00", "procurement_period": "quarterly"})
        _, sq_zero = import_scenario("D-情景季度0", {"procurement_recurring_cost": "0", "procurement_period": "quarterly"})
        _, sy_zero = import_scenario("D-情景年度0", {"procurement_recurring_cost": "0", "procurement_period": "yearly"})
        _, sy_pos = import_scenario("D-情景年度正", {"procurement_recurring_cost": "1200.00", "procurement_period": "yearly"})
        check("S2-21-recurring", (smon_pos or {}).get("net_per_order_minor") is None
              and (smon_zero or {}).get("net_per_order_minor") is not None
              and (sq_pos or {}).get("net_per_order_minor") is None
              and (sq_pos or {}).get("recurring_monthly_total_minor") is None
              and (sy_pos or {}).get("net_per_order_minor") is None
              and (sy_pos or {}).get("recurring_monthly_total_minor") is None
              and (sq_zero or {}).get("net_per_order_minor") is not None
              and (sy_zero or {}).get("net_per_order_minor") is not None,
              f"月度正={(smon_pos or {}).get('net_per_order_minor')} 月度0={(smon_zero or {}).get('net_per_order_minor')} "
              f"季度正={(sq_pos or {}).get('net_per_order_minor')}/月额={(sq_pos or {}).get('recurring_monthly_total_minor')} "
              f"年度正={(sy_pos or {}).get('net_per_order_minor')}/月额={(sy_pos or {}).get('recurring_monthly_total_minor')} "
              f"季度0={(sq_zero or {}).get('net_per_order_minor')} 年度0={(sy_zero or {}).get('net_per_order_minor')}")

        # ---------- 5) 草稿与边界 ----------
        st, dr, _ = jpost(f"/api/candidates/{cand}/drafts", {"kind": "listing_copy", "method": "template"})
        draft_id = (dr or {}).get("id")
        body_text = (dr or {}).get("body") or ""
        st_model, _, _ = jpost(f"/api/candidates/{cand}/drafts", {"kind": "listing_copy", "method": "model_assisted"})
        st_patch, pl_patch, _ = jpatch(f"/api/drafts/{draft_id}", {"status": "final"}) if draft_id else (0, None, b"")
        send_404 = http("POST", f"/api/candidates/{cand}/send", body=b"{}", ctype="application/json")[0]
        pay_404 = http("POST", "/api/payments", body=b"{}", ctype="application/json")[0]
        buy_404 = http("POST", "/api/purchase", body=b"{}", ctype="application/json")[0]
        check("S2-24-draft", st == 201 and draft_id and st_model == 422 and st_patch == 200 and send_404 == 404
              and ("【待" in body_text or "未核验" in body_text),
              f"template={st} id={bool(draft_id)} model_assisted={st_model} patch={st_patch} /send={send_404} "
              f"占位标记={'【待' in body_text or '未核验' in body_text} body 头={body_text[:60]!r}")
        check("S2-22-no-purchase", pay_404 == 404 and buy_404 == 404,
              f"采购/付款端点 -> /api/payments={pay_404} /api/purchase={buy_404}")

        # ---------- 6) 反馈 ----------
        st_sale, sale_fb, _ = jpost(f"/api/candidates/{cand}/feedback",
                                    {"kind": "sale", "order_ref": "D-ORDER-1", "amount_minor": 10000, "quantity": 1})
        sale_id = (sale_fb or {}).get("id")
        st_ref_bad, _, _ = jpost(f"/api/candidates/{cand}/feedback", {"kind": "refund", "amount_minor": 10000, "refund_state": "pending"})
        st_ref_ok, ref_fb, _ = jpost(f"/api/candidates/{cand}/feedback",
                                     {"kind": "refund", "order_ref": "D-ORDER-1", "related_feedback_id": sale_id,
                                      "amount_minor": 10000, "refund_state": "pending"})
        ref_id = (ref_fb or {}).get("id")
        st_settle, pl_settle, _ = jpatch(f"/api/feedback/{ref_id}", {"refund_state": "settled"}) if ref_id else (0, None, b"")
        st_settle2, _, _ = jpatch(f"/api/feedback/{ref_id}", {"refund_state": "settled"}) if ref_id else (0, None, b"")
        st_pred, pl_pred, _ = jpatch(f"/api/feedback/{sale_id}", {"predicted_net_per_order_minor": 1}) if sale_id else (0, None, b"")
        st_time, tm_fb, _ = jpost(f"/api/candidates/{cand}/feedback",
                                  {"kind": "manual_time", "actual_minutes": 20, "actual_hourly_rate_minor": 3000})
        tm_id = (tm_fb or {}).get("id")
        st_time2, _, _ = jpatch(f"/api/feedback/{tm_id}", {"actual_minutes": 25}) if tm_id else (0, None, b"")
        fb_rows = rows("SELECT kind, predicted_net_per_order_minor, actual_net_per_order_minor, actual_complete, actual_minutes FROM feedback WHERE candidate_id=? ORDER BY created_at", (cand,))
        sale_row = next((r for r in fb_rows if r["kind"] == "sale"), {})
        check("S2-25-feedback", st_sale == 201 and st_ref_bad == 422 and st_ref_ok == 201 and st_settle == 200
              and st_settle2 == 200 and st_pred == 422 and st_time == 201 and st_time2 == 200
              and sale_row.get("actual_net_per_order_minor") is None and sale_row.get("actual_complete") is None,
              f"sale={st_sale}(predicted={sale_row.get('predicted_net_per_order_minor')}) 退款裸提交={st_ref_bad} "
              f"退款正确={st_ref_ok} 结算={st_settle}/{st_settle2} 改预测={st_pred}(code={(pl_pred or {}).get('error', {}).get('code')}) "
              f"人工={st_time}/{st_time2} 实际净值={sale_row.get('actual_net_per_order_minor')} actual_complete={sale_row.get('actual_complete')}")

        # ---------- 降级：失效 → 零写 → 复核 → 重核 ----------
        before_get = counts()
        st, d1, _ = http("GET", f"/api/candidates/{cand}")
        st, d2, _ = http("GET", f"/api/candidates/{cand}")
        after_get = counts()
        st_inv, pl_inv, _ = jpost(f"/api/evidences/{demand_ev}/invalidate", {"invalid_reason": "D 复核：证据失效演练"})
        st, d3, _ = http("GET", f"/api/candidates/{cand}")
        st_rc1, rc1, _ = jpost("/api/runs/recompute")
        st_rc2, rc2, _ = jpost("/api/runs/recompute")
        reviews = rows("SELECT id, kind, status, blocking FROM review_item WHERE status='open'")
        st_res, _, _ = jpost(f"/api/review-items/{reviews[0]['id']}/resolve", {"status": "dismissed", "note": "D 复核处理"}) if reviews else (0, None, b"")
        st, d4, _ = http("GET", f"/api/candidates/{cand}")
        check("S2-15-downgrade", before_get == after_get and st_inv == 200 and st_rc1 == 200 and st_rc2 == 200
              and st_res == 200
              and (d3 or {}).get("gates", {}).get("demand") == "expired" and (d3 or {}).get("derived_status") == "stale"
              and reviews and (d4 or {}).get("gates", {}).get("demand") == "expired" and (d4 or {}).get("derived_status") == "stale",
              f"GET 零写={before_get == after_get} 失效={st_inv} 降级后 gates.demand={(d3 or {}).get('gates', {}).get('demand')} "
              f"derived={(d3 or {}).get('derived_status')} recompute={st_rc1}/{st_rc2} dismiss={st_res} "
              f"dismiss 后仍={(d4 or {}).get('derived_status')}")

        # ---------- UI（HTTP/HTML，无浏览器） ----------
        st_home, _, html_home = http("GET", "/")
        check("UI-P1", st_home == 200 and "今日工作台" in html_home.decode("utf-8", "replace"),
              f"GET / -> {st_home} bytes={len(html_home)}")
        for path, name in (("/import", "UI-P3"), ("/ops", "UI-P4")):
            st_p, _, raw = http("GET", path)
            check(name, st_p == 200, f"GET {path} -> {st_p} bytes={len(raw)}")
        st_det, _, html_det = http("GET", f"/opportunity/{cand}")
        check("UI-P2", st_det == 200, f"GET /opportunity/<id> -> {st_det} bytes={len(html_det)}")
        st_404, _, html_404 = http("GET", "/opportunity/c_missing_id")
        check("UI-404", st_404 == 404, f"GET 不存在候选 -> {st_404}")

        xss = dict(common, title="<script>alert(1)</script>", demand_source="xianyu",
                   demand_url="https://example.com/demand/d-xss", demand_excerpt="<img src=x onerror=alert(1)>",
                   demand_kind="other", demand_native_id="")
        xss["data_origin"] = "synthetic"
        xss["demand_kind"] = "other"
        xss["demand_native_id"] = ""
        http("POST", "/api/imports?format=csv&mode=atomic", body=csv_text(mini_src, xss).encode("utf-8"),
             ctype="text/csv; charset=utf-8")
        st_h, _, html_x = http("GET", "/?q=script")
        st_xo, _, html_xo = http("GET", f"/opportunity/{rows('SELECT id FROM candidate WHERE title LIKE ?', ('%script%',))[0]['id']}")
        text_x = html_x.decode("utf-8", "replace")
        text_xo = html_xo.decode("utf-8", "replace")
        check("UI-escape", st_xo == 200 and "<script>alert(1)</script>" not in text_xo and "<img src=x" not in text_xo
              and "&lt;script&gt;" in text_xo,
              f"服务端渲染的机会页 -> {st_xo} 原样 script 标签={'<script>alert(1)</script>' in text_xo} "
              f"原样 img 标签={'<img src=x' in text_xo} 转义出现={'&lt;script&gt;' in text_xo}；"
              f"首页为 JS 渲染（titles 不在 HTML），其含原样 script 标签={'<script>alert(1)</script>' in text_x}")

        st_u, _, html_u = http("GET", f"/opportunity/{rows('SELECT id FROM candidate WHERE title LIKE ?', ('D-情景未知',))[0]['id']}")
        text_u = html_u.decode("utf-8", "replace")
        check("UI-unknown0", "未知" in text_u and ("¥0.00" in text_u or "0.00" in text_u),
              f"未知候选详情 -> 未知标记={'未知' in text_u} 零标记={'¥0.00' in text_u}")

        st_src, _, html_src = http("GET", "/import")
        text_src = html_src.decode("utf-8", "replace")
        check("UI-sources", st_src == 200 and "人工导入" in text_src,
              f"/import 来源三态 -> {st_src} 人工导入标记={'人工导入' in text_src}")

        st_pg, pg, _ = http("GET", "/api/candidates?page=2&page_size=2")
        st_flt, flt, _ = http("GET", "/api/candidates?status=stale")
        check("UI-paging-pool", st_pg == 200 and len((pg or {}).get("items", [])) == 2 and (pg or {}).get("page") == 2
              and (flt or {}).get("total", 0) >= 1,
              f"分页 page=2&size=2 -> items={len((pg or {}).get('items', []))} total={(pg or {}).get('total')}；"
              f"分池 status=stale -> total={(flt or {}).get('total')}")

        node = shutil.which("node") or os.environ.get("NODE_BIN")
        mirror = TMP / "mirror"
        for rel in ("app/static/ui.js", "tests/ui/ui_behavior.mjs", "tests/ui/__init__.py"):
            if (SNAP / rel).exists():
                dst = mirror / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(SNAP / rel, dst)
        mirror_ok = all(hashlib.sha256((mirror / r).read_bytes()).hexdigest()
                        == hashlib.sha256((SNAP / r).read_bytes()).hexdigest()
                        for r in ("app/static/ui.js", "tests/ui/ui_behavior.mjs") if (SNAP / r).exists())
        artifact = mirror / "tests" / "ui" / "_tmp" / "feedback_payloads.json"
        captured = None
        if node and mirror_ok:
            proc_n = subprocess.run([node, str(mirror / "tests" / "ui" / "ui_behavior.mjs")], cwd=str(mirror),
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            check("UI-JS-node-harness", proc_n.returncode == 0 and artifact.exists(),
                  f"镜像内 node（模拟 DOM，非浏览器；产物只落 _tmp 镜像）exit={proc_n.returncode} "
                  f"artifact={artifact.exists()} tail={(proc_n.stdout or '').strip().splitlines()[-2:]}")
            if artifact.exists():
                raw_art = json.loads(artifact.read_text(encoding="utf-8"))
                if isinstance(raw_art, dict):
                    entry = raw_art.get("refund") or {}
                    captured = entry.get("payload") if isinstance(entry, dict) else None
                else:
                    captured = next((it for it in (raw_art or []) if isinstance(it, dict) and it.get("kind") == "refund"), None)
        else:
            check("UI-JS-node-harness", False,
                  f"node 缺失或镜像哈希不一致（node={bool(node)} mirror_ok={mirror_ok}）：按失败处理，不跳过")
        # 桥接检查独立于 harness 成败（不在失败分支内）：拿到载荷就桥接，拿不到即 FAIL
        if captured:
            real = dict(captured)
            real.update({"related_feedback_id": sale_id, "order_ref": "D-ORDER-1", "refund_state": "pending"})
            for key in ("candidate_id", "candidateId"):
                real.pop(key, None)
            st_js, pl_js, _ = jpost(f"/api/candidates/{cand}/feedback", real)
            check("UI-JS-refund-realHTTP", st_js == 201,
                  f"JS 捕获退款载荷经真实 HTTP -> {st_js}：金额 {captured.get('amount_minor')} 保留，"
                  f"关联 ID/order_ref/refund_state 经适配后提交（非原样字节）body={json.dumps(pl_js, ensure_ascii=False)[:100]}")
        else:
            check("UI-JS-refund-realHTTP", False,
                  f"未取得 refund 载荷（node={bool(node)} mirror_ok={mirror_ok} artifact={artifact.exists()}）：FAIL，不跳过")

        # ---------- 重启后一致性 ----------
        pre = counts()
        pre_pred = rows("SELECT predicted_net_per_order_minor FROM feedback WHERE kind='sale' ORDER BY created_at LIMIT 1")
        stop_server(proc)
        proc2, health2 = start_server("second")
        post = counts()
        st_after, detail_after, _ = http("GET", f"/api/candidates/{cand}")
        post_pred = rows("SELECT predicted_net_per_order_minor FROM feedback WHERE kind='sale' ORDER BY created_at LIMIT 1")
        check("S2-32-restart", health2 is not None and pre == post
              and (detail_after or {}).get("derived_status") == "stale" and pre_pred == post_pred,
              f"重启后 health={bool(health2)} 计数一致={pre == post} 候选状态={(detail_after or {}).get('derived_status')} "
              f"预测快照一致={pre_pred == post_pred}")

        must_ids = ["S2-01-health", "S2-01-schema", "S2-01-seeds", "S2-03-csv38", "S2-03-scenario190",
                    "S2-04-reimport", "S2-06-version", "S2-09-atomic", "S2-10-gbk", "S2-27-idempotency",
                    "S2-29-validate", "S2-13-initial-pending", "S2-14-g1-counterexample", "S2-14-g2-counterexamples",
                    "S2-17-testable", "S2-12-unknown-not-zero", "S2-20-scenario800", "S2-19-negative",
                    "S2-21-onetime-gap", "S2-21-recurring", "S2-24-draft", "S2-22-no-purchase", "S2-25-feedback",
                    "S2-15-downgrade", "UI-P1", "UI-P2", "UI-P3", "UI-P4", "UI-404", "UI-escape", "UI-unknown0",
                    "UI-sources", "UI-paging-pool", "UI-JS-node-harness", "UI-JS-refund-realHTTP", "S2-32-restart"]
        executed = {r[0] for r in results}
        missing = [i for i in must_ids if i not in executed]
        infos = [r[0] for r in results if r[1] == "INFO"]
        check("SELF-COVERAGE", not missing and not infos,
              f"expected 必测 ID 全部执行且无 INFO；actual 缺失={missing or 'none'} INFO={infos or 'none'}"
              f"（漏检不得 exit 0）")

        log("")
        log("# 汇总")
        for cid, state, _ in results:
            log(f"{state}\t{cid}")
        fails = [r for r in results if r[1] == "FAIL"]
        log(f"合计 {len(results)} 项：PASS {sum(1 for r in results if r[1] == 'PASS')} / "
            f"FAIL {len(fails)} / INFO {sum(1 for r in results if r[1] == 'INFO')}")
        if LOG.name:                      # 守卫早退时 LOG 为空 Path（str(Path())=='.'），用 name 判定
            LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0 if not fails else 1
    finally:
        stop_server(proc)
        if "proc2" in dir():
            stop_server(proc2)
        try:
            leftover = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="replace").stdout
            still = [ln.strip() for ln in leftover.splitlines() if f":{PORT}" in ln and "LISTENING" in ln.upper()]
            log(f"清理核对：端口 {PORT} 残留监听={still or 'none'}")
        except Exception:
            pass
        if LOG.name:                      # 守卫早退时 LOG 为空 Path（str(Path())=='.'），用 name 判定
            LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
