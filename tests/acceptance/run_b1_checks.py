"""S2-B1 独立复核脚本（D 角色，只读使用 app/**，写入仅限 tests/acceptance/**）。

复跑（工作区根目录）：
    $env:PYTHONUTF8='1'
    & .\.venv\Scripts\python.exe -X utf8 tests\acceptance\run_b1_checks.py

设计要点：
- 使用独立库 tests/acceptance/_tmp/b1_check.db 与端口 5051，不触碰 instance/ 与 B 的 5000。
- 每一步记录命令/请求、退出码或 HTTP 状态、决定性输出到 tests/acceptance/_tmp/b1_check_log.txt。
- 不导入应用模块、不修改 app/**；仅通过 HTTP 与 sqlite3 只读查询观测行为。
"""

from __future__ import annotations

import csv
import hashlib
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

ROOT = Path(__file__).resolve().parents[2]
ACC = ROOT / "tests" / "acceptance"
TMP = ACC / "_tmp"
FIX = ACC / "fixtures"
PORT = int(os.environ.get("B1_CHECK_PORT", "5051"))
DB = TMP / "b1_check.db"
LOG = TMP / "b1_check_log.txt"
CONTRACT = ROOT / "docs" / "design" / "CONTRACT.md"
BIZ = ["candidate", "demand_signal", "evidence", "supply_offer", "cost_item"]
EXTRA = ["import_batch", "run_record", "idempotency_key", "review_item", "gate_review"]

results: list[tuple[str, str, str]] = []
_loglines: list[str] = []


def log(line: str = "") -> None:
    _loglines.append(line)
    print(line, flush=True)


def check(cid: str, ok: bool | None, detail: str) -> None:
    state = "PASS" if ok is True else ("FAIL" if ok is False else "MANUAL")
    results.append((cid, state, detail))
    log(f"[{state}] {cid}: {detail}")


def http(method: str, path: str, body: bytes | None = None, ctype: str | None = None, timeout: int = 20):
    url = f"http://127.0.0.1:{PORT}{path}"
    req = urllib.request.Request(url, data=body, method=method)
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


def counts() -> dict:
    out: dict = {}
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for table in BIZ + EXTRA + ["source", "sqlite_master"]:
        try:
            out[table] = con.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        except sqlite3.Error:
            out[table] = None
    con.close()
    return out


def rows(db: Path, sql: str, params: tuple = ()) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        got = [dict(r) for r in con.execute(sql, params).fetchall()]
    except sqlite3.Error as exc:
        got = [{"__error__": str(exc)}]
    con.close()
    return got


def env_for_server() -> dict:
    env = os.environ.copy()
    env["APP_DB_PATH"] = str(DB)
    env["APP_PORT"] = str(PORT)
    env["APP_HOST"] = "127.0.0.1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def start_server(tag: str, env: dict):
    handle = open(TMP / f"server_{tag}.log", "ab")
    proc = subprocess.Popen([sys.executable, "-m", "app"], cwd=str(ROOT), env=env,
                            stdout=handle, stderr=subprocess.STDOUT)
    payload = None
    for _ in range(60):
        time.sleep(0.5)
        try:
            status, payload, _ = http("GET", "/api/health", timeout=2)
            if status == 200:
                break
            payload = None
        except Exception:
            payload = None
    return proc, payload, handle.name


def stop_server(proc) -> int:
    if proc.poll() is None:
        proc.terminate()
    try:
        code = proc.wait(timeout=8)
    except Exception:
        proc.kill()
        code = proc.wait(timeout=8)
    return code


