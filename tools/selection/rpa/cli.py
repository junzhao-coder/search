"""RPA 命令行入口：`python -m tools.selection.rpa <command>`。

子命令：
- `extract --cards-json F`：把页面内 JS 取出的**可见卡片数组**转成记录（不解析原始 HTML）。
- `window`：打开可见窗口做**本地**验证；`--url` 只接受 `about:blank` 与
  `docs/validation/v10/browser-rpa/fixtures/` 下的 `file://`；本地模式封网。
  `--desktop-proof` 额外给出**桌面级证据**：前台窗口匹配 + 窗口矩形 + 整屏截图。
- `login`：可见窗口打开微博登录页，**用户本人**操作。顺序固定：
  `precheck(固定权威账本) → 预扣 active_nav → 启动浏览器 → 桌面证据 → 等待/超时 → 关闭
  → 风险锁 / 结果登记`。不代填、不读 cookie 值；登录态只报 `unknown` 或页面可见证据。
- `live-search`：真实搜索。只有 `--allow-live` 且批次已授权、未锁、窗口内、剩余>0
  才会启动浏览器；顺序固定：`precheck → 预扣 search → 导航 → 风险(HTTP/墙词) →
  可见卡片提取 → 记录预留 → 结果登记`。失败非零、不退款、不重试、不换词。

退出码沿用 `tools.selection.access.codes`：
0 成功 / 3 空 / 4 不支持或未知 / 5 风险 / 6 守卫或策略拒绝 / 7 传输 / 8 输入错误 /
11 登录超时 / 12 窗口显示的不是目标页 / 13 登录未知。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import uuid

from tools.selection.access import browser as browser_mod
from tools.selection.access import codes
from tools.selection.access import records as rec
from tools.selection.access import weibo as weibo_mod

from . import comments as comments_mod
from . import desktop as desktop_mod
from . import extract as extract_mod
from . import guard as guard_mod
from . import probe as probe_mod
from . import session as session_mod

FIXTURES = pathlib.Path(__file__).resolve().parents[3] / "docs" / "validation" / "v10" / \
    "browser-rpa" / "fixtures"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

#: 窗口显示的不是目标页（标题不一致）——可见性前提不成立，非零且不等待扫码。
EXIT_VISIBILITY = 12

LOGIN_POLL_INTERVAL = 2.0


def _settle_window_title(desktop, *, attempts: int = 15, interval: float = 0.2) -> dict:
    """等 OS 窗口标题追上页面标题，消除"页面已就绪、窗口标题还没刷新"的竞态误判。

    Chrome 更新窗口标题是异步的（页面 `document.title` 先变，OS 标题后变），
    直接判会得到假阴性；这里只读轮询最多 ~3s，仍不匹配才交给 gate 拦。
    """
    if not desktop or desktop.get("window_title_matches_page") is True:
        return desktop
    waited = desktop_mod.wait_title_match(desktop.get("hwnd") or 0,
                                          desktop.get("page_title"),
                                          attempts=attempts, interval=interval)
    desktop["window_title"] = waited.get("window_title")
    desktop["window_title_matches_page"] = waited.get("matched")
    desktop["title_wait"] = waited
    return desktop


def _visibility_gate(desktop) -> str | None:
    """`window_title_matches_page` 不是 True 时返回 stop；否则 None。

    这是"窗口显示目标页"的**可判读前提**：截图/前台匹配都只能证明"某个窗口被置前"，
    不能证明置前的是登录页。标题不一致时直接拒绝，不进入等待扫码。
    """
    if not desktop:
        return "window_showing_other_tab"
    match = desktop.get("window_title_matches_page")
    if match is True:
        return None
    return "window_showing_other_tab"


# -- seams (tests patch these; nothing else needs to know about them) ------
def _open_ledger():
    """固定权威账本；没有路径参数，CLI 不提供任何覆盖入口。"""
    return guard_mod.open_guard()


def _new_session(profile, *, live: bool, timeout: float | None = None,
                 user_agent: str | None = None):
    """真实参数必须带进会话：timeout 是 CDP 单步超时，UA 是浏览器启动开关。"""
    kwargs: dict = {"live": live}
    if timeout is not None:
        kwargs["timeout"] = float(timeout)
    if user_agent:
        kwargs["user_agent"] = str(user_agent)
    return session_mod.VisibleSession(profile, **kwargs)


def _monotonic() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _user_confirmed() -> bool:
    """Windows 控制台里按 Enter = 用户确认登录完成；非 TTY 一律 False（走超时）。"""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
        import msvcrt
    except Exception:  # noqa: BLE001 - 非 Windows/无控制台：只靠超时
        return False
    try:
        while msvcrt.kbhit():
            if msvcrt.getwch() in ("\r", "\n"):
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


# -- helpers ---------------------------------------------------------------
def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _outcome(exit_code: int) -> str:
    if exit_code == codes.EXIT_OK:
        return "success"
    if exit_code in (codes.EXIT_PARTIAL, codes.EXIT_TRANSPORT):
        return "unknown"
    return "failed"


def _local_url(raw: str) -> tuple[str | None, str | None]:
    """只放行 about:blank 与 fixtures 目录内的 file://；返回 (url, 拒绝原因)。"""
    text = (raw or "").strip()
    if text in ("about:blank", ""):
        return "about:blank", None
    if not text.lower().startswith("file:"):
        return None, "non_local_url"
    # Windows file URL 的 path 形如 `/D:/dir/x.html`；url2pathname 才会给出 `D:\dir\x.html`
    path = pathlib.Path(urllib.request.url2pathname(urllib.parse.urlsplit(text).path))
    try:
        resolved = path.resolve()
        resolved.relative_to(FIXTURES.resolve())
    except (ValueError, OSError):
        return None, "outside_fixtures"
    if not resolved.is_file():
        return None, "fixture_missing"
    return resolved.as_uri(), None


