"""CSV/JSON import pipeline: parse -> validate (V1..V27) -> write (atomic/partial/validate).

Contract §4: identity/dedupe per §4.5, money rules per §0.3, unknown-vs-zero per §0.4,
idempotency per §0.7/§1.15, status derivation per §3.3.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from dataclasses import dataclass, field

from .errors import AppError, RowError
from .gates import add_review, downgrade_cost_gate_if_verified
from .identity import (
    candidate_identity_key,
    content_hash,
    demand_identity_key,
    title_norm_hash,
    url_norm,
)
from .money import MONEY_MINOR_ALIASES, apply_rate, minor_int, yuan_to_minor
from .state import apply_status
from .util import now_utc, slug_id, today_local

BASE_COLUMNS = ("title", "data_origin", "category", "use_case", "delivery_form", "notes", "observed_at")
DEMAND_COLUMNS = (
    "demand_url", "demand_excerpt", "demand_native_id", "demand_source", "demand_kind",
    "demand_published_at", "demand_published_date", "demand_engagement",
    "demand_original_author", "demand_is_repost", "demand_origin_group_key",
)
SUPPLY_COLUMNS = (
    "supply_provider", "supply_url", "supply_native_id", "supply_origin_type", "supply_format_version",
    "supply_price", "supply_price_basis", "supply_price_valid_until", "supply_license_summary",
    "supply_license_scope_note", "supply_evidence_url", "supply_evidence_excerpt",
    "supply_evidence_fact_kind", "supply_downloadable", "supply_commercial_allowed",
    "supply_redistribute_allowed", "supply_resale_allowed", "supply_sample_checked",
    "supply_sample_note", "supply_last_checked_at",
)
COST_COLUMNS = (
    "sale_price", "platform_fee_bp", "payment_fee_bp", "acquisition_cost", "refund_rate_bp",
    "procurement_unit_cost", "procurement_cost", "procurement_recurring_cost", "procurement_period",
    "manual_minutes", "manual_hourly_rate", "other_cost", "scenario_variant", "currency", "cost_supply_url",
)
ALL_COLUMNS = tuple(BASE_COLUMNS) + DEMAND_COLUMNS + SUPPLY_COLUMNS + COST_COLUMNS + tuple(MONEY_MINOR_ALIASES)

EXAMPLES = ("example.com", "example.org", "example.net")
DATA_ORIGINS = {"real", "synthetic"}
DEMAND_KINDS = {"seller_promo", "specific_ask", "want_to_buy", "business_record", "other"}
ORIGIN_TYPES = {"original_author", "official", "open_repo", "distributor", "self_made", "unknown"}
YES_NO_UNKNOWN = {"yes", "no", "unknown"}
SAMPLE_CHECKED = {"none", "partial", "checked"}
PERIODS = {"monthly", "quarterly", "yearly"}
PRICE_BASIS = {"one_time", "per_unit", "subscription"}
MAX_EXCERPT, MAX_NOTES, MAX_TEXT = 4000, 2000, 500

# Cost column -> (role, basis, value_kind)
COST_MAP = {
    "sale_price": ("sale_price", "per_order", "money"),
    "platform_fee_bp": ("platform_fee", "per_order", "rate"),
    "payment_fee_bp": ("payment_fee", "per_order", "rate"),
    "acquisition_cost": ("acquisition", "per_order", "money"),
    "refund_rate_bp": ("refund_reserve", "per_order", "rate"),
    "procurement_unit_cost": ("procurement", "per_order", "money"),
    "procurement_cost": ("procurement", "one_time", "money"),
    "procurement_recurring_cost": ("procurement", "recurring", "money"),
    "other_cost": ("other", "per_order", "money"),
}


@dataclass
class CostSpec:
    role: str
    basis: str
    value_kind: str
    money_minor: int | None = None
    rate_bp: int | None = None
    minutes: int | None = None
    hourly_rate_minor: int | None = None
    period: str | None = None
    variant: str = "base"
    currency: str = "CNY"
    supply_url: str | None = None


@dataclass
class ParsedRow:
    row_no: int
    base: dict
    demand: dict | None
    supply: dict | None
    costs: list[CostSpec]
    warnings: list[tuple[str, str]] = field(default_factory=list)

    def errors(self) -> list[RowError]:
        return list(getattr(self, "_errors", []))

    def add_error(self, err: RowError) -> None:
        if not hasattr(self, "_errors"):
            self._errors = []
        self._errors.append(err)


# ---------------------------------------------------------------- parsing helpers

def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _bad(code: str, field_name: str, reason: str) -> RowError:
    return RowError(code, field_name, reason)


def _is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def _host_of(url: str) -> str:
    rest = url.split("://", 1)[1] if "://" in url else url
    host = rest.split("/", 1)[0].split("?", 1)[0].lower()
    return host.split(":", 1)[0]


def _check_url(value: str, field_name: str, origin: str, errors: list[RowError]) -> None:
    if not value:
        return
    if origin == "synthetic":
        if not _is_url(value) or _host_of(value) not in EXAMPLES:
            errors.append(_bad("V4", field_name, "synthetic 行的 URL 必须为空或示例域"))
        return
    if not _is_url(value) or _host_of(value) in EXAMPLES:
        errors.append(_bad("V4", field_name, "real 行必须使用非示例域的 http(s) 绝对地址"))


def _parse_amount(raw: str, field_name: str, errors: list[RowError]) -> int | None:
    if raw == "":
        return None
    try:
        return yuan_to_minor(raw)
    except ValueError as exc:
        errors.append(_bad("V5", field_name, str(exc)))
        return None


def _parse_minor(raw, field_name: str, errors: list[RowError]) -> int | None:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    try:
        return minor_int(raw)
    except ValueError as exc:
        errors.append(_bad("V5", field_name, str(exc)))
        return None


def _parse_int(raw, field_name: str, errors: list[RowError], low: int, high: int, code: str = "V6") -> int | None:
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    if isinstance(raw, bool):
        errors.append(_bad(code, field_name, "布尔值不是合法整数"))
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        errors.append(_bad(code, field_name, "必须是整数"))
        return None
    if value < low or value > high:
        errors.append(_bad(code, field_name, f"必须在 {low}..{high}"))
        return None
    return value


def _check_at(raw: str, field_name: str, errors: list[RowError]) -> str | None:
    if raw == "":
        return None
    body = raw
    if body.endswith("Z"):
        core = body[:-1]
    elif len(body) >= 6 and body[-6] in "+-" and body[-3] == ":":
        core = body[:-6]
    else:
        errors.append(_bad("V7", field_name, "时间必须带 Z 或 ±HH:MM 时区"))
        return None
    try:
        import datetime as _dt

        _dt.datetime.strptime(core, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        errors.append(_bad("V7", field_name, "时间必须是 ISO-8601 秒精度"))
        return None
    return body


def _check_date(raw: str, field_name: str, errors: list[RowError]) -> str | None:
    if raw == "":
        return None
    import datetime as _dt

    try:
        _dt.datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        errors.append(_bad("V7", field_name, "日期必须是 YYYY-MM-DD"))
        return None
    return raw


def _check_len(raw: str, field_name: str, limit: int, errors: list[RowError]) -> str:
    if len(raw) > limit:
        errors.append(_bad("V12", field_name, f"长度超过 {limit} 字符"))
    return raw


# ---------------------------------------------------------------- row validation

def validate_row(row_no: int, raw: dict, cfg: dict, source_names: dict[str, str]) -> ParsedRow:
    errors: list[RowError] = []
    warnings: list[tuple[str, str]] = []
    get = lambda name: _text(raw.get(name, ""))
    get_minor = lambda name: raw.get(name, None)

    title = _check_len(get("title"), "title", 300, errors)
    if not title:
        errors.append(_bad("V2", "title", "title 必填且去空白后非空"))
    origin = get("data_origin")
    if origin not in DATA_ORIGINS:
        errors.append(_bad("V3", "data_origin", "必须是 real 或 synthetic"))

    category = _check_len(get("category"), "category", MAX_TEXT, errors)
    use_case = _check_len(get("use_case"), "use_case", MAX_TEXT, errors)
    delivery_form = _check_len(get("delivery_form"), "delivery_form", MAX_TEXT, errors)
    notes = _check_len(get("notes"), "notes", MAX_NOTES, errors) or None
    observed_at_raw = get("observed_at")
    observed_at = _check_at(observed_at_raw, "observed_at", errors)

    # ---- demand group
    demand_present = any(get(c) for c in DEMAND_COLUMNS)
    demand = None
    if demand_present:
        url = get("demand_url")
        excerpt = _check_len(get("demand_excerpt"), "demand_excerpt", MAX_EXCERPT, errors)
        if not url:
            errors.append(_bad("V10", "demand_url", "需求组必须提供 demand_url"))
        if not excerpt:
            errors.append(_bad("V10", "demand_excerpt", "需求组必须提供 demand_excerpt"))
        source_name = get("demand_source") or "manual_import"
        if source_name == "manual":
            source_name = "manual_import"
        if source_name not in source_names:
            errors.append(_bad("V9", "demand_source", f"未登记来源名：{source_name}"))
        if origin in DATA_ORIGINS:
            _check_url(url, "demand_url", origin, errors)
        kind = get("demand_kind") or "other"
        if kind not in DEMAND_KINDS:
            errors.append(_bad("V9", "demand_kind", "枚举外值"))
        published_at = _check_at(get("demand_published_at"), "demand_published_at", errors)
        published_date = _check_date(get("demand_published_date"), "demand_published_date", errors)
        if published_at and published_date:
            errors.append(_bad("V8", "demand_published_at", "published_at 与 published_date 至多一个"))
        repost = _parse_int(get("demand_is_repost") or None, "demand_is_repost", errors, 0, 1)
        demand = {
            "url": url,
            "url_norm": url_norm(url),
            "native_id": get("demand_native_id") or None,
            "source_name": source_name,
            "excerpt": excerpt,
            "kind": kind,
            "published_at": published_at,
            "published_date": published_date,
            "engagement": get("demand_engagement") or None,
            "author": get("demand_original_author") or None,
            "is_repost": repost or 0,
            "origin_group_key": get("demand_origin_group_key") or None,
        }
    elif observed_at_raw:
        warnings.append(("V23", "无需求组的行没有 observed_at 落点，已忽略该值"))

    # ---- supply group
    supply_present = any(get(c) for c in SUPPLY_COLUMNS)
    supply = None
    if supply_present:
        provider = get("supply_provider")
        s_url = get("supply_url")
        if not provider:
            errors.append(_bad("V10", "supply_provider", "货源组必须提供 supply_provider"))
        if not s_url:
            errors.append(_bad("V10", "supply_url", "货源组必须提供 supply_url"))
        if origin in DATA_ORIGINS:
            _check_url(s_url, "supply_url", origin, errors)
        licenses = {}
        for field_name in ("supply_commercial_allowed", "supply_redistribute_allowed", "supply_resale_allowed"):
            value = get(field_name) or "unknown"
            if value not in YES_NO_UNKNOWN:
                errors.append(_bad("V9", field_name, "必须是 yes/no/unknown"))
            licenses[field_name] = value
        origin_type = get("supply_origin_type") or "unknown"
        if origin_type not in ORIGIN_TYPES:
            errors.append(_bad("V9", "supply_origin_type", "枚举外值"))
        sample_checked = get("supply_sample_checked") or "none"
        if sample_checked not in SAMPLE_CHECKED:
            errors.append(_bad("V9", "supply_sample_checked", "枚举外值"))
        sample_note = get("supply_sample_note") or None
        if sample_checked != "none" and not sample_note:
            errors.append(_bad("V10", "supply_sample_note", "非 none 的抽检必须填写 sample_note"))
        price_raw = get("supply_price")
        if price_raw.startswith("-"):
            errors.append(_bad("V22", "supply_price", "输入金额必须非负"))
            price = None
        else:
            price = _parse_amount(price_raw, "supply_price", errors)
        if get("supply_price_minor"):
            minor_value = _parse_minor(get_minor("supply_price_minor"), "supply_price_minor", errors)
            if minor_value is not None and get("supply_price") and minor_value != price:
                errors.append(_bad("V21", "supply_price_minor", "与 supply_price 数值不一致"))
            price = minor_value if price is None else price
        basis = get("supply_price_basis") or None
        if basis and basis not in PRICE_BASIS:
            errors.append(_bad("V9", "supply_price_basis", "枚举外值"))
        downloadable = get("supply_downloadable") or "unknown"
        if downloadable not in YES_NO_UNKNOWN:
            errors.append(_bad("V9", "supply_downloadable", "必须是 yes/no/unknown"))
        evidence_excerpt = _check_len(get("supply_evidence_excerpt"), "supply_evidence_excerpt", MAX_EXCERPT, errors)
        evidence_url = get("supply_evidence_url")
        if evidence_excerpt and not evidence_url:
            errors.append(_bad("V10", "supply_evidence_url", "提供条款摘录时必须提供条款证据链接"))
        if origin in DATA_ORIGINS:
            _check_url(evidence_url, "supply_evidence_url", origin, errors)
        evidence_fact = get("supply_evidence_fact_kind") or "fact"
        if evidence_fact not in {"fact", "estimate", "assumption"}:
            errors.append(_bad("V9", "supply_evidence_fact_kind", "枚举外值"))
        supply = {
            "provider_name": provider,
            "provider_url": s_url,
            "url_norm": url_norm(s_url),
            "native_id": get("supply_native_id") or None,
            "origin_type": origin_type,
            "format_version": get("supply_format_version"),
            "unit_price_minor": price,
            "price_basis": basis,
            "price_valid_until": _check_date(get("supply_price_valid_until"), "supply_price_valid_until", errors),
            "license_summary": get("supply_license_summary") or None,
            "license_scope_note": get("supply_license_scope_note") or None,
            "license_evidence_url": evidence_url or None,
            "license_evidence_excerpt": evidence_excerpt or None,
            "license_evidence_fact_kind": evidence_fact,
            "downloadable": downloadable,
            "commercial_allowed": licenses["supply_commercial_allowed"],
            "redistribute_allowed": licenses["supply_redistribute_allowed"],
            "resale_allowed": licenses["supply_resale_allowed"],
            "sample_checked": sample_checked,
            "sample_note": sample_note,
            "last_checked_at": _check_at(get("supply_last_checked_at"), "supply_last_checked_at", errors),
        }

    # ---- cost group
    variant = get("scenario_variant") or "base"
    currency = get("currency") or "CNY"
    if currency != "CNY":
        errors.append(_bad("V15", "currency", "v1 仅支持 CNY"))
    if origin in DATA_ORIGINS:
        _check_url(get("cost_supply_url"), "cost_supply_url", origin, errors)
    costs: list[CostSpec] = []
    money_values: dict[str, int | None] = {}
    for column, (role, basis, value_kind) in COST_MAP.items():
        raw_value = get(column)
        if value_kind == "rate":
            bp = _parse_int(raw_value or None, column, errors, 0, 10000)
            if bp is None:
                continue
            costs.append(
                CostSpec(role=role, basis=basis, value_kind="rate", rate_bp=bp, variant=variant,
                         currency=currency, supply_url=get("cost_supply_url") or None)
            )
            continue
        if raw_value.startswith("-"):
            errors.append(_bad("V22", column, "输入金额必须非负"))
            continue
        alias = f"{column}_minor"
        alias_raw = get_minor(alias)
        minor_value = _parse_minor(alias_raw, alias, errors) if alias in MONEY_MINOR_ALIASES else None
        yuan_value = _parse_amount(raw_value, column, errors) if raw_value else None
        if minor_value is not None and yuan_value is not None and minor_value != yuan_value:
            errors.append(_bad("V21", alias, f"与 {column} 数值不一致"))
            continue
        value = yuan_value if yuan_value is not None else minor_value
        money_values[column] = value
        if value is None:
            continue
        if column == "procurement_recurring_cost" and not get("procurement_period"):
            errors.append(_bad("V16", "procurement_period", "recurring 采购必须提供 monthly/quarterly/yearly"))
            continue
        costs.append(
            CostSpec(
                role=role,
                basis=basis,
                value_kind="money",
                money_minor=value,
                period=get("procurement_period") if basis == "recurring" else None,
                variant=variant,
                currency=currency,
                supply_url=get("cost_supply_url") or None,
            )
        )
    # manual labour: minutes (+ optional hourly rate)
    minutes = _parse_int(get("manual_minutes") or None, "manual_minutes", errors, 0, 1440)
    hourly_minor = None
    if get("manual_hourly_rate_minor"):
        hourly_minor = _parse_minor(get_minor("manual_hourly_rate_minor"), "manual_hourly_rate_minor", errors)
    elif get("manual_hourly_rate"):
        hourly_minor = _parse_amount(get("manual_hourly_rate"), "manual_hourly_rate", errors)
    if minutes is not None:
        costs.append(
            CostSpec(
                role="manual_labor",
                basis="per_order",
                value_kind="minutes",
                minutes=minutes,
                hourly_rate_minor=hourly_minor,
                variant=variant,
                currency=currency,
                supply_url=get("cost_supply_url") or None,
            )
        )
    if get("procurement_cost") and get("supply_price"):
        procurement = money_values.get("procurement_cost")
        supply_price = supply["unit_price_minor"] if supply else None
        if procurement is not None and supply_price is not None and procurement != supply_price:
            warnings.append(("V19", "procurement_cost 与 supply_price 不一致，可能重复计入"))

    parsed = ParsedRow(row_no=row_no, base={"title": title, "data_origin": origin, "category": category or None,
                                            "use_case": use_case or None, "delivery_form": delivery_form or None,
                                            "notes": notes, "observed_at": observed_at},
                       demand=demand, supply=supply, costs=costs, warnings=warnings)
    for err in errors:
        err.row_no = row_no
        parsed.add_error(err)
    return parsed


# ---------------------------------------------------------------- parsing

def parse_csv(text: str, cfg: dict) -> tuple[list[tuple[int, dict]], list[tuple[str, str]], list[str]]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration:
        raise AppError("CSV 内容为空", code="validation_failed")
    header = [h.strip() for h in header]
    if "title" not in header or "data_origin" not in header:
        raise AppError("表头缺少 title/data_origin", code="validation_failed", status=422)
    if len(set(header)) != len(header):
        raise AppError("表头存在重复列", code="validation_failed", status=422)
    unknown = [h for h in header if h not in ALL_COLUMNS]
    warnings = [("V18", f"未知列已忽略：{h}") for h in unknown]
    rows: list[tuple[int, dict]] = []
    header_set = set(header)
    for index, fields in enumerate(reader, start=1):
        if not fields or all(not f.strip() for f in fields):
            continue
        if set(f.strip() for f in fields) == header_set:
            raise AppError("数据区出现重复表头", code="validation_failed", status=422)
        record = {}
        for pos, name in enumerate(header):
            record[name] = fields[pos].strip() if pos < len(fields) else ""
        if len(fields) != len(header):
            record["__width_error__"] = f"V25 行宽 {len(fields)} 与表头 {len(header)} 不一致"
        rows.append((index, record))
    return rows, warnings, header


def parse_json(text: str, cfg: dict) -> tuple[list[tuple[int, dict]], list[tuple[str, str]], list[str]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(f"JSON 解析失败：{exc.msg}", code="validation_failed")
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise AppError("JSON 导入必须是对象数组", code="unsupported_format")
    keys: set[str] = set()
    for item in payload:
        keys.update(item.keys())
    unknown = sorted(k for k in keys if k not in ALL_COLUMNS)
    warnings = [("V18", f"未知列已忽略：{k}") for k in unknown]
    rows = [(index, {k: ("" if v is None else v) for k, v in item.items()}) for index, item in enumerate(payload, start=1)]
    return rows, warnings, sorted(keys)


# ---------------------------------------------------------------- writes

def _insert_review(conn, kind, ref_type, ref_id, reason, origin, *, ref_gate=None, ref_id_b=None, blocking=0):
    add_review(conn, kind, ref_type, ref_id, reason, origin, ref_gate=ref_gate, ref_id_b=ref_id_b, blocking=blocking)


def process_row(conn, cfg: dict, row: ParsedRow, batch_id: str, source_names: dict[str, str]) -> dict:
    """Write one validated row; returns {records, actions, warnings, suspect}."""
    origin = row.base["data_origin"]
    now = now_utc()
    records: list[dict] = []
    skipped: list[dict] = []
    actions: list[str] = []

    # ---- demand signal + candidate identity
    demand_key = None
    if row.demand:
        source_id = source_names[row.demand["source_name"]]
        # Identity namespace uses the registered source NAME, matching the frozen examples
        # (`n:xianyu:1001` / `u:xianyu:<url_norm>`); the row keeps the internal source_id FK.
        demand_key, key_source = demand_identity_key(row.demand["source_name"], row.demand["native_id"], row.demand["url_norm"])
    else:
        source_id = None
        key_source = None

    title_hash = title_norm_hash(row.base["title"])
    identity_key, identity_source = candidate_identity_key(demand_key, title_hash)

    cand = conn.execute(
        "SELECT id FROM candidate WHERE data_origin=? AND identity_key=?", (origin, identity_key)
    ).fetchone()
    if cand:
        candidate_id = cand["id"]
        actions.append("duplicate_skipped")
        skipped.append({"type": "candidate", "id": candidate_id})
    else:
        candidate_id = slug_id("c")
        conn.execute(
            "INSERT INTO candidate(id,title,identity_key,identity_source,category,use_case,delivery_form,notes,status,"
            "status_reason,status_updated_at,manual_override,title_norm_hash,data_origin,import_batch_id,created_at,updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,'none',?,?,?,?,?)",
            (candidate_id, row.base["title"], identity_key, identity_source, row.base["category"], row.base["use_case"],
             row.base["delivery_form"], row.base["notes"], "pending", "derived:pending|gates_incomplete", now,
             title_hash, origin, batch_id, now, now),
        )
        records.append({"type": "candidate", "id": candidate_id})
        actions.append("created")

    # ---- demand signal
    if row.demand:
        excerpt = row.demand["excerpt"]
        fingerprint = content_hash(excerpt, row.base["title"])
        observed_at = row.base["observed_at"] or now
        observed_source = "source" if row.base["observed_at"] else "import_time"
        latest = conn.execute(
            "SELECT id, content_hash, version_no FROM demand_signal WHERE data_origin=? AND source_id=? AND identity_key=?"
            " ORDER BY version_no DESC LIMIT 1",
            (origin, source_id, demand_key),
        ).fetchone()
        signal_id = None
        if latest and latest["content_hash"] == fingerprint:
            signal_id = latest["id"]
            conn.execute("UPDATE demand_signal SET last_seen_at=? WHERE id=?", (now, signal_id))
            actions.append("duplicate_skipped")
            skipped.append({"type": "demand_signal", "id": signal_id})
        else:
            version = (latest["version_no"] + 1) if latest else 1
            signal_id = slug_id("d")
            conn.execute(
                "INSERT INTO demand_signal(id,candidate_id,source_id,native_id,url,url_norm,identity_key,identity_source,"
                "excerpt,signal_kind,engagement_json,published_at,published_date,observed_at,observed_at_source,"
                "original_author,is_repost,origin_group_key,content_hash,version_no,first_seen_at,last_seen_at,"
                "data_origin,import_batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (signal_id, candidate_id, source_id, row.demand["native_id"], row.demand["url"], row.demand["url_norm"],
                 demand_key, key_source, excerpt, row.demand["kind"], row.demand["engagement"], row.demand["published_at"],
                 row.demand["published_date"], observed_at, observed_source, row.demand["author"],
                 row.demand["is_repost"], row.demand["origin_group_key"], fingerprint, version, now, now, origin, batch_id),
            )
            records.append({"type": "demand_signal", "id": signal_id})
            if latest:
                conn.execute("UPDATE demand_signal SET superseded_by=? WHERE id=?", (signal_id, latest["id"]))
                actions.append("version_added")
            else:
                actions.append("created")
            evidence_id = slug_id("e")
            conn.execute(
                "INSERT INTO evidence(id,candidate_id,evidence_type,demand_signal_id,source_id,source_url,native_id,excerpt,"
                "fact_kind,observed_at,data_origin,import_batch_id,created_at)"
                " VALUES (?,?,'demand',?,?,?,?,?,'fact',?,?,?,?)",
                (evidence_id, candidate_id, signal_id, source_id, row.demand["url"], row.demand["native_id"], excerpt,
                 observed_at, origin, batch_id, now),
            )
            records.append({"type": "evidence", "id": evidence_id})
        # cross-object suspicion: same fingerprint, different identity
        other = conn.execute(
            "SELECT id FROM demand_signal WHERE data_origin=? AND content_hash=? AND identity_key<>? LIMIT 1",
            (origin, fingerprint, demand_key),
        ).fetchone()
        if other:
            _insert_review(conn, "dup_suspect", "demand_signal", signal_id,
                           f"内容指纹相同但身份不同（{demand_key}）", origin, ref_id_b=other["id"])
            actions.append("suspect_review")

    # ---- supply offer
    if row.supply:
        supply = row.supply
        existing = conn.execute(
            "SELECT * FROM supply_offer WHERE data_origin=? AND candidate_id=? AND url_norm=? AND format_version=?",
            (origin, candidate_id, supply["url_norm"], supply["format_version"]),
        ).fetchone()
        supply_id = None
        if existing is None:
            supply_id = slug_id("sp")
            conn.execute(
                "INSERT INTO supply_offer(id,candidate_id,provider_name,provider_url,url_norm,native_id,origin_type,"
                "format_version,unit_price_minor,currency,price_basis,price_valid_until,license_summary,license_scope_note,"
                "license_evidence_url,downloadable,commercial_allowed,redistribute_allowed,resale_allowed,sample_checked,"
                "sample_note,status,last_checked_at,data_origin,created_at,updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'candidate',?,?,?,?)",
                (supply_id, candidate_id, supply["provider_name"], supply["provider_url"], supply["url_norm"],
                 supply["native_id"], supply["origin_type"], supply["format_version"], supply["unit_price_minor"],
                 "CNY", supply["price_basis"], supply["price_valid_until"], supply["license_summary"],
                 supply["license_scope_note"], supply["license_evidence_url"], supply["downloadable"],
                 supply["commercial_allowed"], supply["redistribute_allowed"], supply["resale_allowed"],
                 supply["sample_checked"], supply["sample_note"], supply["last_checked_at"], origin, now, now),
            )
            records.append({"type": "supply_offer", "id": supply_id})
            actions.append("created")
        else:
            supply_id = existing["id"]
            changed = any(
                [
                    existing["unit_price_minor"] != supply["unit_price_minor"],
                    existing["commercial_allowed"] != supply["commercial_allowed"],
                    existing["redistribute_allowed"] != supply["redistribute_allowed"],
                    existing["resale_allowed"] != supply["resale_allowed"],
                    existing["sample_checked"] != supply["sample_checked"],
                    (existing["sample_note"] or None) != (supply["sample_note"] or None),
                    (existing["license_evidence_url"] or None) != (supply["license_evidence_url"] or None),
                ]
            )
            if changed:
                price_changed = existing["unit_price_minor"] != supply["unit_price_minor"]
                conn.execute(
                    "UPDATE supply_offer SET unit_price_minor=?, commercial_allowed=?, redistribute_allowed=?,"
                    "resale_allowed=?, sample_checked=?, sample_note=?, license_evidence_url=?, last_checked_at=?,"
                    "updated_at=? WHERE id=?",
                    (supply["unit_price_minor"], supply["commercial_allowed"], supply["redistribute_allowed"],
                     supply["resale_allowed"], supply["sample_checked"], supply["sample_note"],
                     supply["license_evidence_url"], supply["last_checked_at"], now, supply_id),
                )
                records.append({"type": "supply_offer", "id": supply_id})
                actions.append("created")
                if price_changed:
                    _insert_review(conn, "cost_changed", "supply_offer", supply_id, "货源价格变化", origin,
                                   ref_gate="cost", blocking=1)
                    downgrade_cost_gate_if_verified(conn, candidate_id, "import: 货源价格变化")
                    actions.append("suspect_review")
            else:
                actions.append("duplicate_skipped")
                skipped.append({"type": "supply_offer", "id": supply_id})
        # clause evidence only when an excerpt was provided (never fabricate one), and only
        # when it is new or actually changed (re-import must not proliferate evidence rows)
        if supply["license_evidence_excerpt"]:
            previous_evidence = None
            if existing is not None and existing["license_evidence_id"]:
                previous_evidence = conn.execute(
                    "SELECT id, excerpt FROM evidence WHERE id=?", (existing["license_evidence_id"],)
                ).fetchone()
            need_evidence = previous_evidence is None or previous_evidence["excerpt"] != supply["license_evidence_excerpt"]
            if need_evidence:
                evidence_id = slug_id("e")
                conn.execute(
                    "INSERT INTO evidence(id,candidate_id,evidence_type,source_id,source_url,excerpt,fact_kind,observed_at,"
                    "supersedes_id,data_origin,import_batch_id,created_at) VALUES (?,?,'supply_distribution',?,?,?,?,?,?,?,?,?)",
                    (evidence_id, candidate_id, source_id, supply["license_evidence_url"],
                     supply["license_evidence_excerpt"], supply["license_evidence_fact_kind"],
                     row.base["observed_at"] or now, previous_evidence["id"] if previous_evidence else None,
                     origin, batch_id, now),
                )
                conn.execute("UPDATE supply_offer SET license_evidence_id=? WHERE id=?", (evidence_id, supply_id))
                records.append({"type": "evidence", "id": evidence_id})

    # ---- cost items
    supply_lookup = {
        r["url_norm"]: r["id"]
        for r in conn.execute(
            "SELECT id, url_norm FROM supply_offer WHERE candidate_id=?", (candidate_id,)
        ).fetchall()
    }
    for spec in row.costs:
        bound_supply = supply_lookup.get(url_norm(spec.supply_url)) if spec.supply_url else None
        if spec.supply_url and not bound_supply:
            row.warnings.append(("V18", f"cost_supply_url 未匹配到本候选货源：{spec.supply_url}"))
        active = conn.execute(
            "SELECT * FROM cost_item WHERE candidate_id=? AND role=? AND basis=? AND variant=? AND is_active=1",
            (candidate_id, spec.role, spec.basis, spec.variant),
        ).fetchone()
        same = bool(
            active
            and active["value_kind"] == spec.value_kind
            and active["money_minor"] == spec.money_minor
            and active["rate_bp"] == spec.rate_bp
            and active["minutes"] == spec.minutes
            and active["hourly_rate_minor"] == spec.hourly_rate_minor
            and (active["period"] or None) == (spec.period or None)
        )
        if same:
            actions.append("duplicate_skipped")
            skipped.append({"type": "cost_item", "id": active["id"]})
            continue
        if active is not None:
            conn.execute("UPDATE cost_item SET is_active=0 WHERE id=?", (active["id"],))
        cost_id = slug_id("ci")
        conn.execute(
            "INSERT INTO cost_item(id,candidate_id,supply_offer_id,role,basis,value_kind,money_minor,rate_bp,minutes,"
            "hourly_rate_minor,period,variant,currency,fact_kind,assumption_note,is_active,supersedes_id,data_origin,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'assumption',NULL,1,?,?,?)",
            (cost_id, candidate_id, bound_supply, spec.role, spec.basis, spec.value_kind, spec.money_minor, spec.rate_bp,
             spec.minutes, spec.hourly_rate_minor, spec.period, spec.variant, spec.currency,
             active["id"] if active else None, origin, now),
        )
        records.append({"type": "cost_item", "id": cost_id})
        actions.append("created")
        if active is not None:
            downgrade_cost_gate_if_verified(conn, candidate_id, "import: 成本项实质变化")

    apply_status(conn, candidate_id)
    suspect = "suspect_review" in actions
    if suspect:
        final_action = "suspect_review"
    elif "rejected" in actions:
        final_action = "rejected"
    elif "version_added" in actions:
        final_action = "version_added"
    elif "created" in actions:
        final_action = "created"
    else:
        final_action = "duplicate_skipped"
    return {"records": records, "skipped": skipped, "action": final_action, "warnings": row.warnings}


# ---------------------------------------------------------------- entry point

def _canonical_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def handle_import(conn, cfg, *, fmt: str, body: bytes, filename: str | None, mode: str,
                  format_version: int, client_ref: str | None) -> tuple[dict, int, bool]:
    if mode not in {"atomic", "partial", "validate"}:
        raise AppError("mode 仅支持 atomic/partial/validate", code="unsupported_format")
    if format_version != 1:
        raise AppError("仅支持 format_version=1", code="unsupported_format")
    if fmt not in {"csv", "json"}:
        raise AppError("format 仅支持 csv/json", code="unsupported_format")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError("文件必须是 UTF-8 编码", code="encoding_error")

    if fmt == "csv":
        raw_rows, file_warnings, header = parse_csv(text, cfg)
        columns = header
    else:
        raw_rows, file_warnings, columns = parse_json(text, cfg)

    if len(raw_rows) > cfg["max_rows_per_batch"]:
        raise AppError(f"单批最多 {cfg['max_rows_per_batch']} 行", code="validation_failed")
    if not raw_rows:
        raise AppError("空文件或仅表头", code="validation_failed")

    source_names = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM source").fetchall()}
    parsed_rows = [validate_row(row_no, raw, cfg, source_names) for row_no, raw in raw_rows]
    width_errors = [raw.get("__width_error__") for _, raw in raw_rows if raw.get("__width_error__")]
    for row_no, raw in raw_rows:
        if raw.get("__width_error__"):
            parsed_rows[row_no - 1].add_error(RowError("V25", "row", raw["__width_error__"], row_no))

    counts = {"created": 0, "duplicate_skipped": 0, "version_added": 0, "suspect_review": 0, "rejected": 0, "warning": 0}
    for parsed in parsed_rows:
        if parsed.errors():
            counts["rejected"] += 1
    counts["warning"] = len(file_warnings)

    if mode == "validate":
        rows_out = [
            {
                "row_no": parsed.row_no,
                "preview_action": "rejected" if parsed.errors() else "created",
                "errors": [e.as_detail() for e in parsed.errors()],
                "warnings": [{"code": c, "reason": r} for c, r in parsed.warnings],
            }
            for parsed in parsed_rows
        ]
        return {
            "mode": "validate",
            "saved": False,
            "format": fmt,
            "rows_total": len(parsed_rows),
            "counts": counts,
            "project_errors": [{"row": 0, "field": "columns", "reason": f"{c}: {r}"} for c, r in file_warnings],
            "rows": rows_out,
        }, 200, False

    req_hash = _canonical_hash(body)
    if client_ref:
        existing = conn.execute(
            "SELECT request_hash, response_json FROM idempotency_key WHERE scope='import' AND client_ref=?",
            (client_ref,),
        ).fetchone()
        if existing:
            if existing["request_hash"] == req_hash:
                return json.loads(existing["response_json"]), 200, True
            raise AppError("client_ref 已用于不同的导入内容", code="conflict", status=409)

    batch_id = slug_id("ib")
    started = now_utc()
    fatal = counts["rejected"] > 0 and mode == "atomic"
    conn.execute("BEGIN")
    try:
        # Placeholder status inside this transaction; the final status is written before COMMIT
        # (the contract's import_batch.status enum has no "running" value).
        conn.execute(
            "INSERT INTO import_batch(id,file_name,format,format_version,mode,encoding,status,rows_total,created_at)"
            " VALUES (?,?,?,?,?,'utf-8',?,?,?)",
            (batch_id, filename or f"inline.{fmt}", fmt, format_version, mode,
             "rejected" if fatal else "committed", len(parsed_rows), started),
        )
        if fatal:
            conn.execute("COMMIT")
        else:
            rows_out = []
            for parsed in parsed_rows:
                if parsed.errors():
                    rows_out.append({"row_no": parsed.row_no, "action": "rejected",
                                     "errors": [e.as_detail() for e in parsed.errors()],
                                     "warnings": [{"code": c, "reason": r} for c, r in parsed.warnings]})
                    for err in parsed.errors():
                        conn.execute(
                            "INSERT INTO import_row_result(id,batch_id,row_no,action,reason_code,reason_detail)"
                            " VALUES (?,?,?,'rejected',?,?)",
                            (slug_id("rr"), batch_id, parsed.row_no, err.code, err.reason),
                        )
                    continue
                outcome = process_row(conn, cfg, parsed, batch_id, source_names)
                counts[outcome["action"]] = counts.get(outcome["action"], 0) + 1
                rows_out.append({"row_no": parsed.row_no, "action": outcome["action"], "records": outcome["records"],
                                 "warnings": [{"code": c, "reason": r} for c, r in outcome["warnings"]]})
                for record in outcome["records"]:
                    conn.execute(
                        "INSERT INTO import_row_result(id,batch_id,row_no,action,record_type,record_id)"
                        " VALUES (?,?,?,?,?,?)",
                        (slug_id("rr"), batch_id, parsed.row_no, outcome["action"], record["type"], record["id"]),
                    )
                for record in outcome.get("skipped", []):
                    # V17: sub-records are judged independently, so a row can create one record
                    # and skip another; each decision is queryable.
                    conn.execute(
                        "INSERT INTO import_row_result(id,batch_id,row_no,action,record_type,record_id)"
                        " VALUES (?,?,?,'duplicate_skipped',?,?)",
                        (slug_id("rr"), batch_id, parsed.row_no, record["type"], record["id"]),
                    )
                for code, reason in outcome["warnings"]:
                    conn.execute(
                        "INSERT INTO import_row_result(id,batch_id,row_no,action,reason_code,reason_detail)"
                        " VALUES (?,?,?,'warning',?,?)",
                        (slug_id("rr"), batch_id, parsed.row_no, code, reason),
                    )
            status = "committed" if counts["rejected"] == 0 else "partial_committed"
            conn.execute(
                "UPDATE import_batch SET status=?, rows_created=?, rows_duplicate=?, rows_version_added=?"
                ", rows_suspect=?, rows_rejected=?, finished_at=? WHERE id=?",
                (status, counts["created"], counts["duplicate_skipped"], counts["version_added"],
                 counts["suspect_review"], counts["rejected"], now_utc(), batch_id),
            )
            conn.execute(
                "INSERT INTO run_record(id,run_type,trigger,logical_date,source_id,status,started_at,finished_at,"
                "items_found,items_new,items_dup,notes) VALUES (?,'import','manual',?,NULL,?,?,?,?,?,?,?)",
                (slug_id("r"), today_local(cfg["tz_offset_hours"]), "ok" if status == "committed" else "partial",
                 started, now_utc(), len(parsed_rows), counts["created"], counts["duplicate_skipped"], f"batch={batch_id}"),
            )
            payload = {
                "batch_id": batch_id,
                "status": status,
                "format": fmt,
                "mode": mode,
                "rows_total": len(parsed_rows),
                "counts": counts,
                "rows": rows_out,
            }
            if client_ref:
                conn.execute(
                    "INSERT INTO idempotency_key(id,scope,client_ref,request_hash,response_json,record_id,created_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (slug_id("ik"), "import", client_ref, req_hash, json.dumps(payload, ensure_ascii=False), batch_id, now_utc()),
                )
            conn.execute("COMMIT")
            return payload, 201, False
    except Exception:
        conn.execute("ROLLBACK")
        raise

    # atomic failure path: batch + row reasons are kept, no business rows exist
    for parsed in parsed_rows:
        if parsed.errors():
            for err in parsed.errors():
                conn.execute(
                    "INSERT INTO import_row_result(id,batch_id,row_no,action,reason_code,reason_detail)"
                    " VALUES (?,?,?,'rejected',?,?)",
                    (slug_id("rr"), batch_id, parsed.row_no, err.code, err.reason),
                )
    conn.execute("UPDATE import_batch SET finished_at=?, error_summary=? WHERE id=?",
                 (now_utc(), f"{counts['rejected']} 行校验失败（atomic 未写入业务数据）", batch_id))
    payload = {
        "batch_id": batch_id,
        "status": "rejected",
        "format": fmt,
        "mode": mode,
        "rows_total": len(parsed_rows),
        "counts": counts,
        "rows": [
            {"row_no": p.row_no, "action": "rejected", "errors": [e.as_detail() for e in p.errors()],
             "warnings": [{"code": c, "reason": r} for c, r in p.warnings]}
            for p in parsed_rows if p.errors()
        ],
    }
    return payload, 422, False
