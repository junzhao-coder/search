"""Browser-RPA：可见卡片提取 + 本地可见窗口 + 桌面级可见性证据 + 平台守卫。

- `extract` 吃页面内 JS 取出的**可见卡片 JSON**，不解析原始 HTML；
- `window` 只做本地 fixture 渲染验证（about:blank / fixtures 下的 file://），并封网；
  `--desktop-proof` 用标准库 ctypes 证明窗口真的被置前（前台句柄匹配 + 窗口矩形 + 整屏截图）；
- `login` / `live-search` 是**真实**路径：先过固定权威账本 `precheck → 预扣`，再启动浏览器；
  本轮未执行真实导航（旧批次已耗尽），代码路径已实现、待新授权批次实测。
"""

from __future__ import annotations

from .cli import build_parser, main
from .extract import ASSUMED_SELECTORS, extract_cards, extract_detail
from .guard import GuardBlocked, charge_nav, charge_search, enforce_risk, open_guard, \
    precheck, record_result, reserve_records, risk_reason
from .session import SessionUnavailable, VisibleSession

__all__ = [
    "ASSUMED_SELECTORS", "GuardBlocked", "SessionUnavailable", "VisibleSession",
    "build_parser", "charge_nav", "charge_search", "enforce_risk", "extract_cards",
    "extract_detail", "main", "open_guard", "precheck", "record_result",
    "reserve_records", "risk_reason",
]