def _page_summary(page: dict | None, *, include_title: bool = False) -> dict:
    page = page or {}
    out = {"final_url": weibo_mod.redact_detail(page.get("url") or ""),
           "ready": page.get("ready"), "http_status": page.get("http_status"),
           "text_len": page.get("text_len"), "timed_out": page.get("timed_out"),
           "visibility": page.get("visibility")}
    if include_title:
        out["title"] = page.get("title")
    return out


def _blocked(payload: dict, exc: guard_mod.GuardBlocked, stage: str) -> int:
    """守卫拒绝：不建 transport、不启动浏览器、不扣未扣的额度。"""
    _emit({**payload, "ok": False, "exit": codes.EXIT_BUDGET,
           "stop": f"blocked:{exc.stop}", "detail": exc.detail, "stage": stage,
           "browser_started": False,
           "note": "守卫拒绝：未启动浏览器，未发生导航"})
    return codes.EXIT_BUDGET


def _settle(ledger, batch_id, payload: dict, exit_code: int, stop: str | None, *,
            charged: bool, stage: str, result_kind: str, result_source: str,
            records=(), parsed=None, page=None, desktop=None, out_path=None,
            extra=None) -> int:
    """先登记结果，再写导出；两步失败都不许被当成成功。

    - 结果登记失败：`records=[]`、**不写导出文件**、exit 6 `result_write_failed`
      （输出里 `result_persisted=false`）；
    - 导出失败：exit 9 `export_failed`（已读到的记录仍列出，但不落盘）。
    """
    record_error = None
    if charged:
        try:
            guard_mod.record_result(ledger, batch_id, result_kind,
                                    _outcome(exit_code), source=result_source)
        except guard_mod.GuardBlocked as exc:
            record_error = exc.stop
            exit_code, stop = codes.EXIT_BUDGET, "result_write_failed"
            records = ()                    # 未登记的结果不得输出，也不得落盘
    written = None
    export_error = None
    if records and out_path:
        try:
            written = rec.write_records(list(records), out_path)
        except (OSError, ValueError) as exc:
            export_error = f"{type(exc).__name__}:{exc}"
            exit_code, stop = codes.EXIT_EXPORT, f"export_failed:{type(exc).__name__}"
    records = list(records)
    out = {**payload, "ok": exit_code == codes.EXIT_OK, "exit": exit_code, "stop": stop,
           "stage": stage, "count": len(records), "records": records,
           "output": written, "export_error": export_error,
           "result_kind": result_kind, "result_source": result_source,
           "parsed_structure": (parsed or {}).get("structure"),
           "diagnostics": (parsed or {}).get("diagnostics"),
           "assumptions": (parsed or {}).get("assumptions"),
           "page": _page_summary(page, include_title=payload.get("command") == "login"),
           "desktop": desktop,
           "desktop_visibility_proven": bool((desktop or {}).get("proven")),
           "result_persisted": record_error is None, "record_error": record_error}
    if extra:
        out.update(extra)
    _emit(out)
    return exit_code


def _login_state(result: dict) -> dict:
    """只报页面可见证据；命中任一强信号才算 ok，否则一律 unknown。"""
    page = result.get("page") or {}
    signed = result.get("verdict") == "signed_in"
    evidence = result.get("evidence")
    if signed and evidence:
        # 兼容旧字段：hasLogout 仍写成 page:logout_control，其余写 page:<rule>
        label = "logout_control" if evidence == "hasLogout" else str(evidence)
        evidence_text = f"page:{label}"
    else:
        evidence_text = "page:logout_control" if signed else None
    return {"verdict": "ok" if signed else "unknown",
            "evidence": evidence_text,
            "final_url": weibo_mod.redact_detail(page.get("url") or ""),
            "http_status": page.get("http_status"),
            "text_len": page.get("text_len"),
            "note": "未读 cookie 值；cookie 存在不等于在线"}


# -- commands --------------------------------------------------------------
def cmd_extract(args) -> int:
    target = pathlib.Path(args.cards_json)
    if not target.is_file():
        _emit({"command": "extract", "exit": codes.EXIT_INPUT, "stop": "input_error",
               "detail": f"cards json not found: {args.cards_json}"})
        return codes.EXIT_INPUT
    try:
        cards = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"command": "extract", "exit": codes.EXIT_INPUT, "stop": "input_error",
               "detail": type(exc).__name__})
        return codes.EXIT_INPUT
    if isinstance(cards, dict):
        cards = cards.get("cards") or []
    collected_at = _utc()
    if args.kind == "search":
        parsed = extract_mod.extract_cards(cards, collected_at=collected_at, limit=args.limit)
        exit_code = codes.EXIT_OK
        if parsed["stop"] == "empty":
            exit_code = codes.EXIT_EMPTY
        elif parsed["stop"] == "unknown":
            exit_code = codes.EXIT_UNSUPPORTED
        records = parsed["records"]
    else:
        card = cards[0] if isinstance(cards, list) and cards else None
        parsed = extract_mod.extract_detail(card, collected_at=collected_at)
        records = [parsed["record"]] if parsed.get("record") else []
        exit_code = codes.EXIT_OK if parsed["stop"] is None else codes.EXIT_UNSUPPORTED
    written = rec.write_records(records, args.out) if args.out else None
    _emit({"command": "extract", "kind": args.kind, "exit": exit_code,
           "count": len(records), "stop": parsed["stop"],
           "structure": parsed["structure"], "diagnostics": parsed["diagnostics"],
           "assumptions": parsed["assumptions"], "output": written, "records": records})
    return exit_code


