"""可见窗口会话：真实浏览器 + 本机渲染证据 + 桌面级可见性证明。

复用既有 Chrome/nodriver 底座（`tools.selection.access.browser.available()`），单事件循环。

两种模式，网络策略不同、边界相同：
- **local**（默认）：开 `about:blank` → CDP `Network.setBlockedURLs(http/https/ws/wss)`
  + `--host-resolver-rules=MAP * ~NOTFOUND` → 导航到 `file://` fixture；导航后用
  `performance.getEntriesByType('resource')` 复核没有任何外部请求，有则判 `escaped`。
- **live**（`live=True`，只有 `login` / `live-search` 在守卫通过后才会用）：不封网、
  不放 DNS 黑洞，按真实站点导航；风险与预算由 `guard` 先行拦截。

证据边界（回应退回意见与「没看到窗口」投诉）：
- 截图与 `document.visibilityState` 只证明"非 headless 渲染"，**不证明桌面可见**；
- 桌面可见由 `desktop.prove()` 单独证明（前台窗口匹配 + 窗口矩形 + 整屏截图）；
- 不读 cookie、不代填凭据；登录只读页面可见信号。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import pathlib
import time

from tools.selection.access import browser as browser_mod

#: 页面内取"可见卡片"：只取最外层容器；正文**从原 DOM 的可见文本节点**收集
#: （不 clone、不用 textContent 回退），并跳过导航/作者/控制文字/嵌套卡片。
CARD_JS = r"""
(() => {
  const CARD_SEL = "article, div[class*='card']";
  const FULL = new Set(["全文", "展开全文", "查看全文", "阅读全文"]);
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "NAV", "ASIDE", "HEADER",
                             "FOOTER", "FORM", "BUTTON", "SELECT", "TEXTAREA", "SVG",
                             "IFRAME"]);
  const SKIP_SEL = "[class*='author'],[class*='nick'],[class*='avatar']," +
                   "[class*='toolbar'],[class*='action'],[class*='time']," +
                   "a[href*='/u/'],a[href*='/profile/']";
  const NOISE = /(转发\s*\d*|评论\s*\d*|赞\s*\d*|\d+\s*(分钟|小时|秒)前|昨天\s*\d{1,2}:\d{2}|今天\s*\d{1,2}:\d{2}|\d{1,2}-\d{1,2}\s*\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?)/g;
  const num = (t) => { if (!t) return null; const m = String(t).replace(/\s/g,'').match(/^(\d+(?:\.\d+)?)([万wW]?)$/); if (!m) return null; return Math.round(parseFloat(m[1]) * (m[2] ? 10000 : 1)); };
  const visible = (el) => {
    if (!el || !el.getClientRects || el.getClientRects().length === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== "hidden" && s.display !== "none";
  };
  const ownCard = (el, root) => el.closest(CARD_SEL) === root;   // 只认本卡自己的节点

  const collectText = (root) => {
    const parts = [];
    const walk = (node) => {
      if (node.nodeType === 3) {
        const parent = node.parentElement;
        if (!parent) return;
        if (parent.closest(SKIP_SEL)) return;
        if (!visible(parent)) return;                        // 卡内隐藏后代整体跳过
        const anchor = parent.closest("a");
        if (anchor && FULL.has((anchor.textContent || "").trim())) return;
        parts.push(node.nodeValue || "");
        return;
      }
      if (node.nodeType !== 1) return;
      const el = node;
      if (el !== root && el.matches(CARD_SEL)) return;        // 嵌套卡片正文不串
      if (SKIP_TAGS.has(el.tagName)) return;
      if (!visible(el)) return;
      for (const child of el.childNodes) walk(child);
    };
    for (const child of root.childNodes) walk(child);
    return parts.join(" ").replace(NOISE, " ").replace(/\s+/g, " ").trim();
  };

  const containers = Array.from(document.querySelectorAll(CARD_SEL))
    .filter((el) => visible(el) && !el.parentElement.closest(CARD_SEL));
  const out = [];
  containers.forEach((el, index) => {
    const link = Array.from(el.querySelectorAll("a[href*='/status/'], a[href*='/detail/']"))
      .find((a) => visible(a) && ownCard(a, el));
    if (!link) return;
    const m = (link.getAttribute("href") || "").match(/\/(?:status|detail)\/(\d{6,})/);
    if (!m) return;
    const titleEl = Array.from(el.querySelectorAll("h1,h2,h3,[class*='title']"))
      .find((n) => visible(n) && ownCard(n, el));
    const title = titleEl ? (titleEl.textContent || "").replace(/\s+/g, " ").trim() : null;
    let text = collectText(el);
    if (title && text.startsWith(title)) text = text.slice(title.length).trim();
    const bar = Array.from(el.querySelectorAll("[class*='toolbar'],[class*='action'],footer"))
      .find((n) => visible(n) && ownCard(n, el));
    const barText = bar ? (bar.textContent || "") : "";
    const timeEl = Array.from(el.querySelectorAll("[class*='time'],footer"))
      .find((n) => visible(n) && ownCard(n, el));
    const pick = (re) => { const x = barText.match(re); return x ? num(x[1]) : null; };
    out.push({
      container_id: el.id || ("card-" + index),
      id: m[1],
      url: link.href,
      text: text,
      title: title,
      time: timeEl ? (timeEl.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40) : null,
      counts: { comments: pick(/评论\s*([0-9.]+[万wW]?)/), likes: pick(/赞\s*([0-9.]+[万wW]?)/) },
      hidden: false,
    });
  });
  return JSON.stringify({ url: location.href, ready: document.readyState, cards: out });
})()
"""

#: 桌面版 `s.weibo.com` 的结果卡：容器 `div.card-wrap`（带 `mid`），正文 `p.txt`，
#: 作者 `a.name`，时间/来源 `div.from`，互动在 `div.card-act` 文本里。
#: 没有 mid 时回退解析卡内 `a[href*="//weibo.com/"]` 的 `/<uid>/<bid>`，并用 `id_source` 标明来源。
DESKTOP_CARD_JS = r"""
(() => {
  const CARD = 'div.card-wrap';
  const visible = (el) => {
    if (!el || !el.getClientRects || el.getClientRects().length === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const num = (t) => {
    if (!t) return null;
    const m = String(t).replace(/\s/g, '').match(/^(\d+(?:\.\d+)?)([万亿wW]?)$/);
    if (!m) return null;
    const mult = m[2] === '万' || m[2] === 'w' || m[2] === 'W' ? 10000 : 1;
    return Math.round(parseFloat(m[1]) * mult);
  };
  const out = [];
  document.querySelectorAll(CARD).forEach((el, index) => {
    if (!visible(el)) return;
    const mid = (el.getAttribute('mid') || '').trim();
    let id = null;
    let idSource = null;
    let href = null;
    let bid = null;
    if (/^\d{5,}$/.test(mid)) {
      id = mid;
      idSource = 'mid';
    }
    const links = Array.from(el.querySelectorAll('a[href]'))
      .filter((a) => visible(a) && /\/(\d+)\/([0-9A-Za-z]+)/.test(a.getAttribute('href') || ''));
    const link = links.find((a) => (a.getAttribute('href') || '').includes('weibo.com'))
      || links[0] || null;
    if (link) {
      href = link.getAttribute('href') || null;
      const m = href.match(/\/(\d+)\/([0-9A-Za-z]+)/);
      if (m) {
        bid = m[2];
        if (!id) { id = m[2]; idSource = 'bid'; }
      }
    }
    const texts = Array.from(el.querySelectorAll('p.txt'))
      .filter((p) => visible(p) && p.closest(CARD) === el)
      .map((p) => norm(p.textContent)).filter(Boolean);
    const text = Array.from(new Set(texts)).join(' ');
    const authorEl = Array.from(el.querySelectorAll('a.name')).find((a) => visible(a));
    const fromEl = Array.from(el.querySelectorAll('div.from')).find((n) => visible(n));
    const actEl = Array.from(el.querySelectorAll('div.card-act')).find((n) => visible(n));
    const ul = actEl ? Array.from(actEl.querySelectorAll('ul')).find((n) => visible(n)) : null;
    const lis = ul ? Array.from(ul.children).filter((n) => n.tagName === 'LI' && visible(n))
      : [];
    const ORDER = ['reposts', 'comments', 'likes'];
    const counts = { reposts: null, comments: null, likes: null };
    const countMeta = {
      reposts: { source: 'absent', raw: null, unit: null, text_len: 0 },
      comments: { source: 'absent', raw: null, unit: null, text_len: 0 },
      likes: { source: 'absent', raw: null, unit: null, text_len: 0 },
    };
    // 位置即类型：li[0]=转发 li[1]=评论 li[2]=赞（计数>0 时标签会消失，不能按标签识别）
    ORDER.forEach((slot, i) => {
      const li = lis[i];
      if (!li) return;                       // li 缺失 → null + absent
      // 先按空白切成 token 再找数字：`12 13` 不能被并成 `1213`
      const text = ((li.innerText || li.textContent || '')).replace(/\s+/g, ' ').trim();
      const nums = text.match(/\d+(?:\.\d+)?[万亿wW]?/g) || [];
      const meta = { source: 'position', raw: null, unit: null, text_len: text.length };
      if (nums.length === 0) {
        counts[slot] = 0;                    // 只有标签、没有数字 → 真实 0
      } else if (nums.length > 1) {
        meta.source = 'ambiguous';           // 多个数字 → 不猜，保留长度
      } else {
        const m = nums[0].match(/(\d+(?:\.\d+)?)([万亿wW]?)/);
        const mult = (m[2] === '万' || m[2] === 'w' || m[2] === 'W') ? 10000 : 1;
        counts[slot] = Math.round(parseFloat(m[1]) * mult);
        meta.raw = m[1] + (m[2] || '');
        meta.unit = m[2] || null;
      }
      countMeta[slot] = meta;
    });
    out.push({
      container_id: el.getAttribute('mid') || ('card-' + index),
      mid: mid || null,
      id: id,
      id_source: idSource,
      bid: bid,
      href: href,
      url: href ? href.replace(/^http:/, 'https:').replace(/^\/\//, 'https://') : null,
      author: authorEl ? norm(authorEl.textContent) : null,
      text: text,
      time: fromEl ? norm(fromEl.textContent).slice(0, 60) : null,
      counts: counts,
      count_meta: countMeta,
      hidden: false,
    });
  });
  return JSON.stringify({ url: location.href, ready: document.readyState, cards: out });
})()
"""

#: 点开评论区入口：**只点精确文本为「评论」的入口**或 `a[href*="comment"]`；
#: 绝不点 `div.card-act > ul`（它的文本是「转发 评论 赞」）。
CLICK_COMMENT_JS = r"""
(() => {
  const visible = (el) => {
    if (!el || !el.getClientRects || el.getClientRects().length === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  const norm = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const inActBar = (el) => !!el.closest('div.card-act');
  const nodes = Array.from(document.querySelectorAll('a,button,div,span,li'))
    .filter((el) => visible(el) && !inActBar(el));
  const exact = nodes.filter((el) => norm(el.innerText) === '评论');
  const byHref = nodes.filter((el) => /comment/i.test(el.getAttribute('href') || ''));
  const withCount = nodes.filter((el) => /^评论\s*\d+$/.test(norm(el.innerText)));
  const hit = exact[0] || byHref[0] || withCount[0] || null;
  if (!hit) return JSON.stringify({ clicked: false, reason: 'no_comment_entry' });
  const label = norm(hit.innerText).slice(0, 12);
  const tag = hit.tagName.toLowerCase();
  const href = (hit.getAttribute('href') || '').slice(0, 80);
  hit.click();
  return JSON.stringify({ clicked: true, label: label, tag: tag,
                          href_shape: /comment/i.test(href) ? 'comment' : 'other' });
})()
"""

#: 在页面内挂钩 fetch/XHR：只记 host/path/参数名/状态/大小/顶层键，**不记请求头与响应正文**。
NET_HOOK_JS = r"""
(() => {
  if (window.__dshNetInstalled) return JSON.stringify({ installed: true, reused: true });
  window.__dshNet = [];
  const push = (e) => { if (window.__dshNet.length < 60) window.__dshNet.push(e); };
  const shape = (u) => {
    try {
      const x = new URL(u, location.href);
      return { host: x.hostname, path: x.pathname,
               params: Array.from(x.searchParams.keys()).slice(0, 20) };
    } catch (e) { return { host: '', path: '', params: [] }; }
  };
  const keysOf = (t) => {
    try {
      const o = JSON.parse(t);
      return (o && typeof o === 'object' && !Array.isArray(o)) ? Object.keys(o).slice(0, 12) : [];
    } catch (e) { return []; }
  };
  const origFetch = window.fetch;
  window.fetch = function (...args) {
    const url = (args[0] && args[0].url) || args[0] || '';
    const method = (args[1] && args[1].method) || 'GET';
    const p = origFetch.apply(this, args);
    p.then((r) => {
      const base = shape(String(url));
      r.clone().text().then((t) => push({ ...base, method: method, status: r.status,
                                          size: t.length, keys: keysOf(t) })).catch(() => {});
    }).catch(() => {});
    return p;
  };
  const OrigXHR = window.XMLHttpRequest;
  function Hooked() {
    const x = new OrigXHR();
    let info = { method: 'GET', url: '' };
    const open = x.open;
    x.open = function (m, u, ...rest) { info = { method: m, url: u }; return open.call(x, m, u, ...rest); };
    const send = x.send;
    x.send = function (...a) {
      x.addEventListener('loadend', () => {
        const base = shape(String(info.url));
        const t = (x.responseType === '' || x.responseType === 'text') ? (x.responseText || '') : '';
        push({ ...base, method: info.method, status: x.status, size: t.length, keys: keysOf(t) });
      });
      return send.apply(x, a);
    };
    return x;
  }
  Hooked.prototype = OrigXHR.prototype;
  window.XMLHttpRequest = Hooked;
  window.__dshNetInstalled = true;
  return JSON.stringify({ installed: true, reused: false });
})()
"""

RESOURCE_AUDIT_JS = r"""
(() => {
  const entries = performance.getEntriesByType("resource").map((e) => ({
    name: e.name, transfer: e.transferSize || 0, status: e.responseStatus || 0,
  }));
  const external = entries.filter((e) => /^(https?|wss?):/i.test(e.name));
  const completed = external.filter((e) => e.transfer > 0 || e.status > 0);
  return JSON.stringify({
    total: entries.length,
    external_attempts: external.length,
    external_completed: completed.length,
    sample: external.slice(0, 5).map((e) => ({ name: e.name, transfer: e.transfer,
                                               status: e.status })),
    href: location.href,
    ready: document.readyState,
  });
})()
"""

NAV_STATE_JS = r"""
(() => JSON.stringify({
  href: location.href,
  ready: document.readyState,
  visibility: document.visibilityState,
  outerWidth: window.outerWidth, outerHeight: window.outerHeight,
  screenX: window.screenX, screenY: window.screenY,
}))()
"""

PAGE_STATE_JS = r"""
(() => {
  const nav = (performance.getEntriesByType("navigation")[0]) || {};
  return JSON.stringify({
    url: location.href,
    title: document.title,
    ready: document.readyState,
    http_status: (typeof nav.responseStatus === "number" && nav.responseStatus > 0)
                 ? nav.responseStatus : null,
    text: ((document.body && document.body.innerText) || "").slice(0, 4000),
    text_len: ((document.body && document.body.innerText) || "").length,
    visibility: document.visibilityState,
    outerWidth: window.outerWidth, outerHeight: window.outerHeight,
    screenX: window.screenX, screenY: window.screenY,
  });
})()
"""

LOCAL_SCHEMES = ("about:", "file:")


def title_consistency(window_title, page_title) -> bool | None:
    """OS 窗口标题是否**确实显示**该页面：页面标题须是窗口标题的子串。

    Chrome 的窗口标题形如 `登录 - 微博 - Google Chrome`，页面标题是 `登录 - 微博`；
    空白新标签页时窗口标题是 `新标签页 - Google Chrome`，此时返回 False。
    任一为空 → None（未知，不能当作成立）。
    """
    from . import desktop as desktop_mod

    return desktop_mod.title_contains(window_title, page_title)
HTTP_SCHEMES = ("http:", "https:")


class SessionUnavailable(RuntimeError):
    pass


class VisibleSession:
    """一次可见窗口会话；`live=False` 时封闭所有 http(s)/ws(s) 请求。"""

    def __init__(self, profile, *, chrome: str | None = None, timeout: float = 60.0,
                 live: bool = False, user_agent: str | None = None) -> None:
        self.profile = pathlib.Path(profile).expanduser().resolve()
        self.chrome = chrome
        self.timeout = timeout
        self.live = bool(live)
        self.user_agent = user_agent
        self._loop: asyncio.AbstractEventLoop | None = None
        self._browser = None
        #: 最近一次 open_local/open_live 的标签页激活结果（供 desktop_proof 回读）
        self.last_activation: dict | None = None
        #: 只用于**定位窗口**，不是桌面可见性证据（证据见 desktop.prove）。
        self._pid: int | None = None

    def _get_loop(self):
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop

    def _run(self, coro):
        return self._get_loop().run_until_complete(asyncio.wait_for(coro, timeout=self.timeout))

    # -- lifecycle ---------------------------------------------------------
    def browser_args(self) -> list[str]:
        """启动参数：local 封 DNS，live 才允许真实 DNS；UA 是启动开关不是重试手段。"""
        args = ["--disable-background-networking", "--no-first-run",
                "--no-default-browser-check"]
        if self.live:
            # live 模式：真实站点导航，UA 是启动开关（与 access/weibo.SITE 同一假设）
            if self.user_agent:
                args.append(f"--user-agent={self.user_agent}")
        else:
            # 本地模式：DNS 黑洞 + CDP URL 黑名单，双保险
            args.append("--host-resolver-rules=MAP * ~NOTFOUND")
        return args

    def start(self) -> dict:
        info = browser_mod.available()
        if not info["usable"]:
            raise SessionUnavailable(
                f"browser_unavailable:nodriver={info['nodriver']}:chrome={bool(info['chrome'])}")
        import nodriver as uc

        chrome = self.chrome or info["chrome"]
        self.profile.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        self._browser = self._run(uc.start(
            headless=False, user_data_dir=str(self.profile),
            browser_executable_path=chrome, browser_args=self.browser_args()))
        # nodriver 0.50.6 把启动进程 pid 存在 `_process_pid`；两版都兼容。
        self._pid = getattr(self._browser, "_process_pid", None) or \
            getattr(self._browser, "process_pid", None)
        return {"started_in_s": round(time.monotonic() - started, 2),
                "profile": str(self.profile), "chrome": chrome, "headless": False,
                "mode": "live" if self.live else "local",
                "network": "open" if self.live else "blocked",
                "browser_pid": self._pid, "dns_blocked": not self.live,
                "note": "browser_pid 只用于定位窗口；桌面可见性由 desktop.prove 判定"}

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.stop()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
        self._pid = None
        if self._loop is not None and not self._loop.is_closed():
            try:
                self._loop.close()
            except Exception:  # noqa: BLE001
                pass
            self._loop = None

    # -- navigation --------------------------------------------------------
    def _block_network(self, tab) -> dict:
        from nodriver import cdp

        # nodriver 0.50.6 的生成代码把名字拼成 `set_blocked_ur_ls`，两版都兼容。
        setter = getattr(cdp.network, "set_blocked_urls", None) or \
            getattr(cdp.network, "set_blocked_ur_ls", None)
        if setter is None:
            raise SessionUnavailable("network_block_unavailable")

        async def _apply():
            await tab.send(cdp.network.enable())
            await tab.send(setter(urls=["http://*", "https://*", "ws://*", "wss://*"]))
        self._run(_apply())
        return {"blocked_patterns": ["http://*", "https://*", "ws://*", "wss://*"]}

    def open_local(self, url: str) -> tuple[object, dict]:
        """本地模式：about:blank → 封网 → 导航 → **激活该标签页**；返回 (tab, 封网证据)。"""
        if self._browser is None:
            raise SessionUnavailable("session_not_started")
        if not url.startswith(LOCAL_SCHEMES):
            raise SessionUnavailable("non_local_url")
        tab = self._run(self._browser.get("about:blank"))
        blocked = self._block_network(tab)
        self._run(tab.get(url))
        self.last_activation = self.activate(tab)
        return tab, blocked

    def open_live(self, url: str) -> object:
        """live 模式：单次真实导航（不重试、不回退、不换 UA）→ **激活该标签页**。"""
        if self._browser is None:
            raise SessionUnavailable("session_not_started")
        if not str(url).lower().startswith(HTTP_SCHEMES):
            raise SessionUnavailable("non_http_url")
        if not self.live:
            raise SessionUnavailable("live_mode_required")
        tab = self._run(self._browser.get(url))
        self.last_activation = self.activate(tab)
        return tab

    def open_live_hooked(self, url: str) -> object:
        """**导航前**注入 `NET_HOOK_JS`（CDP addScriptToEvaluateOnNewDocument），
        以便捕获导航期与首屏加载期的 XHR/fetch；注入失败则退回导航后挂钩。"""
        if self._browser is None:
            raise SessionUnavailable("session_not_started")
        if not str(url).lower().startswith(HTTP_SCHEMES):
            raise SessionUnavailable("non_http_url")
        if not self.live:
            raise SessionUnavailable("live_mode_required")

        async def go():
            tab = await self._browser.get("about:blank")
            injected = False
            error = None
            try:
                from nodriver import cdp

                await tab.send(cdp.page.enable())          # 必须先开 Page 域
                await tab.send(cdp.page.add_script_to_evaluate_on_new_document(
                    source=NET_HOOK_JS))
                injected = True
            except Exception as exc:                 # noqa: BLE001 - 记录原因，不静默
                error = f"cdp:{type(exc).__name__}:{exc}"[:200]
            await tab.get(url)
            if not injected:
                try:
                    await tab.evaluate(NET_HOOK_JS)
                    error = (error or "") + "|fallback_eval_ok"
                except Exception as exc:             # noqa: BLE001
                    error = f"{error or ''}|fallback:{type(exc).__name__}:{exc}"[:300]
            self.last_hook_error = error
            return tab

        tab = self._run(go())
        self.last_activation = self.activate(tab)
        return tab

    def activate(self, tab) -> dict:
        """把目标标签页置前；先 `Tab.activate()`，失败再退 CDP。失败只记录，不抛。"""
        out: dict = {"activated": False, "method": None, "error": None}

        async def _call(fn):
            result = fn()
            if inspect.isawaitable(result):
                return await result
            return result

        activate = getattr(tab, "activate", None)
        if callable(activate):
            try:
                self._run(_call(activate))
                out.update(activated=True, method="tab.activate")
            except Exception as exc:  # noqa: BLE001 - 记录后继续尝试 CDP
                out["error"] = f"tab.activate:{type(exc).__name__}"
        if not out["activated"]:
            try:
                from nodriver import cdp

                async def _cdp():
                    target_id = getattr(getattr(tab, "target", None), "target_id", None)
                    if target_id:
                        await tab.send(cdp.target.activate_target(target_id=target_id))
                    await tab.send(cdp.page.bring_to_front())

                self._run(_cdp())
                out.update(activated=True,
                           method="cdp.target.activateTarget+page.bringToFront")
            except Exception as exc:  # noqa: BLE001
                suffix = f"cdp:{type(exc).__name__}"
                out["error"] = f"{out['error']};{suffix}" if out["error"] else suffix
        return out

    def read_page(self, tab) -> dict:
        """页面状态：url/title/readyState/导航 HTTP 状态/可见正文（截断 4000 字）。"""
        return json.loads(self._run(tab.evaluate(PAGE_STATE_JS)))

    def html(self, tab) -> str:
        """渲染后的整页 HTML（结构侦察用；不落正文，只给 summarize 数结构）。"""
        return self._run(tab.get_content())

    def read_signals(self, tab, script: str) -> dict:
        """跑调用方的信号脚本（如 weibo.SIGNED_IN_JS），返回解析后的字典型信号。"""
        raw = self._run(tab.evaluate(script))
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def wait_ready(self, tab, *, attempts: int = 20, interval: float = 0.5,
                   keepalive=None) -> dict:
        """live 页面等到 readyState=complete；超时如实标记，不抛。

        `keepalive` 每轮 tick 一次：只在前台丢失时把窗口夺回（不每轮抢焦点）。
        """
        state: dict = {}
        for _ in range(max(1, int(attempts))):
            state = self.read_page(tab)
            if keepalive is not None:
                keepalive.tick()
            if state.get("ready") == "complete":
                return {**state, "timed_out": False}
            time.sleep(interval)
        return {**state, "timed_out": True}

    def set_title(self, tab, title: str) -> str:
        """给本地 fixture 打一次性标题 nonce，便于桌面证据按标题反查窗口。"""
        self._run(tab.evaluate(f"(document.title = {json.dumps(title)}, document.title)"))
        return title

    def desktop_proof(self, *, tab=None, screenshot=None, title_hint: str | None = None,
                      wait_s: float = 2.0) -> dict:
        """桌面级可见性证据；`screenshot=None` 时不抓图（真实登录页禁止截图）。

        传 `tab` 时会读页面 title，并与 OS 窗口标题比对：
        `window_title_matches_page` 是"窗口显示的就是目标页"的**可判读前提**。
        """
        from . import desktop as desktop_mod

        target = pathlib.Path(screenshot) if screenshot is not None else None
        page_title = None
        if tab is not None:
            try:
                page_title = (self.read_page(tab) or {}).get("title")
            except Exception:  # noqa: BLE001 - 读不到就按未知处理
                page_title = None
        proof = desktop_mod.prove(pid=self._pid, title_hint=title_hint,
                                  screenshot=target, wait_s=wait_s)
        proof["page_title"] = page_title
        proof["window_title_matches_page"] = title_consistency(
            proof.get("window_title"), page_title)
        proof["activation"] = getattr(self, "last_activation", None)
        return proof

    def navigate_stable(self, tab, *, attempts: int = 6, interval: float = 0.3) -> dict:
        """轮询 href/readyState，记录重定向与超时；跳出本地 scheme 即 escaped。"""
        requested = self._run(tab.evaluate("location.href"))
        redirects: list[str] = []
        timed_out = False
        state: dict = {}
        for _ in range(attempts):
            state = json.loads(self._run(tab.evaluate(NAV_STATE_JS)))
            href = state.get("href") or ""
            if href and href != requested and href not in redirects:
                redirects.append(href)
            if state.get("ready") == "complete":
                break
            time.sleep(interval)
        else:
            timed_out = True
        href = state.get("href") or ""
        return {"requested_url": requested, "final_url": href, "redirects": redirects,
                "ready_state": state.get("ready"), "timed_out": timed_out,
                "escaped": bool(href) and not href.startswith(LOCAL_SCHEMES)}

    def audit_network(self, tab) -> dict:
        return json.loads(self._run(tab.evaluate(RESOURCE_AUDIT_JS)))

    # -- page --------------------------------------------------------------
    def dump_cards(self, tab) -> dict:
        """页面内 JS 取可见卡片（同一容器内的 id/正文/时间/计数）。"""
        return json.loads(self._run(tab.evaluate(CARD_JS)))

    def dump_desktop_cards(self, tab) -> dict:
        """桌面版 `s.weibo.com` 的卡片：容器 `div.card-wrap`，ID 优先 `mid`。"""
        return json.loads(self._run(tab.evaluate(DESKTOP_CARD_JS)))

    def click_comment_entry(self, tab) -> dict:
        """点一次「评论」入口（调用方负责把它记成一次显式调用）。"""
        return json.loads(self._run(tab.evaluate(CLICK_COMMENT_JS)))

    def install_net_hook(self, tab) -> dict:
        """在页面内挂 fetch/XHR 钩子（只记结构，不记请求头与正文）。"""
        return json.loads(self._run(tab.evaluate(NET_HOOK_JS)))

    def read_net_hook(self, tab) -> list:
        """读回钩子捕获的请求（原始条目；过滤/整形交给 probe.summarize_network）。"""
        return json.loads(self._run(tab.evaluate(
            "JSON.stringify(window.__dshNet || [])")))

    def hook_installed(self, tab) -> bool:
        """钩子是否真的装上了（导航前注入是否生效）。"""
        try:
            return json.loads(self._run(tab.evaluate(
                "JSON.stringify({v: !!window.__dshNetInstalled})"))).get("v") is True
        except Exception:                     # noqa: BLE001
            return False

    def wait_render_stable(self, tab, *, min_len: int = 500, attempts: int = 20,
                           interval: float = 0.5, keepalive=None) -> dict:
        """等详情页渲染稳定：连续两次 `text_len` 相同且 ≥ `min_len`，最多 ~10s。"""
        import time as _time

        started = _time.monotonic()
        last = None
        stable = 0
        text_len = 0
        for _ in range(max(1, attempts)):
            page = self.read_page(tab) or {}
            text_len = int(page.get("text_len") or 0)
            if keepalive is not None:
                keepalive.tick()
            if text_len == last:
                stable += 1
            else:
                stable = 0
            last = text_len
            if text_len >= min_len and stable >= 1:
                break
            _time.sleep(max(0.0, float(interval)))
        return {"text_len": text_len, "stable": stable >= 1 and text_len >= min_len,
                "waited_ms": int((_time.monotonic() - started) * 1000)}

    def fetch_json(self, tab, url: str, *, await_promise: bool = True) -> dict:
        """在**页面内**用 fetch 调同源端点，返回 {status, json|None, text_len}。

        只回传解析后的 JSON 与长度；响应正文不落盘（由调用方决定保留哪些字段）。
        """
        async def go():
            js = ("(async () => {"
                  f" const r = await fetch({url!r}, {{credentials: 'include'}});"
                  " const t = await r.text();"
                  " let j = null; try { j = JSON.parse(t); } catch (e) { j = null; }"
                  " return JSON.stringify({status: r.status, json: j, text_len: t.length});"
                  "})()")
            return await tab.evaluate(js, await_promise=await_promise)

        raw = self._run(go())
        if isinstance(raw, str):
            return json.loads(raw)
        return raw or {}

    def scroll_page(self, tab, *, segments: int = 3, pause: float = 0.8) -> list:
        """分段滚动到页面底部（触发懒加载），每段之间等待。"""
        heights = []
        for i in range(1, max(1, segments) + 1):
            script = ("(() => { const h = document.body.scrollHeight;"
                      f" window.scrollTo(0, Math.round(h * {i} / {max(1, segments)}));"
                      " return JSON.stringify({h: h, y: Math.round(window.scrollY)}); })()")
            heights.append(json.loads(self._run(tab.evaluate(script))))
            time.sleep(max(0.0, float(pause)))
        return heights

    def evidence(self, tab, *, screenshot: pathlib.Path | None = None) -> dict:
        """渲染证据：窗口几何 + visibility + 资源审计 +（可选）截图。"""
        geo = json.loads(self._run(tab.evaluate(NAV_STATE_JS)))
        audit = self.audit_network(tab)
        out = {"geometry": geo, "network_audit": audit, "pid_evidence": False,
               "desktop_visibility_proven": False,
               "note": "几何+截图只证明非 headless 渲染；桌面是否被人眼看到未证实"}
        if screenshot is not None:
            path = pathlib.Path(screenshot)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._run(tab.save_screenshot(str(path)))
                out["screenshot"] = {"path": str(path),
                                     "bytes": path.stat().st_size if path.exists() else 0}
            except Exception as exc:  # noqa: BLE001 - 截图失败要如实报，不冒充成功
                out["screenshot"] = {"path": str(path), "error": type(exc).__name__}
        return out
