"""Engine-agnostic trial loop: real actions, incremental IDs, honest stops.

The loop never treats "no new IDs" as "the end".  It records the exact stop
reason (no growth, configured scroll limit, cancellation, error) and always
returns `complete=False` unless a future caller supplies a verifiable end
marker.  The page's own event log is what proves a click / wheel / expand
really happened; the driver's return value alone is not enough.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import extract


@dataclass
class TrialConfig:
    scroll_step: int = 700
    max_scrolls: int = 8
    stall_limit: int = 2
    settle_ms: int = 250
    timeout_ms: int = 15000


def _empty_state() -> dict:
    return {"thread": {}, "records": {}, "events": [], "scroll": {"y": 0, "height": 0},
            "declared": None, "url": None, "title": None, "unidentified": 0}


def _merge(base: dict, new: dict) -> dict:
    out = {
        "thread": dict(base.get("thread") or {}),
        "records": dict(base.get("records") or {}),
        "events": new.get("events") or base.get("events") or [],
        "scroll": new.get("scroll") or base.get("scroll") or {"y": 0, "height": 0},
        "declared": new.get("declared") if new.get("declared") is not None
        else base.get("declared"),
        "url": new.get("url") or base.get("url"),
        "title": new.get("title") or base.get("title"),
        "unidentified": max(int(base.get("unidentified") or 0),
                            int(new.get("unidentified") or 0)),
    }
    for key, value in (new.get("thread") or {}).items():
        if value is not None and value != []:
            out["thread"][key] = value
    out["thread"]["missing"] = [field for field in extract.FIELDS
                                if out["thread"].get(field) is None]
    for key, record in (new.get("records") or {}).items():
        if key not in out["records"]:
            out["records"][key] = record
            continue
        old = out["records"][key]
        for field in ("text", "author", "published_at", "likes", "parent_id"):
            if old.get(field) is None and record.get(field) is not None:
                old[field] = record[field]
        old["missing"] = [field for field in extract.FIELDS if old.get(field) is None]
    return out


def _read(driver) -> dict:
    return extract.normalize(driver.evaluate(extract.EXTRACT_JS))


def _action(value) -> dict:
    return value if isinstance(value, dict) else {"clicked": False,
                                                   "raw": repr(value)[:120]}


def _scroll_loop(driver, state: dict, *, prefix: str, max_steps: int,
                 config: TrialConfig, should_cancel, mark) -> tuple[dict, str, int]:
    stall = 0
    steps = 0
    for _ in range(max(1, int(max_steps))):
        if should_cancel is not None and should_cancel():
            return state, "cancelled", steps
        before = state
        action = _action(driver.wheel(0, config.scroll_step))
        driver.wait(config.settle_ms)
        state = _merge(before, _read(driver))
        new_ids = sorted(set(extract.ids_of(state)) - set(extract.ids_of(before)))
        delta_y = state["scroll"]["y"] - before["scroll"]["y"]
        steps += 1
        mark(f"{prefix}_{steps}", new_ids=new_ids, scroll_dy=delta_y,
             action=action)
        if not new_ids and delta_y == 0:
            stall += 1
        else:
            stall = 0
        if stall >= max(1, int(config.stall_limit)):
            return state, "no_growth", steps
    return state, "scroll_limit", steps


def _at(timeline: list[dict], phase: str):
    for entry in timeline:
        if entry.get("phase") == phase:
            return entry.get("ms")
    return None


def _phases(timeline: list[dict], *, evidence_ms: float = 0.0,
            final_evidence_ms: float = 0.0) -> dict:
    marks = {phase: _at(timeline, phase) for phase in
             ("start_begin", "start_done", "navigate", "first_read",
              "final_read", "close")}
    out = {}
    for name, start, end in (
        ("start", "start_begin", "start_done"),
        ("navigate", "start_done", "navigate"),
        ("first_read", "navigate", "first_read"),
        ("actions", "first_read", "final_read"),
        ("close", "final_read", "close"),
    ):
        left, right = marks[start], marks[end]
        out[f"{name}_ms"] = round(right - left, 1) if (
            left is not None and right is not None) else None
    # Evidence capture is not a collection action: report it separately so
    # the two engines' action/close phases are comparable.
    out["evidence_ms"] = round(evidence_ms, 1)
    out["final_evidence_ms"] = round(final_evidence_ms, 1)
    if out["actions_ms"] is not None:
        out["actions_ms"] = round(max(0.0, out["actions_ms"] - evidence_ms), 1)
    if out["close_ms"] is not None:
        out["close_ms"] = round(max(0.0, out["close_ms"] - final_evidence_ms), 1)
    out["total_ms"] = marks["close"] if marks["close"] is not None else (
        timeline[-1].get("ms") if timeline else None)
    return out


def _stop_detail(stop: str, declared, observed: int, config: TrialConfig) -> str:
    if stop == "no_growth":
        return (f"连续 {config.stall_limit} 次滚动无新增原生 ID 且无页面位移；"
                f"页面声明 {declared if declared is not None else '未知'} 条，"
                f"可见 {observed} 条。没有可核验的到底标记，按部分/未知处理，"
                "不宣称取全。")
    if stop == "scroll_limit":
        return (f"达到配置的滚动上限 {config.max_scrolls} 次，仍可能有未加载内容；"
                f"可见 {observed} 条，按部分处理。")
    if stop == "cancelled":
        return (f"调用方取消；已保留 {observed} 条可见记录，可按原生 ID 续跑去重。")
    if stop.startswith("error:"):
        return (f"动作或读取异常（{stop.split(':', 1)[1]}）；已保留 "
                f"{observed} 条可见记录，未把异常当成到底。")
    return f"停止原因 {stop}；可见 {observed} 条，按部分/未知处理。"


def run_trial(driver, url: str, *, config: TrialConfig | None = None,
              should_cancel=None, evidence=None, final_evidence=None) -> dict:
    """Run one visible trial and return records, IDs, timeline and stop reason.

    `evidence(driver, state)` is called after the first read while the page is
    still open (the CLI uses it for a page screenshot / desktop proof).
    """
    config = config or TrialConfig()
    timeline: list[dict] = []
    started = time.perf_counter()

    def mark(phase: str, **detail) -> None:
        # `ms` is this timeline's clock.  A driver may return its own `ms` for
        # a phase; keep that as `driver_ms` instead of overwriting the clock.
        entry = {"phase": phase,
                 "ms": round((time.perf_counter() - started) * 1000, 1)}
        detail.pop("phase", None)
        driver_ms = detail.pop("ms", None)
        if driver_ms is not None:
            entry["driver_ms"] = driver_ms
        entry.update(detail)
        timeline.append(entry)

    result = {"engine": getattr(driver, "name", "unknown"), "url": url,
              "config": config.__dict__, "timeline": timeline, "stop": None,
              "stop_detail": None, "complete": False, "partial": True,
              "error": None, "thread": {}, "records": [], "ids": [],
              "declared": None, "observed": 0, "comment_count": 0, "lzl_count": 0,
              "events": [], "scroll": {"y": 0, "height": 0},
              "initial_scroll": {"y": 0, "height": 0}, "scroll_steps": 0,
              "expand": {}, "load_more": {}, "unidentified": 0, "fields": {},
              "action_evidence": {}, "evidence": None, "final_evidence": None,
              "evidence_ms": 0.0, "final_evidence_ms": 0.0,
              "environment": {}, "start_info": {}, "phases": {}}
    state = _empty_state()
    stop = None
    expand_clicked = False
    load_clicked = False
    scroll_steps = 0

    try:
        mark("start_begin")
        result["start_info"] = _action(driver.start())
        mark("start_done", **result["start_info"])
        result["environment"] = driver.environment()

        if should_cancel is not None and should_cancel():
            stop = "cancelled"
            mark("cancelled_before_navigate")
        else:
            mark("navigate", **_action(driver.goto(url)))
            state = _merge(state, _read(driver))
            result["initial_scroll"] = dict(state["scroll"])
            mark("first_read", ids=len(extract.ids_of(state)),
                 records=len(state["records"]))
            if evidence is not None:
                evidence_started = time.perf_counter()
                try:
                    result["evidence"] = evidence(driver, state)
                except Exception as exc:  # noqa: BLE001 - evidence must not kill the run
                    result["evidence"] = {"error": f"{type(exc).__name__}:{exc}"}
                finally:
                    result["evidence_ms"] = round(
                        (time.perf_counter() - evidence_started) * 1000, 1)

            if should_cancel is not None and should_cancel():
                stop = "cancelled"
                mark("cancelled_before_actions")
            else:
                result["expand"] = _action(driver.click("div.show-more-lzl"))
                expand_clicked = bool(result["expand"].get("clicked"))
                mark("expand", **result["expand"])
                driver.wait(config.settle_ms)
                state = _merge(state, _read(driver))
                mark("expand_read", ids=len(extract.ids_of(state)))

                result["load_more"] = _action(driver.click("#load-more"))
                load_clicked = bool(result["load_more"].get("clicked"))
                mark("load_more", **result["load_more"])
                driver.wait(config.settle_ms)
                before_load = set(extract.ids_of(state))
                state = _merge(state, _read(driver))
                new_load = sorted(set(extract.ids_of(state)) - before_load)
                mark("load_more_read", new_ids=new_load,
                     ids=len(extract.ids_of(state)))

                state, stop, steps = _scroll_loop(
                    driver, state, prefix="scroll", max_steps=config.max_scrolls,
                    config=config, should_cancel=should_cancel, mark=mark)
                scroll_steps += steps

                state = _merge(state, _read(driver))
                mark("final_read", ids=len(extract.ids_of(state)))
                if final_evidence is not None:
                    final_started = time.perf_counter()
                    try:
                        result["final_evidence"] = final_evidence(driver, state)
                    except Exception as exc:  # noqa: BLE001
                        result["final_evidence"] = {
                            "error": f"{type(exc).__name__}:{exc}"}
                    finally:
                        result["final_evidence_ms"] = round(
                            (time.perf_counter() - final_started) * 1000, 1)
    except Exception as exc:  # noqa: BLE001 - report the exact failure, keep partial data
        stop = f"error:{type(exc).__name__}"
        result["error"] = str(exc)[:400]
        mark("error", error=result["error"])
    finally:
        try:
            close_info = _action(driver.close())
            mark("close", **close_info)
        except Exception as exc:  # noqa: BLE001 - close failure is evidence, not silence
            mark("close_error", error=f"{type(exc).__name__}:{exc}")

    stop = stop or "error:unknown"
    records = sorted(state["records"].values(),
                     key=lambda item: (item.get("kind") or "", item.get("key") or ""))
    observed = sum(1 for item in records if item.get("kind") in ("comment", "lzl"))
    result.update({
        "stop": stop,
        "thread": state["thread"],
        "records": records,
        "ids": extract.ids_of(state),
        "declared": state["declared"],
        "observed": observed,
        "comment_count": sum(1 for item in records if item.get("kind") == "comment"),
        "lzl_count": sum(1 for item in records if item.get("kind") == "lzl"),
        "events": state["events"],
        "scroll": state["scroll"],
        "scroll_steps": scroll_steps,
        "unidentified": state["unidentified"],
        "fields": extract.field_summary(records),
        "phases": _phases(timeline, evidence_ms=result["evidence_ms"],
                          final_evidence_ms=result["final_evidence_ms"]),
    })
    counts: dict[str, int] = {}
    trusted: dict[str, int] = {}
    for event in state["events"]:
        event = event if isinstance(event, dict) else {}
        event_type = str(event.get("type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
        detail = event.get("detail")
        if isinstance(detail, dict) and detail.get("trusted") is True:
            trusted[event_type] = trusted.get(event_type, 0) + 1
    displacement = {
        "scroll_y_start": result["initial_scroll"].get("y", 0),
        "scroll_y_end": state["scroll"].get("y", 0),
        "scroll_height_start": result["initial_scroll"].get("height", 0),
        "scroll_height_end": state["scroll"].get("height", 0),
    }
    expected_clicks = int(expand_clicked) + int(load_clicked)
    checks = {
        "wheel_events": counts.get("wheel", 0) >= scroll_steps and scroll_steps > 0,
        "click_events": counts.get("click", 0) >= expected_clicks and expected_clicks > 0,
        "expand_event": counts.get("expand", 0) >= int(expand_clicked) and expand_clicked,
        "load_more_event": counts.get("load_more", 0) >= int(load_clicked) and load_clicked,
        "scroll_event": counts.get("scroll", 0) >= 1,
        "page_moved": displacement["scroll_y_end"] > displacement["scroll_y_start"],
        "height_grew": (displacement["scroll_height_end"]
                        >= displacement["scroll_height_start"]),
        "trusted_input": (
            trusted.get("click", 0) >= expected_clicks
            and trusted.get("wheel", 0) >= scroll_steps
            and trusted.get("expand", 0) >= int(expand_clicked)
            and trusted.get("load_more", 0) >= int(load_clicked)),
    }
    result["action_evidence"] = {
        "counts": counts,
        "trusted": trusted,
        "displacement": displacement,
        "expected": {"wheel": scroll_steps, "click": expected_clicks,
                     "expand": int(expand_clicked), "load_more": int(load_clicked)},
        "checks": checks,
        "ok": all(checks.values()),
    }
    result["stop_detail"] = _stop_detail(stop, result["declared"],
                                         result["comment_count"], config)
    result["complete"] = False
    result["partial"] = True
    result["total_ms"] = result["phases"].get("total_ms")
    return result