def cmd_window(args) -> int:
    url, refusal = _local_url(args.url)
    info = browser_mod.available()
    plan = {"command": "window", "profile": str(pathlib.Path(args.profile).expanduser()),
            "url": url or args.url, "headless": False, "screenshot": args.screenshot,
            "dump_cards": args.dump_cards, "browser": info, "local_only": True,
            "desktop_proof_requested": bool(args.desktop_proof),
            "desktop_visibility_proven": False,
            "note": "只做本地 fixture 渲染验证；不代填凭据、不读 cookie、不导航真实站点"}
    if refusal:
        _emit({**plan, "exit": codes.EXIT_BUDGET, "stop": f"blocked:{refusal}"})
        return codes.EXIT_BUDGET
    if args.dry_run:
        _emit({**plan, "exit": codes.EXIT_OK, "dry_run": True,
               "would_launch": info["usable"],
               "would_prove_desktop": bool(args.desktop_proof)})
        return codes.EXIT_OK
    if not info["usable"]:
        _emit({**plan, "exit": codes.EXIT_TRANSPORT, "stop": "browser_unavailable"})
        return codes.EXIT_TRANSPORT
    session = _new_session(args.profile, live=False)
    try:
        started = session.start()
        tab, blocked = session.open_local(url)
        nav = session.navigate_stable(tab)
        evidence = session.evidence(
            tab, screenshot=pathlib.Path(args.screenshot) if args.screenshot else None)
        cards = None
        if args.dump_cards:
            dumped = session.dump_cards(tab)
            target = pathlib.Path(args.dump_cards)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(dumped, ensure_ascii=False, indent=1),
                              encoding="utf-8")
            cards = {"path": str(target), "count": len(dumped.get("cards") or [])}
        desktop = None
        if args.desktop_proof:
            nonce = f"DSH-RPA-PROOF-{uuid.uuid4().hex[:8]}"
            session.set_title(tab, nonce)
            shot = pathlib.Path(args.desktop_screenshot) if args.desktop_screenshot else \
                pathlib.Path(args.profile).expanduser() / "desktop-proof.png"
            desktop = session.desktop_proof(screenshot=shot, title_hint=nonce)
        exit_code, stop = codes.EXIT_OK, None
        audit = evidence["network_audit"]
        if audit.get("external_completed"):
            exit_code, stop = codes.EXIT_RISK, "external_request_completed"
        elif nav["escaped"]:
            exit_code, stop = codes.EXIT_UNSUPPORTED, "navigation_escaped"
        elif nav["timed_out"]:
            exit_code, stop = codes.EXIT_UNSUPPORTED, "navigation_timeout"
        if desktop is not None and not desktop["proven"]:
            exit_code, stop = codes.EXIT_TRANSPORT, \
                f"desktop_proof_failed:{desktop.get('reason')}"
        mirror = {}
        if desktop is not None:
            # 顶层镜像三个关键字段，便于外部按字段名直接核对
            mirror = {"foreground_matched": desktop.get("foreground_matched"),
                      "window_rect": desktop.get("window_rect"),
                      "desktop_screenshot_bytes": desktop.get("desktop_screenshot_bytes")}
        _emit({**plan, **mirror, "exit": exit_code, "stop": stop, "started": started,
               "network_block": blocked, "navigation": nav, "evidence": evidence,
               "desktop": desktop,
               "desktop_visibility_proven": bool(desktop and desktop.get("proven")),
               "external_attempts_blocked": audit.get("external_attempts", 0) - \
               audit.get("external_completed", 0), "cards": cards})
        if not args.no_wait and exit_code == codes.EXIT_OK:
            input("本地页面已渲染；按 Enter 关闭窗口…")
        return exit_code
    except session_mod.SessionUnavailable as exc:
        _emit({**plan, "exit": codes.EXIT_TRANSPORT, "stop": str(exc)})
        return codes.EXIT_TRANSPORT
    finally:
        session.close()


