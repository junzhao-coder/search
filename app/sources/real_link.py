"""S3 受控 real 模式：授权闸门 + 真实 transport + 预算/间隔/超时 + 审计 + 异常兜底。

设计依据：docs/design/S3_REAL_LINK_SPEC.md v2（§3 预算/间隔/退避/超时、§4 失败矩阵、§5 观察时间、
§6 身份/ABA、§7 复用边界、§9.2 实现批后验）。**仅本模块实现 real 模式**，不改 frozen 的
wiring.py / bilibili_view.py / importer.py；notes 审计通道按设计 §11-1 选"批次审计文件、不入库"。

纪律
----
* 授权闸门：缺少授权参数/批次号/用户确认时**立即拒绝且发起 0 次网络请求**。
* 预算：请求次数（含重试）≤ ``budget``（默认且上限 20）；耗尽后停止并在 notes 写 ``BUDGET_EXHAUSTED``。
* 间隔：请求间 ≥ ``interval_seconds``（默认且下限 5 秒）；总时长 ≤ ``timeout_seconds``（默认且上限 600 秒）。
* 重试：仅 ``timeout``/``failed``（含 5xx）重试一次，等待 2 秒；``rate_limited``/``blocked_login`` 不重试。
* 异常兜底：transport 抛异常→失败 run（不吞、不当成功），审计留痕。
* 审计：``<run_dir>/audit.jsonl``，每行含 ts/batch_id/bvid/url/http_status/outcome/error/attempt。
* 不写 ``source.last_success_at``；失败 run 的计数列取 schema 默认 0 并注明"技术默认值"。
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import sqlite3

from ..core import importer
from ..core.errors import AppError
from ..core.util import now_utc
from . import wiring
from .bilibili_view import BilibiliViewReader

SOURCE_ID = "s_bili"
REAL_ORIGIN = "real"
REAL_URL = "https://www.bilibili.com/video/{bvid}"
#: 诊断结论（本批）：网页 URL 返回 HTML（gzip, text/html），适配器期望的 JSON 来自**详情 API**；
#: 因此真实 transport 必须改请求 API 端点，并把响应**归一化**为适配器 envelope
#: ``{"http_status", "payload", "error"}``（不改 frozen 适配器）。
REAL_API_URL = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
DEFAULT_BUDGET = 20
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_TIMEOUT_SECONDS = 600.0
MAX_BUDGET = 20
MIN_INTERVAL_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 600.0
RETRY_WAIT_SECONDS = 2.0
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
TIMEOUT_STOP = "BATCH_TIMEOUT"
RETRYABLE_OUTCOMES = {"timeout", "failed"}
NO_RETRY_OUTCOMES = {"rate_limited", "blocked_login"}
_USER_AGENT = "local-selection-tool/1.0 (+offline research)"
_REAL_ROW_DROP = ("supply_", "cost_", "gate_")
_REAL_ROW_KEEP = ("title", "data_origin", "demand_source", "demand_native_id", "demand_url",
                  "demand_excerpt", "demand_kind", "demand_published_date", "observed_at")


_REQUIRED_CFG_INT_RANGES = {"tz_offset_hours": (-12, 14)}


def _require_cfg(cfg) -> None:
    """A: 运行前校验配置（必须在任何网络调用/审计文件之前；缺失或无效→422 且 transport 0 次）。"""
    if not isinstance(cfg, dict):
        raise AppError("缺少运行配置", code="invalid_field", status=422,
                       details=[{"field": "cfg", "reason": "必须是配置 dict"}])
    problems = []
    tz = cfg.get("tz_offset_hours")
    low, high = _REQUIRED_CFG_INT_RANGES["tz_offset_hours"]
    if isinstance(tz, bool) or not isinstance(tz, int) or not (low <= tz <= high):
        problems.append({"field": "tz_offset_hours", "reason": f"必须是 {low}..{high} 的整数"})
    rows = cfg.get("max_rows_per_batch")
    if isinstance(rows, bool) or not isinstance(rows, int) or rows <= 0:
        problems.append({"field": "max_rows_per_batch", "reason": "必须是正整数"})
    if problems:
        raise AppError("运行配置不合法", code="invalid_field", status=422, details=problems)


MIN_TRANSPORT_TIMEOUT_SECONDS = 0.0005


def _make_default_transport(remaining_ref: list):
    """B/3: 默认 transport 的 URL-only 包装——timeout=min(10, remaining)，不抬高下限。

    剩余 < MIN_TRANSPORT_TIMEOUT_SECONDS 时**直接停止**（raise 由调用层转为失败），
    绝不用 0.001 之类下限把"几乎无剩余"变成一次真实请求。
    """
    def _transport(url: str) -> dict:
        remaining = remaining_ref[0]
        if remaining is None or remaining < MIN_TRANSPORT_TIMEOUT_SECONDS:
            raise RuntimeError("deadline exceeded before transport call")
        return real_transport(url, timeout=min(10.0, remaining))
    return _transport


def check_authorization(authorization: dict | None) -> str:
    """授权闸门：必须在任何网络调用之前执行。返回批次号。"""
    if not isinstance(authorization, dict):
        raise AppError("未授权批次：缺少授权参数", code="invalid_field", status=422,
                       details=[{"field": "authorization", "reason": "必须提供授权对象"}])
    batch_id = str(authorization.get("batch_id") or "").strip()
    if not batch_id:
        raise AppError("未授权批次：批次号为空", code="invalid_field", status=422,
                       details=[{"field": "batch_id", "reason": "非空批次号必填"}])
    if authorization.get("confirmed") is not True:
        raise AppError("未授权批次：缺少用户确认", code="invalid_field", status=422,
                       details=[{"field": "confirmed", "reason": "必须为 true（用户逐项授权）"}])
    return batch_id


def _bvid_from_url(url: str) -> str:
    """从网页 URL 或 API URL 提取 bvid（适配器实际传入的是详情 API URL）。"""
    from urllib.parse import parse_qs, urlsplit
    parts = urlsplit(str(url))
    query = parse_qs(parts.query).get("bvid")
    if query:
        return query[0]
    return parts.path.rstrip("/").rsplit("/", 1)[-1]


def api_url(bvid: str) -> str:
    return REAL_API_URL.format(bvid=bvid)


def _decode_body(body: bytes, encoding: str | None) -> bytes:
    """gzip 兼容解码（诊断实测网页 URL 返回 gzip 内容；API 端要求 identity 但仍兜底）。"""
    if body[:2] == b"\x1f\x8b":
        import gzip

        return gzip.decompress(body)
    return body


def normalize_response(http_status, content_type: str | None, body: bytes) -> dict:
    """把原始 HTTP 响应归一化为 bilibili_view 适配器 envelope（本批新增层，不改适配器）。"""
    del content_type  # 仅按内容判断，避免依赖服务端声明
    decoded = _decode_body(body, None)
    try:
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"http_status": http_status, "payload": None, "error": "html_shell"}
    if not isinstance(payload, dict):
        return {"http_status": http_status, "payload": None, "error": "html_shell"}
    return {"http_status": http_status, "payload": payload, "error": None}


def real_transport(url: str, *, timeout: float = 10.0) -> dict:
    """真实 transport：请求详情 API（适配器传入的已是 API URL 时直接使用），返回 envelope。"""
    bvid = _bvid_from_url(url)
    request_url = str(url) if "bvid=" in str(url) else api_url(bvid)
    request = urllib.request.Request(request_url, headers={"User-Agent": _USER_AGENT,
                                                            "Accept": "application/json",
                                                            "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            body = response.read(2_000_000)
        return normalize_response(status, None, body)
    except urllib.error.HTTPError as exc:
        body = exc.read(200_000) if hasattr(exc, "read") else b""
        try:
            return normalize_response(exc.code, None, body)
        except Exception:  # noqa: BLE001
            return {"http_status": exc.code, "payload": None, "error": "http_error"}
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return {"http_status": None, "payload": None, "error": "timeout"}
        return {"http_status": None, "payload": None, "error": "transport_error"}
    except (TimeoutError, socket.timeout):
        return {"http_status": None, "payload": None, "error": "timeout"}
    except Exception:  # noqa: BLE001 - 兜底：绝不穿透
        return {"http_status": None, "payload": None, "error": "transport_error"}


def _audit(writer, **event) -> None:
    """写审计；**写失败必须冒泡**（不得吞掉，也不得因审计失败递归调用 record_failure）。"""
    writer.write(json.dumps({"ts": now_utc(), **event}, ensure_ascii=False) + "\n")
    writer.flush()


def _build_real_row(record: dict, observed_at: str | None, observed_at_source: str,
                    warnings: list[tuple[str, str]]) -> dict:
    """real 模式行构造（独立于 wiring.build_row 的 synthetic-only 判定，仅此受控入口）。"""
    if record.get("outcome") != "ok":
        raise AppError("记录不是成功结果", code="invalid_field", status=422,
                       details=[{"reason": str(record.get("failure_reason") or record.get("outcome"))}])
    bvid = str(record.get("bvid") or record.get("native_id") or "").strip()
    if not bvid:
        raise AppError("缺少 bvid", code="invalid_field", status=422)
    title = str(record.get("title") or "").strip()
    if not title or len(title) > 300:
        raise AppError("标题为空或超过 300 字", code="invalid_field", status=422)
    excerpt = str(record.get("excerpt") or "").strip()
    if not excerpt:
        raise AppError("缺少摘录", code="invalid_field", status=422)
    row = {"title": title, "data_origin": REAL_ORIGIN, "demand_source": "bilibili",
           "demand_native_id": bvid, "demand_url": REAL_URL.format(bvid=bvid),
           "demand_excerpt": excerpt}
    if record.get("signal_kind"):
        row["demand_kind"] = str(record["signal_kind"])
    if record.get("published_date") or record.get("published_at"):
        row["demand_published_date"] = str(record.get("published_date") or record["published_at"])[:10]
    if observed_at_source == "source" and observed_at:
        row["observed_at"] = observed_at
    for key in record:
        if key.startswith(_REAL_ROW_DROP) and key not in ("supply_provider",):
            warnings.append(("S3_REAL_FOREIGN_FIELDS", f"真实模式丢弃外部字段：{key}"))
    if record.get("unknown_fields"):
        warnings.append(("S3_UNKNOWN_FIELDS", f"适配器上报未知字段：{record['unknown_fields']}"))
    if record.get("observed_at_rejected"):
        warnings.append(("S3_OBSERVED_AT_REJECTED", f"源观察时间被拒：{record['observed_at_rejected']}"))
    return row


def run_real_batch(conn, bvids, *, authorization, run_dir, budget: int = DEFAULT_BUDGET,
                   interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
                   timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, cfg: dict | None = None,
                   clock=time.monotonic, sleep=time.sleep, transport=None) -> dict:
    """执行受控真实批次（≤ budget 个请求）。调用前必须先通过 :func:`check_authorization`。

    ``transport`` 缺省时使用 URL-only 包装（timeout=min(10, 剩余时间)）；自定义 transport 与
    操作系统 I/O 都不是硬实时——剩余时间只在**调用前**检查，单次 I/O 可能超出剩余时间。
    """
    batch_id = check_authorization(authorization)
    _require_cfg(cfg)                                  # A：配置缺失/无效→422，先于任何网络与审计
    if budget < 1 or budget > MAX_BUDGET:
        raise AppError("预算超出允许范围", code="invalid_field", status=422,
                       details=[{"field": "budget", "reason": f"1..{MAX_BUDGET}"}])
    if interval_seconds < MIN_INTERVAL_SECONDS:
        raise AppError("请求间隔不得低于 5 秒", code="invalid_field", status=422,
                       details=[{"field": "interval_seconds", "reason": f">= {MIN_INTERVAL_SECONDS}"}])
    if timeout_seconds <= 0 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise AppError("总超时超出允许范围", code="invalid_field", status=422,
                       details=[{"field": "timeout_seconds", "reason": f"1..{MAX_TIMEOUT_SECONDS}"}])
    targets = [str(item).strip() for item in bvids if str(item).strip()]
    if not targets:
        raise AppError("目标清单为空", code="invalid_field", status=422)
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    audit_path = run_path / "audit.jsonl"
    deadline = clock() + timeout_seconds                     # B：统一 monotonic deadline
    remaining_ref = [deadline - clock()]
    effective_transport = transport if transport is not None else _make_default_transport(remaining_ref)
    requests_made = 0
    stopped_reason = None
    results = []
    truncated = []
    # 2) 按**输入位置**维护（重复 bvid 保留多次，不用 bvid 去重）
    target_summary = [{"index": index, "bvid": bvid, "attempts": 0, "attempted": False,
                       "succeeded": False, "failed": False, "unrequested": False, "error": None}
                      for index, bvid in enumerate(targets)]

    def _remaining() -> float:
        return deadline - clock()

    def _stop_reason():
        """预算/总超时检查（每次请求前与每次等待后复查；deadline 用 >= 判过期）。"""
        remaining_ref[0] = _remaining()
        if requests_made >= budget:
            return BUDGET_EXHAUSTED
        if remaining_ref[0] <= 0:
            return TIMEOUT_STOP
        return None

    with audit_path.open("a", encoding="utf-8") as audit:
        for position, bvid in enumerate(targets):
            reader = BilibiliViewReader(effective_transport)  # 每次新建：避免缓存命中掩盖请求计数
            attempts = 0
            last = None
            while True:
                stopped_reason = _stop_reason()
                if stopped_reason:
                    break
                if requests_made > 0:
                    sleep(interval_seconds)                 # 注：跨境/风控场景严格串行
                    stopped_reason = _stop_reason()          # 等待后复查：过期/预算变化则不再请求
                    if stopped_reason:
                        break
                attempts += 1
                requests_made += 1
                url = api_url(bvid)                     # 审计记录**真实请求**的 API URL
                try:
                    record = reader.complete(REAL_URL.format(bvid=bvid))
                except Exception as exc:  # transport 异常兜底（设计 §4 末行）
                    record = {"outcome": "failed", "failure_reason":
                              f"transport 异常：{type(exc).__name__}: {exc}", "http_status": None}
                _audit(audit, batch_id=batch_id, bvid=bvid, url=url, attempt=attempts,
                       requests_made=requests_made, outcome=record.get("outcome"),
                       http_status=record.get("http_status"), error=record.get("failure_reason"))
                last = record
                if record.get("outcome") == "ok":
                    break
                if record.get("outcome") in NO_RETRY_OUTCOMES or attempts >= 2:
                    break
                if record.get("outcome") in RETRYABLE_OUTCOMES:
                    sleep(RETRY_WAIT_SECONDS)
                    stopped_reason = _stop_reason()          # 退避等待后复查
                    if stopped_reason:
                        break
                    continue
                break
            if stopped_reason:
                # C: 停止分类——已实际尝试且失败（last 非空）才记 failed run（保留原错误）；
                #    未执行/未尝试（last 为空）只写终止事件与 summary，**不伪造**失败 run。
                if last is not None and cfg is not None:
                    reason = (f"批次中止（{stopped_reason}）："
                              f"{last.get('failure_reason') or last.get('outcome')}")
                    wiring.record_failure(conn, cfg, last, reason=reason, status="failed",
                                          source_id=SOURCE_ID)
                _audit(audit, batch_id=batch_id, bvid=bvid, url=api_url(bvid), attempt=attempts,
                       requests_made=requests_made, outcome="truncated", http_status=None,
                       error=stopped_reason, event="truncated")
                truncated.append({"bvid": bvid, "reason": stopped_reason, "attempts": attempts})
                entry = target_summary[position]
                entry.update({"attempts": attempts, "attempted": last is not None,
                              "succeeded": False, "failed": last is not None,
                              "unrequested": last is None,
                              "error": (last.get("failure_reason") if last is not None
                                        else stopped_reason)})
                break
            results.append({"bvid": bvid, "position": position, "record": last,
                            "attempts": attempts, "requests": requests_made})
            entry = target_summary[position]
            entry.update({"attempts": attempts, "attempted": True,
                          # succeeded 仅表示"抓取成功"，导入成功后会被最终判定覆盖
                          "succeeded": last.get("outcome") == "ok",
                          "failed": last.get("outcome") != "ok",
                          "unrequested": False,
                          "error": last.get("failure_reason")})
    notes = [f"batch_id={batch_id}", f"requests={requests_made}",
             f"targets={len(targets)}", "notes_channel=run_dir/audit.jsonl（不入库）"]
    if stopped_reason:
        notes.append(stopped_reason)
    imported = []
    import_errors = []
    for result in results:
        record = result["record"]
        position = result["position"]
        bvid = result["bvid"]
        entry = target_summary[position]
        error_text = None
        status_code = None
        imported_item = None
        if record.get("outcome") != "ok":
            error_text = str(record.get("failure_reason") or record.get("outcome"))
        else:
            warnings: list[tuple[str, str]] = []
            try:
                row = _build_real_row(record, None, "import_time", warnings)
                observed = (record.get("observed_at_source") == "source"
                            and record.get("observed_at"))
                body = json.dumps([row], ensure_ascii=False).encode("utf-8")
                payload, status_code, _ = importer.handle_import(
                    conn, cfg, fmt="json", body=body, filename=f"real:{bvid}.json",
                    mode="atomic", format_version=1, client_ref=None, run_source_id=SOURCE_ID,
                    internal_observation={"observed_at": record.get("observed_at") or now_utc(),
                                          "observed_at_source": "source" if observed else "import_time",
                                          "warnings": warnings})
            except AppError as exc:
                error_text = f"映射/校验失败：{exc.message}"
            except sqlite3.Error as exc:                   # D：SQLite 异常同样落失败审计
                error_text = f"导入SQL异常：{type(exc).__name__}: {exc}"
            else:
                if status_code in (200, 201):
                    imported_item = {"bvid": bvid, "position": position, "status": status_code,
                                     "action": payload.get("rows"), "ok": True}
                else:
                    error_text = f"导入返回非成功码 status={status_code}"
        if imported_item is not None:
            imported.append(imported_item)
            entry.update({"succeeded": True, "failed": False, "error": None})
            continue
        import_errors.append({"bvid": bvid, "position": position,
                              "status": status_code, "error": error_text})
        entry.update({"succeeded": False, "failed": True, "error": error_text})
        if cfg is not None:
            # B1/B2：record_failure 在导入 try 之外、**单次调用**；其自身 sqlite3.Error 向上冒泡，
            # 不被导入的 except sqlite3.Error 捕获（不二次记账、不吞、不递归）。
            wiring.record_failure(conn, cfg, record, reason=str(error_text),
                                  status="failed", source_id=SOURCE_ID)
    # 状态必须在**导入之后**判定：任何导入失败/截断都不得报 ok（原实现先算状态、只看导入返回码）。
    if stopped_reason or truncated or import_errors:
        status_value = "partial" if imported else "failed"
    elif imported and len(imported) == len(targets):
        status_value = "ok"
    else:
        status_value = "partial" if imported else "failed"
    for entry in target_summary:
        if not entry["attempted"]:
            entry.update({"unrequested": True, "error": stopped_reason or "未执行"})
    summary_counts = {"attempted": sum(1 for i in target_summary if i["attempted"]),
                      "succeeded": sum(1 for i in target_summary if i["succeeded"]),
                      "failed": sum(1 for i in target_summary if i["failed"]),
                      "unrequested": sum(1 for i in target_summary if i["unrequested"])}
    terminal = {"batch_id": batch_id, "status": status_value, "requests": requests_made,
                "targets": targets, "target_count": len(targets), "results": len(results),
                "imported": len(imported), "failed_imports": import_errors,
                "truncated": truncated, "stopped_reason": stopped_reason,
                "target_summary": target_summary, "summary_counts": summary_counts,
                "finished_at": now_utc(), "audit_path": str(audit_path)}
    result_path = run_path / "batch_result.json"
    result_path.write_text(json.dumps(terminal, ensure_ascii=False, indent=1), encoding="utf-8")
    notes.append(f"terminal_reason={stopped_reason or 'none'}")
    return {"batch_id": batch_id, "status": status_value, "requests": requests_made,
            "targets": targets, "results": len(results), "imported": imported,
            "failed_imports": import_errors, "truncated": truncated,
            "target_summary": target_summary, "summary_counts": summary_counts,
            "notes": "; ".join(notes), "audit_path": str(audit_path),
            "stopped_reason": stopped_reason, "result_path": str(result_path)}