def sha_map() -> dict:
    out = {}
    for base in ("app", "tests"):
        for path in sorted((ROOT / base).rglob("*.py")):
            parts = path.relative_to(ROOT).parts
            if "_tmp" in parts or ".venv" in parts:
                continue
            out[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for extra in ("requirements.txt",):
        target = ROOT / extra
        if target.exists():
            out[extra] = hashlib.sha256(target.read_bytes()).hexdigest()
    return out


def csv_text(header: list[str], row: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerow([row.get(col, "") for col in header])
    return buf.getvalue()


def post_csv(text: str, query: str, name: str):
    payload = text.encode("utf-8")
    return http("POST", f"/api/imports?{query}", body=payload, ctype="text/csv; charset=utf-8")


def main() -> int:
    TMP.mkdir(parents=True, exist_ok=True)
    FIX.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    log(f"# S2-B1 独立复核 {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    log(f"python={sys.version.split()[0]} sqlite={sqlite3.sqlite_version} cwd={ROOT} db={DB} port={PORT}")
    try:
        import flask  # noqa: F401  (仅记录实际安装版本)
        log(f"flask_importable={flask.__version__}")
    except Exception as exc:  # pragma: no cover
        log(f"flask_importable=FAILED {exc}")

    # 1) 起始哈希（并发 B2 可能改动 app/**）
    start = sha_map()
    (TMP / "app_hashes_repro_start.txt").write_text(
        "\n".join(f"{v}  {k}" for k, v in start.items()) + "\n", encoding="utf-8")
    log(f"STEP1 起始哈希: app/tests/requirements 共 {len(start)} 个文件写入 _tmp/app_hashes_repro_start.txt")

    # 2) 正例夹具：从已冻结契约 §4.7 抽取
    contract_text = CONTRACT.read_text(encoding="utf-8")
    blocks = re.findall(r"```csv\n(.*?)```", contract_text, re.S)
    positive = None
    widths = []
    for block in blocks:
        parsed = list(csv.reader(io.StringIO(block.strip())))
        if parsed and "title" in parsed[0] and "data_origin" in parsed[0]:
            widths.append(len(parsed[0]))
            if positive is None or len(parsed[0]) > len(positive[1][0]):
                positive = (block.strip(), parsed)
    if positive is None:
        check("FIXTURE", False, "未能在 CONTRACT.md §4.7 找到含 title/data_origin 的 CSV 块")
        return 1
    header, parsed_rows = positive[1][0], positive[1][1:]
    fixture_text = positive[0] + "\n"
    (FIX / "contract_4_7_positive.csv").write_text(fixture_text, encoding="utf-8")
    check("FIXTURE-38", len(header) == 38, f"契约正例列数={len(header)} 数据行={len(parsed_rows)} 所有CSV块表头宽度={widths}")
    base_row = dict(zip(header, parsed_rows[0]))

    env = env_for_server()
    proc, health, server_log = start_server("first", env)
    if health is None:
        check("S2-HEALTH", False, f"服务未能在 20s 内就绪；server log={server_log}")
        stop_server(proc)
        (TMP / "b1_check_log.txt").write_text("\n".join(_loglines) + "\n", encoding="utf-8")
        return 1
    log(f"STEP2 服务就绪 server_log={server_log}")

    # 2) health + netstat
    status, payload, _ = http("GET", "/api/health")
    check("S2-HEALTH", status == 200 and payload.get("ok") is True and payload.get("schema_version") == 1,
          f"GET /api/health -> {status} {json.dumps(payload, ensure_ascii=False)}")
    net = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, errors="replace")
    listen = [ln.strip() for ln in net.stdout.splitlines() if f":{PORT}" in ln and "LISTENING" in ln.upper()]
    # netstat -ano 列为 Proto / 本地地址 / 外部地址 / 状态 / PID；只看本地地址列，
    # LISTENING 行的外部地址本就是 0.0.0.0:0，不能据此判定监听全网。
    only_local = bool(listen) and all(ln.split()[1].startswith("127.0.0.1") for ln in listen)
    check("S2-NETSTAT-LOCAL", only_local,
          f"netstat 监听行 {len(listen)} 条，本地地址={[ln.split()[1] for ln in listen]} 原始行={listen[:4]}")

    # 3) schema / 表 / 种子
    versions = rows(DB, "SELECT version, name FROM schema_migrations ORDER BY version")
    tables = rows(DB, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    names = [t["name"] for t in tables]
    check("S2-SCHEMA-V1", [v["version"] for v in versions] == [1], f"schema_migrations={versions} 表数={len(names)}")
    log(f"STEP3 表清单({len(names)}): {names}")
    seeds = rows(DB, "SELECT name, channel, access_mode, access_verified FROM source ORDER BY name")
    seed_ok = len(seeds) == 4 and all(s["access_mode"] == "manual_import" for s in seeds)
    check("S2-SEED-4", seed_ok, f"source 种子={json.dumps(seeds, ensure_ascii=False)}")
    B1_TABLES = ["source", "candidate", "demand_signal", "evidence", "supply_offer", "cost_item", "gate_review",
                 "review_item", "import_batch", "import_row_result", "run_record", "idempotency_key", "schema_migrations"]
    missing = [t for t in B1_TABLES if t not in names]
    extra = [t for t in names if t not in B1_TABLES]
    check("S2-SCHEMA-B1SUBSET", not missing,
          f"B1 声称的 13 张表全部存在={not missing} 缺失={missing} 后续迁移新增={extra}")

    # 4) 正例导入
    c0 = counts()
    status, payload, _ = post_csv(fixture_text, "format=csv&mode=atomic", "contract_4_7_positive.csv")
    created = payload.get("counts", {}).get("created") if payload else None
    cand_id = None
    if payload:
        for rec in payload.get("rows", [{}])[0].get("records", []) or []:
            if rec.get("type") == "candidate":
                cand_id = rec.get("id")
    c1 = counts()
    five_ok = all(c1[t] == {"candidate": 1, "demand_signal": 1, "evidence": 2, "supply_offer": 1, "cost_item": 10}[t] for t in BIZ)
    check("S2-03-COUNT", status == 201 and created == 1 and five_ok,
          f"POST §4.7 正例 -> {status} counts={json.dumps(payload.get('counts') if payload else None, ensure_ascii=False)} 五表={ {t: c1[t] for t in BIZ} }")
    status, payload, _ = http("GET", "/api/candidates")
    identity = payload["items"][0]["identity_key"] if payload and payload.get("items") else None
    check("S2-04-IDENTITY", status == 200 and isinstance(identity, str) and re.match(r"^[un]:[a-z_]+:", identity or "") is not None,
          f"GET /api/candidates -> {status} total={payload.get('total') if payload else None} identity_key={identity}")
    if cand_id:
        status, detail, _ = http("GET", f"/api/candidates/{cand_id}")
        gates = detail.get("gates") if detail else None
        check("S2-12-13-GATES", status == 200 and gates and all(v == "unverified" for v in gates.values())
              and detail.get("derived_status") == "pending",
              f"GET 详情 -> {status} gates={gates} derived_status={detail.get('derived_status') if detail else None} reason={detail.get('derived_status_reason') if detail else None}")
    run_src = rows(DB, "SELECT COUNT(*) AS n FROM run_record WHERE source_id IS NULL")[0]["n"]
    check("S2-01-RUN-SOURCE-NULL", run_src >= 1, f"import 运行记录中 source_id 为 NULL 的条数={run_src}")
    costs = rows(DB, "SELECT role, basis, money_minor, rate_bp, minutes, hourly_rate_minor, period, supply_offer_id FROM cost_item ORDER BY role, basis")
    labor = [c for c in costs if c["role"] == "manual_labor"]
    linked = [c for c in costs if c["supply_offer_id"]]
    check("S2-03-COSTSHAPE", bool(len(costs) == 10 and labor and labor[0]["minutes"] == 15 and labor[0]["hourly_rate_minor"] == 3000),
          f"成本项 {len(costs)} 条 roles={sorted({c['role'] for c in costs})} manual_labor={labor} "
          f"cost_supply_url→supply_offer_id 关联数={len(linked)}")
    if cand_id:
        sc_status, sc_payload, _ = http("GET", f"/api/candidates/{cand_id}/scenario?variant=base")
        log(f"INFO scenario 端点当前状态={sc_status} payload={json.dumps(sc_payload, ensure_ascii=False)[:200] if sc_payload else None}")

    # 5) 同文件重导
    before = counts()
    status, payload, _ = post_csv(fixture_text, "format=csv&mode=atomic", "same.csv")
    after = counts()
    dup = payload.get("counts", {}).get("duplicate_skipped") if payload else None
    unchanged = all(before[t] == after[t] for t in BIZ)
    check("S2-04-REIMPORT", status == 201 and dup == 1 and unchanged,
          f"重导 -> {status} duplicate_skipped={dup} created={payload.get('counts', {}).get('created') if payload else None} 五表不变={unchanged}")

    # 6) 改 excerpt 重导 → version_added
    variant = dict(base_row)
    variant["demand_excerpt"] = (base_row.get("demand_excerpt") or "") + "（独立复核修订版）"
    status, payload, _ = post_csv(csv_text(header, variant), "format=csv&mode=atomic", "variant.csv")
    signals = rows(DB, "SELECT version_no, superseded_by FROM demand_signal ORDER BY version_no")
    superseded = [s for s in signals if s["superseded_by"]]
    check("S2-06-VERSION", status == 201 and payload.get("counts", {}).get("version_added") == 1 and len(superseded) == 1,
          f"改摘录重导 -> {status} counts={json.dumps(payload.get('counts') if payload else None, ensure_ascii=False)} demand_signal={signals}")

    # 7) validate 零写入
    before = counts()
    validate_row = dict(base_row)
    validate_row["title"] = (base_row.get("title") or "") + "-validate-only"
    status, payload, _ = post_csv(csv_text(header, validate_row), "format=csv&mode=validate", "validate.csv")
    after = counts()
    zero = all(before[t] == after[t] for t in BIZ + ["import_batch", "run_record", "idempotency_key"])
    check("S2-29-VALIDATE", status == 200 and payload.get("saved") is False and zero,
          f"validate -> {status} saved={payload.get('saved') if payload else None} 零写入={zero} "
          f"before={ {k: before[k] for k in BIZ + ['import_batch', 'run_record', 'idempotency_key']} } after={ {k: after[k] for k in BIZ + ['import_batch', 'run_record', 'idempotency_key']} }")

    # 7.5) S2-07：无需求组按标题身份复用 + 同需求行新增成本子项
    nd = {"title": "复核-无需求组复用", "data_origin": "synthetic", "sale_price": "9.90", "platform_fee_bp": "500"}
    nd_cols = ["title", "data_origin", "sale_price", "platform_fee_bp"]
    n0 = counts()
    a1, _, _ = post_csv(csv_text(nd_cols, nd), "format=csv&mode=atomic", "nodemand.csv")
    a2, _, _ = post_csv(csv_text(nd_cols, nd), "format=csv&mode=atomic", "nodemand.csv")
    n1 = counts()
    tkey = rows(DB, "SELECT identity_key FROM candidate WHERE title=?", (nd["title"],))
    check("S2-07-NODEMAND", bool(a1 == 201 and a2 == 201 and n1["candidate"] == n0["candidate"] + 1
          and n1["cost_item"] == n0["cost_item"] + 2 and tkey and tkey[0]["identity_key"].startswith("t:")),
          f"无需求组重导 -> {a1}/{a2} candidate+{n1['candidate'] - n0['candidate']} "
          f"cost_item+{n1['cost_item'] - n0['cost_item']} identity={tkey}")
    cols_step1 = ["title", "data_origin", "demand_source", "demand_url", "demand_excerpt", "demand_kind", "sale_price"]
    step1 = {"title": "复核-子项追加", "data_origin": "synthetic", "demand_source": "xianyu",
             "demand_url": "https://example.com/demand/ext-1", "demand_excerpt": "复核：子项追加样例",
             "demand_kind": "other", "sale_price": "10.00"}
    s_a, _, _ = post_csv(csv_text(cols_step1, step1), "format=csv&mode=atomic", "ext1.csv")
    s_b, p_b, _ = post_csv(csv_text(cols_step1 + ["payment_fee_bp"], dict(step1, payment_fee_bp="60")),
                           "format=csv&mode=atomic", "ext2.csv")
    ext_counts = (p_b or {}).get("counts", {})
    ext_batch = (p_b or {}).get("batch_id")
    ext_records = rows(DB, "SELECT action, record_type FROM import_row_result WHERE batch_id=?", (ext_batch,)) if ext_batch else []
    ext_pairs = {(r["action"], r["record_type"]) for r in ext_records}
    ext_costs = rows(DB, "SELECT role FROM cost_item ci JOIN candidate c ON c.id=ci.candidate_id WHERE c.title='复核-子项追加'")
    check("S2-07-SUBRECORD", bool(s_a == 201 and s_b == 201
          and ("duplicate_skipped", "demand_signal") in ext_pairs and ("created", "cost_item") in ext_pairs
          and sorted(r["role"] for r in ext_costs) == ["payment_fee", "sale_price"]),
          f"同需求行仅新增成本列 -> {s_a}/{s_b} 行级桶={json.dumps(ext_counts, ensure_ascii=False)} "
          f"逐记录={sorted(ext_pairs)} 该候选成本项={[r['role'] for r in ext_costs]}")

    # 8) atomic 含坏行
    before = counts()
    good = dict(base_row)
    good["title"] = (base_row.get("title") or "") + "-atomic-good"
    good["demand_url"] = "https://example.com/demand/atom-1"
    bad = dict(good)
    bad["title"] = (base_row.get("title") or "") + "-atomic-bad"
    bad["demand_url"] = "https://example.com/demand/atom-2"
    bad["sale_price"] = "-9.90"
    body = csv_text(header, good) + csv_text(header, bad).split("\n", 1)[1]
    status, payload, _ = post_csv(body, "format=csv&mode=atomic", "atomic_bad.csv")
    after = counts()
    batch_id = payload.get("batch_id") if payload else None
    reasons = rows(DB, "SELECT DISTINCT reason_code FROM import_row_result WHERE batch_id=?", (batch_id,)) if batch_id else []
    biz_unchanged = all(before[t] == after[t] for t in BIZ)
    check("S2-09-ATOMIC", bool(status == 422 and payload.get("status") == "rejected" and biz_unchanged
          and after["import_batch"] == before["import_batch"] + 1 and reasons),
          f"atomic 坏行 -> {status} status={payload.get('status') if payload else None} 业务表不变={biz_unchanged} "
          f"批次+1={after['import_batch'] - before['import_batch']} 行级原因={[r['reason_code'] for r in reasons]}")

    # 9) GBK
    before = counts()
    gbk_text = ("title,data_origin,demand_source,demand_url,demand_excerpt,demand_kind\n"
                "示例-编码核验,synthetic,xianyu,https://example.com/demand/gbk-1,这是一条中文摘录,other\n")
    status, payload, _ = http("POST", "/api/imports?format=csv&mode=atomic",
                              body=gbk_text.encode("gbk"), ctype="text/csv; charset=gbk")
    after = counts()
    unchanged = all(before[t] == after[t] for t in BIZ + ["import_batch", "run_record"])
    check("S2-10-GBK", status == 400 and (payload or {}).get("error", {}).get("code") == "encoding_error" and unchanged,
          f"GBK 导入 -> {status} error={(payload or {}).get('error')} 零写入={unchanged}")

    # 10) 跨渠道同 native_id=1001
    mini_cols = ["title", "data_origin", "demand_source", "demand_url", "demand_excerpt", "demand_kind", "demand_native_id"]
    mini = {"data_origin": "synthetic", "demand_excerpt": "独立复核：跨渠道隔离样例", "demand_kind": "other"}
    row_xy = dict(mini, title="复核-闲鱼同ID", demand_source="xianyu", demand_url="https://example.com/demand/xy-1001", demand_native_id="1001")
    row_bili = dict(mini, title="复核-B站同ID", demand_source="bilibili", demand_url="https://example.com/demand/bl-1001", demand_native_id="1001")
    s1, p1, _ = post_csv(csv_text(mini_cols, row_xy), "format=csv&mode=atomic", "xy_1001.csv")
    s2, p2, _ = post_csv(csv_text(mini_cols, row_bili), "format=csv&mode=atomic", "bl_1001.csv")
    keys = [r["identity_key"] for r in rows(DB, "SELECT identity_key FROM candidate WHERE identity_key LIKE 'n:%1001' ORDER BY identity_key")]
    check("S2-05-CROSSCHANNEL", s1 == 201 and s2 == 201 and keys == ["n:bilibili:1001", "n:xianyu:1001"],
          f"两渠道同 native_id -> {s1}/{s2} 候选身份={keys}")

    # 11) 不同 URL 同文 → dup_suspect
    dup_a = dict(mini, title="复核-同文不同URL", demand_source="xianyu", demand_url="https://example.com/demand/dup-9001", demand_native_id="")
    dup_b = dict(dup_a, demand_url="https://example.com/demand/dup-9002")
    s3, _, _ = post_csv(csv_text(mini_cols, dup_a), "format=csv&mode=atomic", "dup_a.csv")
    s4, p4, _ = post_csv(csv_text(mini_cols, dup_b), "format=csv&mode=atomic", "dup_b.csv")
    review = rows(DB, "SELECT kind, ref_type, ref_id, ref_id_b, blocking, status FROM review_item WHERE kind='dup_suspect' ORDER BY created_at DESC LIMIT 3")
    check("S2-06-DUPSUSPECT", s3 == 201 and s4 == 201 and review and all(r["blocking"] == 0 for r in review),
          f"同文不同URL -> {s3}/{s4} action={p4.get('counts') if p4 else None} dup_suspect={review}")

    # 12) 幂等：同键同载荷 / 异载荷 / 重启后
    idem_row = dict(mini, title="复核-幂等样例", demand_source="xianyu", demand_url="https://example.com/demand/idem-1", demand_native_id="2001")
    idem_body = csv_text(mini_cols, idem_row)
    s5, p5, _ = post_csv(idem_body, "format=csv&mode=atomic&client_ref=b1dr-1", "idem.csv")
    s6, p6, _ = post_csv(idem_body, "format=csv&mode=atomic&client_ref=b1dr-1", "idem.csv")
    changed = dict(idem_row, demand_excerpt="独立复核：异载荷样例")
    s7, p7, _ = post_csv(csv_text(mini_cols, changed), "format=csv&mode=atomic&client_ref=b1dr-1", "idem_changed.csv")
    check("S2-27-IDEMPOTENT", s5 == 201 and s6 == 200 and (p6 or {}).get("deduplicated") is True
          and s7 == 409 and (p7 or {}).get("error", {}).get("code") == "conflict" and p5.get("batch_id") == p6.get("batch_id"),
          f"幂等 -> 首次{s5} 重放{s6}(deduplicated={p6.get('deduplicated') if p6 else None}) 异载荷{s7}(code={(p7 or {}).get('error', {}).get('code')}) batch_same={p5.get('batch_id') == p6.get('batch_id')}")

    # 13) 重启 → 数据保留 + 幂等重放
    pre_restart = counts()
    code = stop_server(proc)
    proc2, health2, server_log2 = start_server("second", env)
    log(f"STEP13 重启：first_exit={code} second_ready={bool(health2)} server_log={server_log2}")
    post_restart = counts()
    s8, p8, _ = post_csv(idem_body, "format=csv&mode=atomic&client_ref=b1dr-1", "idem.csv")
    status, listing, _ = http("GET", "/api/candidates")
    persisted = pre_restart == {k: post_restart[k] for k in pre_restart}
    check("S2-02-RESTART", health2 is not None and persisted and status == 200 and listing.get("total") == post_restart["candidate"],
          f"重启后 -> health={bool(health2)} 计数一致={persisted} GET /api/candidates total={listing.get('total')} 五表={ {t: post_restart[t] for t in BIZ} }")
    check("S2-27-REPLAY-AFTER-RESTART", s8 == 200 and (p8 or {}).get("deduplicated") is True,
          f"重启后重放同 client_ref -> {s8} deduplicated={(p8 or {}).get('deduplicated')}")

    # 14) 依赖边界
    req = [ln.strip() for ln in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
           if ln.strip() and not ln.strip().startswith("#")]
    mods = set()
    for path in (ROOT / "app").rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(?:from|import)\s+([A-Za-z_][\w]*)", line)
            if m:
                mods.add(m.group(1))
    third = sorted(m for m in mods if m not in sys.stdlib_module_names and m not in {"app"})
    req_ok = len(req) == 1 and req[0].lower().startswith("flask")
    check("T-11-DEPS", req_ok and third == ["flask"], f"requirements.txt={req} app 内第三方导入={third}")

    # 15) 编码核验：存储值 vs HTTP 值 vs instance/http_e2e.txt 原始字节
    expect_title = base_row.get("title")
    stored = rows(DB, "SELECT title, excerpt FROM candidate JOIN demand_signal ON demand_signal.candidate_id=candidate.id ORDER BY candidate.created_at LIMIT 1")
    http_title = None
    raw_http = b""
    if stored:
        target_id = rows(DB, "SELECT id FROM candidate ORDER BY created_at LIMIT 1")[0]["id"]
        st, det, raw_http = http("GET", f"/api/candidates/{target_id}")
        http_title = (det or {}).get("candidate", {}).get("title")
    (TMP / "b1_check_http_raw.json").write_bytes(raw_http)
    raw_utf8_ok = expect_title.encode("utf-8") in raw_http
    e2e = ROOT / "instance" / "http_e2e.txt"
    enc_report = "instance/http_e2e.txt 不存在"
    if e2e.exists():
        raw = e2e.read_bytes()
        found = {}
        text = None
        for enc in ("utf-8-sig", "utf-8", "utf-16", "gbk", "cp936", "latin-1"):
            try:
                decoded = raw.decode(enc)
                found[enc] = expect_title in decoded
                if text is None and enc.startswith("utf-8"):
                    text = decoded
            except UnicodeDecodeError:
                found[enc] = None
        repaired = None
        if text is not None:
            for chain in ("cp1252", "latin-1"):
                try:
                    repaired = text.encode(chain).decode("utf-8")
                    if expect_title in repaired:
                        break
                except Exception:
                    repaired = None
        repair_hit = bool(isinstance(repaired, str) and expect_title in repaired)
        snippet = (text or "")[:0]
        enc_report = f"bytes={len(raw)} 直接命中期望标题={found} cp1252→utf-8 反转命中={repair_hit}"
    check("S2-13-ENCODING", bool(stored) and stored[0]["title"] == expect_title and http_title == expect_title and raw_utf8_ok,
          f"库内标题==契约样例={bool(stored) and stored[0]['title'] == expect_title} HTTP 标题==契约样例={http_title == expect_title} "
          f"原始 HTTP 字节含 UTF-8 期望标题={raw_utf8_ok} 库内标题={stored[0]['title'] if stored else None!r} | {enc_report}")

    # 16) T-07 discover 与用例计数（只读观测，不运行 B 的测试目录）
    disc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                          cwd=str(ROOT), env=env, capture_output=True, text=True, errors="replace")
    init_exists = (ROOT / "tests" / "__init__.py").exists()
    tail = (disc.stderr or disc.stdout).strip().splitlines()[-1:] if (disc.stderr or disc.stdout) else []
    check("T-07-DISCOVER", None,
          f"discover exit={disc.returncode} tests/__init__.py 存在={init_exists} 末行={tail} "
          f"（B1 交付时为缺失状态；本项只记录现状，失败归因见报告）")
    b1_files = ["tests/core/test_money.py", "tests/core/test_identity.py", "tests/storage/test_migrations.py", "tests/api/test_import_api.py"]
    counts_by_file = {}
    for rel in b1_files:
        path = ROOT / rel
        counts_by_file[rel] = len(re.findall(r"def (test_\w+)\(", path.read_text(encoding="utf-8"))) if path.exists() else None
    total = sum(v or 0 for v in counts_by_file.values())
    all_tests = {str(p.relative_to(ROOT)): len(re.findall(r"def (test_\w+)\(", p.read_text(encoding="utf-8")))
                 for p in sorted((ROOT / "tests").rglob("test_*.py"))}
    check("B1-UNITTEST-COUNT", total == 45,
          f"B1 四个交付文件的用例数={total} 明细={counts_by_file}（当前工作树全部用例={all_tests}）")

    # 17) 结束时哈希
    end = sha_map()
    changed = sorted(k for k in set(start) | set(end) if start.get(k) != end.get(k))
    (TMP / "app_hashes_repro_end.txt").write_text(
        "\n".join(f"{v}  {k}" for k, v in end.items()) + "\n", encoding="utf-8")
    log(f"STEP17 期间变化的文件({len(changed)}): {changed}")

    stop_server(proc2)
    log("")
    log("# 汇总")
    for cid, state, _ in results:
        log(f"{state}\t{cid}")
    fails = [r for r in results if r[1] == "FAIL"]
    log(f"合计 {len(results)} 项：PASS {sum(1 for r in results if r[1] == 'PASS')} / MANUAL {sum(1 for r in results if r[1] == 'MANUAL')} / FAIL {len(fails)}")
    LOG.write_text("\n".join(_loglines) + "\n", encoding="utf-8")
    return 0 if not fails else 1


if __name__ == "__main__":
    code = main()
    print(f"exit={code}")
    sys.exit(code)