def cmd_login(args) -> int:
    """可见窗口 + 用户本人登录；先 precheck、再预扣 active_nav、最后才启动浏览器。"""
    profile = str(pathlib.Path(args.profile).expanduser())
    default_profile = str(pathlib.Path(weibo_mod.DEFAULT_PROFILE).expanduser())
    expected_profile = str((REPO_ROOT / "docs" / "validation" / "v10" / "weibo-login"
                            / "profile"))
    payload = {"command": "login", "profile": profile, "batch_id": args.batch_id,
               "timeout_s": args.timeout, "headless": False, "browser_started": False,
               "cookie_values_read": False,
               "profile_exists": pathlib.Path(profile).is_dir(),
               "profile_source": "explicit" if profile != default_profile else "default",
               "default_profile": default_profile,
               "expected_profile": expected_profile,
               "profile_matches_expected": os.path.normcase(profile) == os.path.normcase(
                   expected_profile)}
    ledger = _open_ledger()
    try:
        try:
            batch = guard_mod.precheck(ledger, args.batch_id)
        except guard_mod.GuardBlocked as exc:
            return _blocked(payload, exc, "precheck")
        try:
            guard_mod.charge_nav(ledger, args.batch_id, "login")
        except guard_mod.GuardBlocked as exc:
            return _blocked(payload, exc, "charge")
        session = _new_session(profile, live=True)
        page: dict = {}
        desktop = None
        polls = 0
        result: dict = {"verdict": "unknown", "stop": "not_started", "risk_reason": None}

        def finish(exit_code: int, stop, *, stage: str, status: str) -> int:
            session.close()                      # 先关窗口再输出，避免“已关”说谎
            return _settle(ledger, args.batch_id, payload, exit_code, stop, charged=True,
                           stage=stage, result_kind="active_nav",
                           result_source="rpa.login", page=page, desktop=desktop,
                           extra={"batch": batch, "polls": polls, "status": status,
                                  "window_closed": True,
                                  "login_state": _login_state(result)})

        try:
            meta = session.start()
            payload["browser_started"] = True
            payload["session"] = meta
            tab = session.open_live(weibo_mod.LOGIN_URL)
            desktop = session.desktop_proof(tab=tab, screenshot=None)  # 登录页禁止自动截图
            desktop = _settle_window_title(desktop)     # 等窗口标题追上页面标题
            gate = _visibility_gate(desktop)
            if gate is not None:
                print(f"[rpa] 可见性前提不成立：{gate}；"
                      f"窗口标题={desktop.get('window_title')!r} "
                      f"页面标题={desktop.get('page_title')!r}；不等待扫码。",
                      file=sys.stderr)
                return finish(EXIT_VISIBILITY, gate, stage="visibility",
                              status="window_showing_other_tab")
            if not desktop.get("proven"):
                print(f"[rpa] 桌面可见性未证实：{desktop.get('reason')}；"
                      f"窗口句柄={desktop.get('hwnd')} 矩形={desktop.get('window_rect')}",
                      file=sys.stderr)
            elif args.confirm:
                print("窗口已置前并核对为前台窗口。请本人在窗口内完成登录，"
                      "完成后按 Enter；超时按 --timeout 自动关闭。", file=sys.stderr)
            keepalive = desktop_mod.Keepalive(desktop.get("hwnd") or 0)
            payload["keepalive_start"] = keepalive.start()
            desktop["topmost_set"] = payload["keepalive_start"].get("topmost_set")
            desktop["topmost"] = dict(payload["keepalive_start"])
            result = _wait_login(session, tab, timeout=args.timeout,
                                 confirm=args.confirm, keepalive=keepalive)
            payload["keepalive"] = keepalive.finish()
            page = result.get("page") or {}
            polls = int(result.get("polls") or 0)
            stop = result.get("stop")
            if result["verdict"] == "risk":
                reason = result.get("risk_reason") or "login_risk"
                try:
                    guard_mod.lock(ledger, reason, source="rpa.login")
                except guard_mod.GuardBlocked as exc:
                    return finish(codes.EXIT_BUDGET,
                                  f"lock_write_failed:{exc.detail or exc.stop}",
                                  stage="risk", status="risk_lock_failed")
                return finish(codes.EXIT_RISK, stop, stage="risk", status="risk")
            exit_code = {"signed_in": codes.EXIT_OK,
                         "timeout": codes.EXIT_LOGIN_TIMEOUT}.get(
                             result["verdict"], codes.EXIT_LOGIN_UNKNOWN)
            return finish(exit_code, stop, stage="login", status=result["verdict"])
        except session_mod.SessionUnavailable as exc:
            return finish(codes.EXIT_TRANSPORT, str(exc), stage="session",
                          status="session_unavailable")
        except Exception as exc:  # noqa: BLE001 - 已扣费的调用必须结算再非零
            return finish(codes.EXIT_TRANSPORT,
                          f"login_exception:{type(exc).__name__}",
                          stage="exception", status="error")
        finally:
            session.close()
    finally:
        ledger.close()


def _wait_login(session, tab, *, timeout: float, confirm: bool,
                poll: float = LOGIN_POLL_INTERVAL, keepalive=None) -> dict:
    """轮询页面可见信号：风险优先 → 已登录 → 用户确认 → 超时。

    每轮顺带 `keepalive.tick()`：只在前台丢失时重新置前（不每轮抢焦点）。
    """
    deadline = _monotonic() + max(1.0, float(timeout))
    polls = 0
    page: dict = {}
    while True:
        polls += 1
        if keepalive is not None:
            keepalive.tick()
        try:
            page = session.read_page(tab)
            signals = session.read_signals(tab, weibo_mod.SIGNED_IN_JS)
        except Exception as exc:  # noqa: BLE001 - 窗口被用户关掉也要如实结束
            return {"verdict": "unknown", "polls": polls, "page": page,
                    "stop": f"page_read_failed:{type(exc).__name__}", "risk_reason": None}
        # 登录页只认"墙词"（access.weibo.LOGIN_WALL_MARKERS）+ HTTP 状态：
        # 整页 RISK_MARKERS 里的「登录后查看/请先登录」在登录页是正常文案，会把窗口误关。
        reason = guard_mod.risk_reason(text="", http_status=page.get("http_status"))
        if reason is None:
            reason = weibo_mod.detect_login_wall(page.get("text") or "")
        if reason:
            return {"verdict": "risk", "polls": polls, "page": page,
                    "stop": f"risk:{reason}", "risk_reason": reason}
        if weibo_mod.signed_in_verdict(signals):
            return {"verdict": "signed_in", "polls": polls, "page": page,
                    "stop": None, "risk_reason": None,
                    "evidence": weibo_mod.signed_in_evidence(signals)}
        if confirm and _user_confirmed():
            return {"verdict": "confirmed", "polls": polls, "page": page,
                    "stop": "user_confirmed", "risk_reason": None}
        if _monotonic() >= deadline:
            return {"verdict": "timeout", "polls": polls, "page": page,
                    "stop": "login_timeout", "risk_reason": None}
        _sleep(poll)


