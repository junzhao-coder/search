"""桌面搜索入口的结构侦察：只统计选择器命中与 id 一致性，**不保留正文**。

为什么用 Python 解析 HTML 而不是页面 JS：`s.weibo.com` 的搜索结果由服务端直出
（`div.card-wrap` 等），拿 `tab.get_content()` 的 HTML 就能数结构；这样 probe 可以在
纯离线 fixture 上被完整单测，不必依赖真实浏览器。

输出字段（验收要求）：`final_url / http_status / title / text_len / ready`、
候选选择器命中数（`div.card-wrap`、`div.card`、`p.txt`、`a.name`、`div.from`、
`div.card-act`、`a[href*="/status/"]`、`a[href*="s.weibo.com"]`、`img.avator`、`.card-comment`）、
前 5 条 `/status/` 链接的 `href` id 与 `data-id` 是否一致、是否含登录墙/验证码标记。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from tools.selection.access import weibo as weibo_mod

#: 候选选择器 -> 计数键（顺序即报告顺序）。
SELECTORS = (
    ("div.card-wrap", "card_wrap"),
    ("div.card", "card"),
    ("p.txt", "p_txt"),
    ("a.name", "a_name"),
    ("div.from", "div_from"),
    ("div.card-act", "card_act"),
    ('a[href*="/status/"]', "status_links"),
    ('a[href*="s.weibo.com"]', "s_weibo_links"),
    ("img.avator", "img_avator"),
    (".card-comment", "card_comment"),
)

STATUS_ID = re.compile(r"/status/(\d{6,})")


class _Probe(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.counts = {key: 0 for _sel, key in SELECTORS}
        self.status_hrefs: list[str] = []
        self.status_data_ids: list[str | None] = []
        self.title = ""
        self._in_title = False
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attr = {k.lower(): (v or "") for k, v in attrs}
        classes = set(attr.get("class", "").split())
        if tag == "title":
            self._in_title = True
        if tag == "div" and "card-wrap" in classes:
            self.counts["card_wrap"] += 1
        if tag == "div" and "card" in classes:
            self.counts["card"] += 1
        if tag == "p" and "txt" in classes:
            self.counts["p_txt"] += 1
        if tag == "a" and "name" in classes:
            self.counts["a_name"] += 1
        if tag == "div" and "from" in classes:
            self.counts["div_from"] += 1
        if tag == "div" and "card-act" in classes:
            self.counts["card_act"] += 1
        if "card-comment" in classes:
            self.counts["card_comment"] += 1
        if tag == "img" and "avator" in classes:
            self.counts["img_avator"] += 1
        href = attr.get("href", "")
        if tag == "a" and "/status/" in href:
            self.counts["status_links"] += 1
            if len(self.status_hrefs) < 5:
                self.status_hrefs.append(href)
                self.status_data_ids.append(attr.get("data-id") or None)
        if tag == "a" and "s.weibo.com" in href:
            self.counts["s_weibo_links"] += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        self._text.append(data)

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._text).split())


def summarize(html: str, *, url: str = "", requested_url: str | None = None,
              http_status=None, ready=None, title: str | None = None,
              text_len: int | None = None) -> dict:
    """HTML -> 结构计数（不含正文）。"""
    parser = _Probe()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 - 解析失败也要给出可判读结果
        pass
    text = parser.text
    markers = [m for m in weibo_mod.RISK_MARKERS if m and m in text]
    wall = [m for m in weibo_mod.LOGIN_WALL_MARKERS if m and m in text]
    ids = []
    for href, data_id in zip(parser.status_hrefs, parser.status_data_ids):
        match = STATUS_ID.search(href)
        href_id = match.group(1) if match else None
        ids.append({"href_id": href_id, "data_id": data_id,
                    "consistent": (None if not data_id or not href_id
                                   else data_id == href_id)})
    return {
        "structure": "probe:html",
        "diagnostics": {"cards_total": parser.counts["card"] or parser.counts["card_wrap"],
                        "status_links": parser.counts["status_links"],
                        "text_len": text_len if text_len is not None else len(text)},
        "url": url,
        "requested_url": requested_url if requested_url is not None else url,
        "final_url": url,
        "http_status": http_status,
        "title": title if title is not None else parser.title.strip(),
        "text_len": text_len if text_len is not None else len(text),
        "ready": ready,
        "counts": parser.counts,
        "status_ids": ids,
        "wall": {"markers": markers, "login_wall": wall,
                 "captcha_or_risk": bool(markers)},
        "cards_total": parser.counts["card"] or parser.counts["card_wrap"],
        "surface": surface_of(url),
    }


DETAIL_URL = re.compile(r"(weibo\.com/\d+/[0-9A-Za-z]{4,})|(m\.weibo\.cn/status/\d+)")


def surface_of(url: str) -> str:
    """`detail`（单条微博页）还是 `search`（结果列表页）。"""
    return "detail" if DETAIL_URL.search(str(url or "")) else "search"


def verdict(summary: dict) -> tuple[int, str | None]:
    """(exit_code, stop)：风险优先 → 有卡片 → 零命中。"""
    from tools.selection.access import codes

    wall = (summary.get("wall") or {})
    if wall.get("markers"):
        return codes.EXIT_RISK, f"risk:text:{wall['markers'][0]}"
    if wall.get("login_wall"):
        return codes.EXIT_RISK, f"risk:text:{wall['login_wall'][0]}"
    if summary.get("surface") == "detail":
        # 详情页没有 card-wrap 是正常的：按"正文/评论是否取到"判定
        text_len = int(summary.get("text_len") or 0)
        comments = int(((summary.get("comments") or {}).get("items")) or 0)
        if text_len >= 100 or comments > 0:
            return codes.EXIT_OK, None
        return codes.EXIT_EMPTY, "detail_empty"
    if int(summary.get("cards_total") or 0) > 0:
        return codes.EXIT_OK, None
    return codes.EXIT_UNSUPPORTED, "no_cards"


# --- card-act 结构画像 ------------------------------------------------------

TAG_BUCKETS = ("a", "span", "em", "i", "svg")
LABELS = ("转发", "评论", "赞")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "param", "source", "track", "wbr"}
DIGITS_ONLY = re.compile(r"^\d+(?:\.\d+)?[万千]?$")
UNIT = re.compile(r"[万千]")
HREF_SHAPES = (("attitude", "like"), ("like", "like"), ("comment", "comment"),
               ("repost", "repost"), ("forward", "repost"), ("赞", "like"),
               ("评论", "comment"), ("转发", "repost"))


def _href_shape(href: str) -> str:
    low = (href or "").lower()
    for needle, shape in HREF_SHAPES:
        if needle in low:
            return shape
    return "other"


def _text_form(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return "empty"
    if DIGITS_ONLY.match(body):
        return "unit" if UNIT.search(body) else "digits"
    if UNIT.search(body):
        return "unit"
    if re.search(r"[\u4e00-\u9fff]", body):
        return "chinese"
    return "other"


class _CardAct(HTMLParser):
    """只收集结构：标签、class、有无 title/href、文本长度与形态；**不保留正文**。"""

    def __init__(self, limit: int = 5) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.cards: list[dict] = []
        self._depth = 0
        self._card_depth: int | None = None
        self._act_depth: int | None = None
        self._child: dict | None = None
        self._child_depth: int | None = None
        self._ul_depth: int | None = None
        self._item: dict | None = None

    # -- helpers
    def _close_item(self) -> None:
        if self._item is not None:
            text = "".join(self._item.pop("_text"))
            self._item["text_len"] = len(text.strip())
            self._item["text_form"] = _text_form(text)
            self._item["has_digit"] = bool(re.search(r"\d", text))
            if self._child is not None:      # 挂在当前打开的 ul 上（此时它还没进 children）
                self._child["items"].append(self._item)
                bucket = self._item["tag"] if self._item["tag"] in TAG_BUCKETS else "other"
                self._child["tags"][bucket] = self._child["tags"].get(bucket, 0) + 1
        self._item = None

    def _close_child(self) -> None:
        self._close_item()
        if self._child is not None:
            text = "".join(self._child.pop("_text"))
            self._child["text_len"] = len(text.strip())
            self._child["text_form"] = _text_form(text)
            self._child["has_digit"] = bool(re.search(r"\d", text))
            labels = [lb for lb in LABELS if lb in text]
            self._child["labels"] = labels
            self._child["label_count"] = len(labels)
            self._child["label_without_digit"] = bool(labels) and not bool(
                re.search(r"\d", text))
            card = self.cards[-1]
            card["children"].append(self._child)
            bucket = self._child["tag"] if self._child["tag"] in TAG_BUCKETS else "other"
            card["tags"][bucket] = card["tags"].get(bucket, 0) + 1
        self._child = None
        self._child_depth = None
        self._ul_depth = None

    # -- HTMLParser hooks
    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:                     # 空元素不占层级，否则 depth 会永久漂移
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        classes = attr.get("class", "").split()
        self._depth += 1
        depth = self._depth
        if self._card_depth is None:
            if tag == "div" and "card-wrap" in classes and len(self.cards) < self.limit:
                self.cards.append({"exists": False, "tags": {}, "children": [],
                                   "act_text_len": 0})
                self._card_depth = depth
            return
        if self._act_depth is None:
            if tag == "div" and "card-act" in classes:
                self.cards[-1]["exists"] = True
                self._act_depth = depth
            return
        if depth == self._act_depth + 1:
            self._close_child()
            self._child = {"tag": tag, "classes": classes,
                           "has_title": bool(attr.get("title")),
                           "has_href": bool(attr.get("href")),
                           "href_shape": _href_shape(attr.get("href", ""))
                           if attr.get("href") else "none",
                           "items": [], "tags": {}, "_text": []}
            self._child_depth = depth
            self._ul_depth = depth if tag == "ul" else None
            return
        if self._ul_depth is not None and depth == self._ul_depth + 1:
            self._close_item()
            self._item = {"tag": tag, "classes": classes,
                          "has_href": bool(attr.get("href")), "_text": []}

    def handle_startendtag(self, tag, attrs):
        """`<img/>` 这类自闭合标签：不进层级。"""
        return

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self._ul_depth is not None and self._depth == self._ul_depth + 1:
            self._close_item()
        if self._act_depth is not None and self._depth == self._act_depth + 1:
            self._close_child()
        if self._act_depth is not None and self._depth == self._act_depth:
            self._act_depth = None
        elif self._card_depth is not None and self._depth == self._card_depth:
            self._card_depth = None
        self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._item is not None:
            self._item["_text"].append(data)
        elif self._child is not None:
            self._child["_text"].append(data)
        elif self._act_depth is not None and self.cards:
            self.cards[-1]["act_text_len"] += len(data.strip())


def summarize_card_act(html: str, *, limit: int = 5) -> list[dict]:
    """最多 `limit` 张卡的 `div.card-act` 结构画像（不含任何正文/计数文本）。"""
    parser = _CardAct(limit=limit)
    try:
        parser.feed(html or "")
        parser.close()
        parser._close_child()
    except Exception:  # noqa: BLE001 - 结构异常也要给出可判读结果
        pass
    return parser.cards


# --- 评论区结构画像 ---------------------------------------------------------

COMMENT_CONTAINERS = (("div", "comment-item"), ("div", "item comment"),
                      ("li", "comment-item"), ("div", "comment-item-wrap"))
COMMENT_WALL = ("请登录", "登录后查看", "安全验证", "访问过于频繁", "由于用户设置")


class _Comments(HTMLParser):
    """评论结构：容器/条目/作者/正文/时间/点赞/子回复/展开按钮；**不保留正文**。"""

    def __init__(self, limit: int = 20) -> None:
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.items: list[dict] = []
        self.containers: dict[str, int] = {}
        self.expand_buttons = 0
        self.wall_markers: list[str] = []
        self._stack: list[tuple[str, str]] = []      # (tag, class 串)
        self._item: dict | None = None
        self._item_depth = 0
        self._depth = 0
        self._child: dict | None = None

    # -- helpers
    def _close_child(self) -> None:
        if self._child is not None and self._item is not None:
            self._item["children"].append(self._child)
            self._child = None

    def _close_item(self) -> None:
        self._close_child()
        if self._item is not None and len(self.items) < self.limit:
            self.items.append(self._item)
        self._item = None

    def handle_starttag(self, tag, attrs):
        if tag in VOID_TAGS:
            return
        attr = {k.lower(): (v or "") for k, v in attrs}
        classes = attr.get("class", "")
        self._depth += 1
        depth = self._depth
        joined = f"{tag}.{classes}".lower()
        for sel_tag, sel_cls in COMMENT_CONTAINERS:
            if tag == sel_tag and sel_cls in classes:
                key = f"{sel_tag}.{sel_cls.replace(' ', '.')}"
                self.containers[key] = self.containers.get(key, 0) + 1
        if "展开更多" in classes or "查看更多" in classes or "more" in classes:
            self.expand_buttons += 1
        if self._item is None:
            if any(k in joined for k in ("comment-item", "comment_item")):
                self._item = {"author": False, "text_tag": None, "text_len": 0,
                              "time_form": "absent", "like_form": "absent",
                              "children": []}
                self._item_depth = depth
            return
        if depth == self._item_depth + 1:
            kind = None
            if "name" in classes or tag == "a" and "u/" in (attr.get("href") or ""):
                kind = "author"
            elif tag in ("p", "span", "div") and ("txt" in classes or "text" in classes
                                                  or "content" in classes):
                kind = "text"
            elif tag in ("a", "span") and ("like" in classes or "attitude" in classes):
                kind = "like"
            if kind == "author":
                self._item["author"] = True
            elif kind == "text":
                self._item["text_tag"] = tag
            elif kind == "like":
                self._item["like_form"] = "node"
            self._child = {"kind": kind or "other", "tag": tag, "len": 0, "_t": []}

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if self._item is not None and self._child is not None:
            text = "".join(self._child.pop("_t")).strip()
            self._child["len"] = len(text)
            if self._child.get("kind") == "text" and self._item["text_len"] == 0:
                self._item["text_len"] = len(text)
            if self._child.get("kind") == "other" and self._item["time_form"] == "absent":
                if re.search(r"(分钟|小时|昨天|今天|\d+-\d+|\d+月\d+日)", text):
                    self._item["time_form"] = "text"
            self._close_child()
        if self._item is not None and self._depth == self._item_depth:
            self._close_item()
        self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._child is not None:
            self._child["_t"].append(data)
        if any(m in (data or "") for m in COMMENT_WALL):
            marker = next(m for m in COMMENT_WALL if m in data)
            if marker not in self.wall_markers:
                self.wall_markers.append(marker)


NET_HOSTS = ("weibo.com", "weibo.cn")


def summarize_network(entries) -> dict:
    """页面自身请求的结构摘要：只留 host/path/method/参数名/状态/大小/顶层键。

    - 只保留 `weibo.com` / `weibo.cn`（含子域）；
    - **参数值、请求头、响应正文一律不保留**；
    - 响应不是 JSON 时不崩，`keys` 记空列表。
    """
    kept: list[dict] = []
    dropped = 0
    for raw in entries or []:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        host = str(raw.get("host") or "").lower()
        if not any(host == h or host.endswith("." + h) for h in NET_HOSTS):
            dropped += 1
            continue
        params = [str(p) for p in (raw.get("params") or [])][:20]
        keys = [str(k) for k in (raw.get("keys") or [])][:12]
        kept.append({
            "host": host,
            "path": str(raw.get("path") or "")[:200],
            "method": str(raw.get("method") or "GET").upper(),
            "params": params,
            "status": raw.get("status"),
            "size": raw.get("size"),
            "keys": keys,
        })
    by_path: dict[str, int] = {}
    for item in kept:
        by_path[item["path"]] = by_path.get(item["path"], 0) + 1
    comment_like = [i for i in kept
                    if re.search(r"comment|buildComments|hotflow", i["path"], re.I)]
    return {"structure": "network:hook", "requests": kept, "count": len(kept),
            "dropped_non_weibo": dropped, "by_path": by_path,
            "comment_like": comment_like}


def summarize_comments(html: str, *, limit: int = 20) -> dict:
    """评论区结构画像（容器/条目/字段形态/子回复/展开按钮/墙），不含正文。"""
    parser = _Comments(limit=limit)
    try:
        parser.feed(html or "")
        parser.close()
        parser._close_item()
    except Exception:  # noqa: BLE001
        pass
    items = parser.items
    return {
        "structure": "comments:html",
        "containers": parser.containers,
        "items": len(items),
        "author_present": sum(1 for i in items if i["author"]),
        "text_nodes": {i["text_tag"]: sum(1 for j in items if j["text_tag"] == i["text_tag"])
                       for i in items if i["text_tag"]},
        "text_len_total": sum(i["text_len"] for i in items),
        "time_nodes": sum(1 for i in items if i["time_form"] != "absent"),
        "like_nodes": sum(1 for i in items if i["like_form"] != "absent"),
        "expand_buttons": parser.expand_buttons,
        "wall_markers": parser.wall_markers,
        "empty_state": (not items) and not parser.wall_markers,
    }
