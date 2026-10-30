"""平台预算守卫 + 风险闸门（真实导航前必须先过这里）。

规则（与计划 P5 一致，回应退回意见）：
- 账本路径固定（`platform_budget.DEFAULT_PATH`），CLI 不再提供覆盖参数；
- **风险优先于记录**：`enforce_risk()` 在任何记录构建之前调用；验证码/登录墙/403/429 → 写锁后抛错；
- **不吞错**：`lock()` / `record_result()` 写失败一律抛 `GuardBlocked`，由调用方转成非零退出码；
- 平台已锁 / 批次未授权 / 窗口已关 / 剩余 0 → `GuardBlocked`，调用方不得启动浏览器。
"""

from __future__ import annotations

from tools.selection.access import platform_budget as pb
from tools.selection.access import weibo as weibo_mod

#: 403/429/432 这类 HTTP 状态直接判风险（页面文本之外的第二条独立信号）。
RISK_STATUS = {403: "http_403", 429: "http_429", 432: "http_432", 418: "http_418"}


class GuardBlocked(Exception):
    def __init__(self, stop: str, detail: str = "") -> None:
        super().__init__(f"{stop}:{detail}" if detail else stop)
        self.stop = stop
        self.detail = detail


def open_guard(path=None, site: str = "weibo") -> pb.PlatformLedger:
    """固定权威账本；`path` 只给测试/库函数用，CLI 不暴露。"""
    return pb.open_default(path, site=site)


def risk_reason(*, text: str = "", http_status: int | None = None) -> str | None:
    """返回风险原因；None 表示没有命中。文本命中只认真实墙词，不认"获取验证码"。"""
    if http_status in RISK_STATUS:
        return RISK_STATUS[int(http_status)]
    for marker in weibo_mod.RISK_MARKERS:
        if marker and marker in (text or ""):
            return f"text:{marker}"
    return None


def enforce_risk(ledger: pb.PlatformLedger, *, text: str = "",
                 http_status: int | None = None, source: str = "rpa.search") -> None:
    """命中风险就写锁并抛错；写锁失败也要抛（不吞）。"""
    reason = risk_reason(text=text, http_status=http_status)
    if reason is None:
        return
    lock(ledger, reason, source=source)
    raise GuardBlocked(f"risk:{reason}")


def precheck(ledger: pb.PlatformLedger, batch_id: str | None) -> dict:
    """只读判定；不 charge、不导航。"""
    locked, reason = ledger.locked()
    summary = ledger.summary(batch_id) if batch_id else {"authorized": False}
    decision = {"batch_id": batch_id, "locked": bool(locked), "lock_reason": reason,
                "authorized": bool(summary.get("authorized")),
                "remaining": summary.get("remaining"),
                "window_open": summary.get("window_open"),
                "used": summary.get("used"),
                "authorized_calls": summary.get("authorized_calls"),
                "seed_used": summary.get("seed_used")}
    if locked:
        raise GuardBlocked("platform_locked", str(reason or ""))
    if not batch_id:
        raise GuardBlocked("batch_id_required")
    if not decision["authorized"]:
        raise GuardBlocked("no_authorized_batch", str(batch_id))
    if decision["window_open"] is False:
        raise GuardBlocked("batch_window_closed", str(batch_id))
    if decision["remaining"] is not None and int(decision["remaining"]) <= 0:
        raise GuardBlocked("calls_exhausted",
                           f"{decision['used']}/{decision['authorized_calls']}")
    return decision


def charge_search(ledger: pb.PlatformLedger, batch_id: str, detail: str) -> dict:
    try:
        return ledger.charge(batch_id, "search", detail=detail, source="rpa.search")
    except pb.PlatformBudgetError as exc:
        raise GuardBlocked(f"platform:{exc.code}", str(exc.detail or "")) from exc


def charge_nav(ledger: pb.PlatformLedger, batch_id: str, detail: str,
               *, source: str = "rpa.login") -> dict:
    """任何主动导航都要先预扣 `active_nav`，再启动浏览器。"""
    try:
        return ledger.charge(batch_id, "active_nav", detail=detail, source=source)
    except pb.PlatformBudgetError as exc:
        raise GuardBlocked(f"platform:{exc.code}", str(exc.detail or "")) from exc


def reserve_records(ledger: pb.PlatformLedger, batch_id: str, count: int) -> dict:
    try:
        return ledger.reserve_records(batch_id, count, source="rpa.records")
    except pb.PlatformBudgetError as exc:
        raise GuardBlocked(f"platform:{exc.code}", str(exc.detail or "")) from exc


#: 结果事件名：必须与预扣的调用类型一一对应，不能都写成 search_result。
RESULT_EVENTS = {"active_nav": "active_nav_result", "search": "search_result",
                 "comments": "comments_result"}


def record_result(ledger: pb.PlatformLedger, batch_id: str, kind: str, outcome: str, *,
                  source: str) -> None:
    """登记已扣费调用的结果：`kind` 与预扣一致，事件名就是 `<kind>_result`。

    `source` 直接写进账本 `events.source`（`rpa.login` / `rpa.search`），
    不再统一冒充 `weibo.result`。写失败**不吞**：抛 GuardBlocked 由调用方转非零。
    """
    if outcome not in ("success", "failed", "unknown"):
        raise GuardBlocked("invalid_outcome", str(outcome))
    event = RESULT_EVENTS.get(str(kind))
    if event is None:
        raise GuardBlocked("unknown_result_kind", str(kind))
    try:
        ledger.audit(batch_id, event, detail=str(outcome), source=source)
    except Exception as exc:  # noqa: BLE001 - 任何写失败都必须变成明确停止
        code = getattr(exc, "code", type(exc).__name__)
        raise GuardBlocked("result_write_failed", str(code)) from exc


def lock(ledger: pb.PlatformLedger, reason: str, source: str = "rpa.search") -> None:
    """写锁失败**不吞**：抛 GuardBlocked。"""
    try:
        ledger.lock(reason, source=source)
    except pb.PlatformBudgetError as exc:
        raise GuardBlocked("lock_write_failed", f"{exc.code}") from exc