def cmd_live_search(args) -> int:
    """真实搜索：守卫全部在浏览器启动之前；风险判定在记录构建之前。"""
    payload = {"command": "live-search", "keyword": args.keyword,
               "batch_id": args.batch_id, "allow_live": bool(args.allow_live),
               "profile": str(pathlib.Path(args.profile).expanduser()),
               "limit": args.limit, "browser_started": False,
               "note": "单次导航；失败不退款、不重试、不换词"}
    if not args.allow_live:
        _emit({**payload, "ok": False, "exit": codes.EXIT_BUDGET,
               "stop": "blocked:allow_live_required", "stage": "policy",
               "desktop_visibility_proven": False,
               "note": "真实导航需显式 --allow-live 且批次已授权；本次未启动浏览器"})
        return codes.EXIT_BUDGET
    ledger = _open_ledger()
    try:
        try:
            batch = guard_mod.precheck(ledger, args.batch_id)
        except guard_mod.GuardBlocked as exc:
            return _blocked({**payload, "batch": None}, exc, "precheck")
        try:
            guard_mod.charge_search(ledger, args.batch_id, "search")
        except guard_mod.GuardBlocked as exc:
            return _blocked({**payload, "batch": batch}, exc, "charge")
        session = _new_session(payload["profile"], live=True,
                               timeout=args.timeout, user_agent=args.user_agent)
        page: dict = {}
        desktop = None
        parsed = None

        def finish(exit_code: int, stop, *, stage: str, status: str, records=(),
                   extra=None) -> int:
            session.close()                      # 先关窗口再输出，避免“已关”说谎
            merged = {"batch": batch, "status": status,
                      "final_url": page.get("final_url") or page.get("url")}
            merged.update(extra or {})
            return _settle(ledger, args.batch_id, payload, exit_code, stop, charged=True,
                           stage=stage, result_kind="search",
                           result_source="rpa.search", records=records, parsed=parsed,
                           page=page, desktop=desktop, out_path=args.out, extra=merged)

        try:
            meta = session.start()
            payload["browser_started"] = True
            payload["session"] = meta
            requested_search_url = weibo_mod.search_url(args.keyword)
            if str(getattr(args, "sort", "") or "").lower() == "hot":
                requested_search_url += "&xsort=hot"       # 热度排序：拿有互动的样本
            payload["requested_url"] = requested_search_url
            tab = session.open_live(requested_search_url)
            desktop = session.desktop_proof(tab=tab, screenshot=None)  # 真实页面不自动截图
            desktop = _settle_window_title(desktop)     # 等窗口标题追上页面标题
            gate = _visibility_gate(desktop)
            if gate is not None:
                return finish(EXIT_VISIBILITY, gate, stage="visibility",
                              status="window_showing_other_tab")
            keepalive = desktop_mod.Keepalive(desktop.get("hwnd") or 0)
            payload["keepalive_start"] = keepalive.start()
            desktop["topmost_set"] = payload["keepalive_start"].get("topmost_set")
            desktop["topmost"] = dict(payload["keepalive_start"])
            page = session.wait_ready(tab, keepalive=keepalive)
            payload["keepalive"] = keepalive.finish()
            reason = guard_mod.risk_reason(text=page.get("text") or "",
                                           http_status=page.get("http_status"))
            if reason:
                try:
                    guard_mod.lock(ledger, reason, source="rpa.search")
                except guard_mod.GuardBlocked as exc:
                    return finish(codes.EXIT_BUDGET,
                                  f"lock_write_failed:{exc.detail or exc.stop}",
                                  stage="risk", status="risk_lock_failed")
                return finish(codes.EXIT_RISK, f"risk:{reason}", stage="risk",
                              status="risk")
            if page.get("timed_out"):
                # 页面从未到达 readyState=complete：不解析、不输出记录
                return finish(codes.EXIT_TRANSPORT, "readiness_timeout",
                              stage="read", status="not_ready")
            requested_host = (urllib.parse.urlsplit(requested_search_url).hostname or "").lower()
            final_url = page.get("final_url") or page.get("url") or ""
            final_host = (urllib.parse.urlsplit(final_url).hostname or "").lower()
            if requested_host and final_host and requested_host != final_host:
                # 典型：桌面入口 + 移动 UA → 被重定向到 m.weibo.cn（0 卡片）
                return finish(codes.EXIT_UNSUPPORTED, "redirected_elsewhere",
                              stage="navigate", status="redirected",
                              extra={"requested_url": requested_search_url,
                                     "final_url": final_url,
                                     "requested_host": requested_host,
                                     "final_host": final_host})
            dumped = session.dump_desktop_cards(tab)
            parsed = extract_mod.extract_cards(dumped.get("cards") or [],
                                               collected_at=_utc(), limit=args.limit)
            if parsed["stop"] in ("empty", "unknown"):
                code = codes.EXIT_EMPTY if parsed["stop"] == "empty" else \
                    codes.EXIT_UNSUPPORTED
                return finish(code, parsed["stop"], stage="extract",
                              status="no_records",
                              extra={"cards_in": (parsed.get("diagnostics") or {}).get(
                                  "cards_in"),
                                  "rejected": (parsed.get("diagnostics") or {}).get(
                                      "rejected")})
            records = parsed["records"]
            try:
                reserved = guard_mod.reserve_records(ledger, args.batch_id, len(records))
            except guard_mod.GuardBlocked as exc:
                return finish(codes.EXIT_BUDGET, f"blocked:{exc.stop}",
                              stage="reserve", status="reserve_refused")
            return finish(codes.EXIT_OK, None, stage="done", status="records",
                          records=records,
                          extra={"records_target": reserved.get("records_target"),
                                 "records_used": reserved.get("records_used"),
                                 "over_cap": reserved.get("over_cap"),
                                 "over_by": reserved.get("over_by"),
                                 "records_detail": parsed.get("details") or [],
                                 "cards_in": (parsed.get("diagnostics") or {}).get("cards_in"),
                                 "rejected": (parsed.get("diagnostics") or {}).get("rejected")})
        except session_mod.SessionUnavailable as exc:
            return finish(codes.EXIT_TRANSPORT, str(exc), stage="session",
                          status="session_unavailable")
        except Exception as exc:  # noqa: BLE001 - 已扣费必须结算再非零
            return finish(codes.EXIT_TRANSPORT,
                          f"live_search_exception:{type(exc).__name__}",
                          stage="exception", status="error")
        finally:
            session.close()
    finally:
        ledger.close()


def cmd_probe(args) -> int:
    """结构侦察：单次导航，只输出选择器计数与 id 一致性，**不落正文**。"""
    if bool(args.keyword) == bool(args.url):
        _emit({"command": "probe", "ok": False, "exit": codes.EXIT_INPUT,
               "stop": "input_error",
               "detail": "exactly one of --keyword / --url is required"})
        return codes.EXIT_INPUT
    requested_url = args.url or weibo_mod.search_url(args.keyword)
    payload = {"command": "probe", "keyword": args.keyword, "requested_url": requested_url,
               "batch_id": args.batch_id,
               "profile": str(pathlib.Path(args.profile).expanduser()),
               "browser_started": False,
               "note": "单次导航；只统计结构，不取正文；失败不重试"}
    ledger = _open_ledger()
    try:
        try:
            batch = guard_mod.precheck(ledger, args.batch_id)
        except guard_mod.GuardBlocked as exc:
            return _blocked({**payload, "batch": None}, exc, "precheck")
        try:
            guard_mod.charge_nav(ledger, args.batch_id, "probe", source="rpa.probe")
        except guard_mod.GuardBlocked as exc:
            return _blocked({**payload, "batch": batch}, exc, "charge")
        session = _new_session(payload["profile"], live=True, timeout=args.timeout,
                               user_agent=getattr(args, "user_agent", None))
        page: dict = {}
        desktop = None
        summary: dict | None = None

        def finish(exit_code: int, stop, *, stage: str, status: str,
                   extra=None) -> int:
            session.close()
            merged = {"batch": batch, "status": status,
                      "requested_url": requested_url,
                      "final_url": page.get("final_url") or page.get("url")}
            merged.update(extra or {})
            return _settle(ledger, args.batch_id, payload, exit_code, stop,
                           charged=True, stage=stage, result_kind="active_nav",
                           result_source="rpa.probe", records=[], parsed=summary,
                           page=page, desktop=desktop, out_path=args.out,
                           extra=merged)

        try:
            payload["browser_started"] = True
            session.start()
            tab = (session.open_live_hooked(requested_url)
                   if getattr(args, "audit_network", False)
                   else session.open_live(requested_url))
            desktop = session.desktop_proof(tab=tab, screenshot=None)
            desktop = _settle_window_title(desktop)
            gate = _visibility_gate(desktop)
            if gate is not None:
                return finish(EXIT_VISIBILITY, gate, stage="visibility",
                              status="window_showing_other_tab")
            keepalive = desktop_mod.Keepalive(desktop.get("hwnd") or 0)
            payload["keepalive_start"] = keepalive.start()
            desktop["topmost_set"] = payload["keepalive_start"].get("topmost_set")
            page = session.wait_ready(tab, keepalive=keepalive)
            payload["keepalive"] = keepalive.finish()
            reason = guard_mod.risk_reason(text=page.get("text") or "",
                                           http_status=page.get("http_status"))
            if reason:
                try:
                    guard_mod.lock(ledger, reason, source="rpa.probe")
                except guard_mod.GuardBlocked as exc:
                    return finish(codes.EXIT_BUDGET,
                                  f"lock_write_failed:{exc.detail or exc.stop}",
                                  stage="risk", status="risk_lock_failed")
                return finish(codes.EXIT_RISK, f"risk:{reason}", stage="risk",
                              status="risk")
            if page.get("timed_out"):
                return finish(codes.EXIT_TRANSPORT, "readiness_timeout",
                              stage="read", status="not_ready")
            html = session.html(tab)
            if getattr(args, "audit_network", False):
                payload["hook_installed"] = session.hook_installed(tab)
                payload["hook_error"] = getattr(session, "last_hook_error", None)
            summary = probe_mod.summarize(
                html, requested_url=requested_url,
                url=page.get("final_url") or requested_url,
                http_status=page.get("http_status"), ready=page.get("ready"),
                title=page.get("title"), text_len=page.get("text_len"))
            if summary.get("surface") == "detail":
                # 详情页：等正文容器出现且连续两次采样稳定；<500 字视为未渲染
                stable = session.wait_render_stable(tab, min_len=500, attempts=20,
                                                    interval=0.5, keepalive=keepalive)
                payload["render_wait"] = stable
                if stable["text_len"] != page.get("text_len"):
                    page = session.read_page(tab) or page
                    html = session.html(tab)
                    summary = probe_mod.summarize(
                        html, requested_url=requested_url,
                        url=page.get("final_url") or requested_url,
                        http_status=page.get("http_status"), ready=page.get("ready"),
                        title=page.get("title"), text_len=page.get("text_len"))
            if getattr(args, "dump_card_act", False):
                summary["card_act"] = probe_mod.summarize_card_act(html, limit=5)
            if getattr(args, "scroll", 0):
                payload["scroll"] = session.scroll_page(tab, segments=int(args.scroll))
                page = session.read_page(tab) or page
                html = session.html(tab)
            if getattr(args, "dump_comments", False) or getattr(args, "audit_network", False):
                before = probe_mod.summarize_comments(html)
                hook = session.install_net_hook(tab)
                clicked = {"clicked": False, "reason": "click_not_requested"}
                if getattr(args, "click_comment", False):
                    for attempt in range(2):      # 账本 MIN_INTERVAL=15s：等一次再扣
                        try:
                            guard_mod.charge_nav(ledger, args.batch_id, "comments",
                                                 source="rpa.probe.comments")
                            break
                        except guard_mod.GuardBlocked as exc:
                            if attempt == 0 and "interval" in str(exc.stop):
                                time.sleep(16.0)
                                continue
                            return _blocked({**payload, "batch": batch,
                                             "status": "comments_blocked"}, exc,
                                            "charge_comments")
                    clicked = session.click_comment_entry(tab)
                payload["comment_click"] = clicked
                payload["net_hook"] = hook
                page2 = session.wait_ready(tab, keepalive=keepalive)
                html2 = session.html(tab)
                after = probe_mod.summarize_comments(html2)
                summary["comments"] = {**after, "clicked": clicked,
                                       "before": {"items": before["items"],
                                                  "containers": before["containers"]},
                                       "after": {"items": after["items"],
                                                 "containers": after["containers"]},
                                       "text_len_before": page.get("text_len"),
                                       "text_len_after": page2.get("text_len")}
                if getattr(args, "audit_network", False):
                    summary["network"] = probe_mod.summarize_network(
                        session.read_net_hook(tab))
                exit_code, stop = probe_mod.verdict(summary)
            exit_code, stop = probe_mod.verdict(summary)
            if args.out:
                pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                pathlib.Path(args.out).write_text(
                    json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
            return finish(exit_code, stop, stage="probe",
                          status="cards" if exit_code == codes.EXIT_OK else
                          ("risk" if exit_code == codes.EXIT_RISK else "no_cards"),
                          extra={"summary": summary, "output": args.out})
        except session_mod.SessionUnavailable as exc:
            return finish(codes.EXIT_TRANSPORT, str(exc), stage="session",
                          status="session_unavailable")
        except Exception as exc:  # noqa: BLE001 - 已扣费必须结算再非零
            return finish(codes.EXIT_TRANSPORT,
                          f"probe_exception:{type(exc).__name__}",
                          stage="exception", status="error")
        finally:
            session.close()
    finally:
        ledger.close()


def cmd_comments(args) -> int:
    """评论入口：页面自身端点 `buildComments`，一页或多页，保留父子关系。"""
    payload = {"command": "comments", "mid": args.mid, "batch_id": args.batch_id,
               "limit": args.limit, "max_pages": args.max_pages,
               "browser_started": False,
               "note": "页面自身端点 buildComments；每次调用预扣预算；不落响应原文"}
    ledger = _open_ledger()
    try:
        try:
            batch = guard_mod.precheck(ledger, args.batch_id)
        except guard_mod.GuardBlocked as exc:
            return _blocked({**payload, "batch": None}, exc, "precheck")
        try:
            guard_mod.charge_nav(ledger, args.batch_id, "detail", source="rpa.comments")
        except guard_mod.GuardBlocked as exc:
            return _blocked({**payload, "batch": batch}, exc, "charge_nav")
        session = _new_session(payload["profile"] if "profile" in payload else
                               str(pathlib.Path(args.profile).expanduser()),
                               live=True, timeout=args.timeout)
        page: dict = {}
        desktop = None
        pages: list[dict] = []

        def finish(exit_code: int, stop, *, stage: str, status: str,
                   records=(), extra=None) -> int:
            session.close()
            merged = {"batch": batch, "status": status}
            merged.update(extra or {})
            return _settle(ledger, args.batch_id, payload, exit_code, stop, charged=True,
                           stage=stage, result_kind="comments",
                           result_source="rpa.comments", records=records, parsed=None,
                           page=page, desktop=desktop, out_path=args.out, extra=merged)

        try:
            payload["browser_started"] = True
            session.start()
            tab = session.open_live("https://weibo.com/")
            desktop = session.desktop_proof(tab=tab, screenshot=None)
            page = session.wait_ready(tab)
            max_id = None
            for index in range(max(1, int(args.max_pages))):
                charged = False
                for attempt in range(2):          # MIN_INTERVAL=15s
                    try:
                        ledger.charge(args.batch_id, "comments",
                                      detail=f"page{index + 1}", source="rpa.comments")
                        charged = True
                        break
                    except Exception as exc:      # noqa: BLE001
                        if attempt == 0 and "interval" in str(exc):
                            time.sleep(16.0)
                            continue
                        return finish(codes.EXIT_BUDGET, "blocked:comments_charge",
                                      stage="charge", status="comments_blocked",
                                      extra={"pages": pages, "detail": str(exc)[:120]})
                url = comments_mod.page_url(args.mid, count=args.limit, max_id=max_id)
                res = session.fetch_json(tab, url)
                parsed = comments_mod.parse_page(res.get("json"))
                parsed["http_status"] = res.get("status")
                parsed["bytes"] = res.get("text_len")
                parsed["page_index"] = index + 1
                pages.append(parsed)
                max_id = parsed.get("max_id")
                if not charged or not max_id:
                    break
            merged = comments_mod.merge_pages(pages)
            all_records = merged["records"]
            records = all_records                     # v11：软目标，一条不丢
            if not all_records:
                return finish(codes.EXIT_EMPTY, "no_comments", stage="comments",
                              status="empty",
                              extra={"pages": pages, "total_number": merged["total_number"]})
            try:
                reserved = guard_mod.reserve_records(ledger, args.batch_id, len(records))
            except guard_mod.GuardBlocked as exc:
                return finish(codes.EXIT_BUDGET, f"blocked:{exc.stop}",
                              stage="reserve", status="reserve_refused",
                              extra={"pages": pages})
            return finish(codes.EXIT_OK, None, stage="done", status="comments",
                          records=records,
                          extra={"pages": pages, "total_number": merged["total_number"],
                                 "parsed_records": len(all_records),
                                 "kept_records": len(records),
                                 "records_target": reserved.get("records_target"),
                                 "records_used": reserved.get("records_used"),
                                 "over_cap": reserved.get("over_cap"),
                                 "over_by": reserved.get("over_by"),
                                 "parents": merged["parents"],
                                 "children": merged["children"],
                                 "max_id": merged["max_id"]})
        except session_mod.SessionUnavailable as exc:
            return finish(codes.EXIT_TRANSPORT, str(exc), stage="session",
                          status="session_unavailable")
        except Exception as exc:  # noqa: BLE001
            return finish(codes.EXIT_TRANSPORT,
                          f"comments_exception:{type(exc).__name__}",
                          stage="exception", status="error")
        finally:
            session.close()
    finally:
        ledger.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.selection.rpa",
        description="Browser-RPA entry (local fixture render + guarded live paths)")
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="offline: visible-card JSON -> records")
    ex.add_argument("--cards-json", required=True,
                    help="JSON produced by the in-page extractor (visible cards)")
    ex.add_argument("--kind", choices=("search", "detail"), default="search")
    ex.add_argument("--limit", type=int, default=5)
    ex.add_argument("--out", default=None)
    ex.set_defaults(func=cmd_extract)

    win = sub.add_parser("window", help="local visible window (about:blank or fixtures only)")
    win.add_argument("--profile", required=True)
    win.add_argument("--url", default="about:blank")
    win.add_argument("--screenshot", default=None)
    win.add_argument("--dump-cards", default=None)
    win.add_argument("--desktop-proof", action="store_true",
                     help="把 Chrome 主窗口置前，核对 GetForegroundWindow，并抓整屏截图")
    win.add_argument("--desktop-screenshot", default=None,
                     help="整屏截图路径（默认 <profile>/desktop-proof.png）")
    win.add_argument("--dry-run", action="store_true")
    win.add_argument("--no-wait", action="store_true")
    win.set_defaults(func=cmd_window)

    login = sub.add_parser("login", help="visible Weibo login window (user signs in)")
    login.add_argument("--profile", default=str(weibo_mod.DEFAULT_PROFILE))
    login.add_argument("--batch-id", default=None)
    login.add_argument("--timeout", type=float, default=300.0)
    login.add_argument("--confirm", action="store_true", default=True,
                       help="等待用户按 Enter 确认（默认开；非 TTY 自动退回超时）")
    login.add_argument("--no-confirm", dest="confirm", action="store_false")
    login.set_defaults(func=cmd_login)

    live = sub.add_parser("live-search", help="guarded real Weibo search (needs --allow-live)")
    live.add_argument("--keyword", required=True)
    live.add_argument("--profile", default=str(weibo_mod.DEFAULT_PROFILE))
    live.add_argument("--batch-id", default=None)
    live.add_argument("--allow-live", action="store_true",
                      help="显式允许真实导航；缺省即拒绝且不启动浏览器")
    live.add_argument("--limit", type=int, default=5)
    live.add_argument("--sort", choices=("hot", "time"), default=None,
                      help="hot 会在 URL 上追加 xsort=hot（热度排序）")
    live.add_argument("--out", default=None)
    live.add_argument("--timeout", type=float, default=60.0)
    live.add_argument("--user-agent", default=None,
                      help="启动 UA（默认浏览器自带桌面 UA；桌面入口 s.weibo.com 用移动 UA 会被重定向到 m.weibo.cn）")
    live.set_defaults(func=cmd_live_search)

    pr = sub.add_parser("probe", help="one guarded navigation: DOM structure counts only")
    pr.add_argument("--url", default=None,
                    help="explicit URL (local fixture / pinned entry); exclusive with --keyword")
    pr.add_argument("--keyword", default=None,
                    help="build the desktop search URL inside the CLI (no &/%% on the argv)")
    pr.add_argument("--profile", default=str(weibo_mod.DEFAULT_PROFILE))
    pr.add_argument("--batch-id", default=None)
    pr.add_argument("--out", default=None, help="write the structure summary JSON here")
    pr.add_argument("--timeout", type=float, default=60.0)
    pr.add_argument("--user-agent", default=None,
                    help="optional UA override (mobile pages need a mobile UA)")
    pr.add_argument("--dump-card-act", action="store_true",
                    help="also dump div.card-act structure (tags/classes/text shape; no body text)")
    pr.add_argument("--dump-comments", action="store_true",
                    help="open the detail page, click the comment entry once, dump comment structure")
    pr.add_argument("--audit-network", action="store_true",
                    help="hook fetch/XHR and report weibo requests (host/path/param names only)")
    pr.add_argument("--scroll", type=int, default=0,
                    help="scroll to bottom in N segments before dumping (triggers lazy load)")
    pr.add_argument("--click-comment", action="store_true",
                    help="also click the comment entry once (counts as an extra explicit call)")
    pr.set_defaults(func=cmd_probe)

    cm = sub.add_parser("comments", help="guarded: one page of comments via the page's own endpoint")
    cm.add_argument("--mid", required=True)
    cm.add_argument("--limit", type=int, default=20)
    cm.add_argument("--max-pages", type=int, default=1)
    cm.add_argument("--profile", default=str(weibo_mod.DEFAULT_PROFILE))
    cm.add_argument("--batch-id", default=None)
    cm.add_argument("--out", default=None)
    cm.add_argument("--timeout", type=float, default=60.0)
    cm.set_defaults(func=cmd_comments)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else codes.EXIT_INPUT
        _emit({"command": args.command, "exit": code, "stop": "input_error",
               "detail": str(exc)})
        return code


if __name__ == "__main__":
    sys.exit(main())
