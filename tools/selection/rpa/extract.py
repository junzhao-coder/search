"""从**浏览器渲染后的可见卡片**生成记录（纯函数，离线可测）。

边界（回应退回意见）：
- 这里**不解析原始 HTML**：输入是页面内 JS（`session.CARD_JS`）在渲染后取出的**可见卡片**数组，
  元素形如 `{container_id, id, url, text, title, time, counts, hidden}`；
- 卡片 ID 与正文由 JS 限定在**同一容器**内取；Python 只做校验，没有"整页当一张卡"的回退；
- 隐藏卡片、缺键、非数字 ID、跨域链接、重复容器、重复 ID 一律拒绝并计数；
- 空/全被拒 → `stop="empty"|"unknown"`，调用方据此返回非零，不伪造成功。
"""

from __future__ import annotations

import re
import urllib.parse

from tools.selection.access import records as rec

#: 这些选择器写在 `session.CARD_JS` 里；没有真实页面证据，全部标假设。
ASSUMED_SELECTORS = (
    "card_container: article, div[class*='card'] —— 只取最外层且可见 (assumed)",
    "card_id: 同一容器内可见 a[href*='/status/'] 的第一个数字 id，且必须等于 URL 路径 id (assumed)",
    "card_text: 原 DOM 可见文本节点（跳过导航/作者/控制文字/内层卡片）(assumed)",
    "card_title: 同一容器内可见 h1/h2/h3 或 [class*='title'] (assumed)",
    "nested_policy: 内层卡片整棵跳过，不单独输出，也不把其正文并入外层 (assumed)",
)

ALLOWED_HOSTS = {"m.weibo.cn", "weibo.com", "weibo.cn"}

#: 只认这两种 status/detail 路径；路径里的 id 必须与卡片 id 完全一致。
STATUS_PATH = re.compile(r"^/(?:status|detail)/(\d{6,})/?$")

#: 卡片必须有的键；缺任一 → 该卡直接拒绝（不补默认值）。
REQUIRED_KEYS = ("container_id", "id", "url", "text")


def _check(card) -> str | None:
    """返回拒绝原因；None 表示可以进入记录构建。search 与 detail 共用。

    桌面版卡片（带 `id_source`）走独立分支：ID 可以是 `mid`（数字）或 `bid`（base62），
    来源链接必须是 **本卡自己的** https 链接，且路径里确实包含这个 ID。
    """
    if not isinstance(card, dict):
        return "not_a_card"
    if card.get("hidden") is True:
        return "hidden"
    if not all(key in card for key in REQUIRED_KEYS):
        return "missing_keys"
    native_id = str(card.get("id") or "").strip()
    if not native_id:
        return "bad_id"
    url = str(card.get("url") or "")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return "bad_scheme"
    if (parts.hostname or "").lower() not in ALLOWED_HOSTS:
        return "foreign_host"
    if card.get("id_source"):
        if not re.fullmatch(r"[0-9A-Za-z]{5,}", native_id):
            return "bad_id"
        # 链接必须属于本卡片：mid 卡看 bid 是否出现在链接里，bid 卡看 id 本身。
        anchor = native_id if card.get("id_source") == "bid" else str(card.get("bid") or "")
        if not anchor or anchor not in parts.path:
            return "url_id_mismatch"
    else:
        if not native_id.isdigit():
            return "bad_id"
        match = STATUS_PATH.match(parts.path or "")
        if not match:
            return "bad_path"
        if match.group(1) != native_id:
            return "url_id_mismatch"
    if not rec.collapse(card.get("text")) and not rec.collapse(card.get("title")):
        return "no_text"
    return None


def _record(card: dict, *, collected_at: str, source: str) -> dict:
    native_id = str(card["id"]).strip()
    title = rec.collapse(card.get("title")) or None
    text = rec.collapse(card.get("text")) or None
    counts = card.get("counts") or {}
    author = rec.collapse(card.get("author")) or None
    values = {"native_id": native_id, "type": "status", "parent_id": None,
              "url": str(card["url"]), "title": title, "text": text,
              "published_at": rec.collapse(card.get("time")) or None,
              "voteup": None, "comments": counts.get("comments"),
              "likes": counts.get("likes"), "reposts": counts.get("reposts"),
              "author": author}
    evidence = {"native_id": "dom:card a[href]", "type": "derived:status/<id>",
                "parent_id": None, "url": "dom:card a[href]",
                "title": "dom:card title" if title else None,
                "text": "dom:card visible text" if text else None,
                "published_at": "dom:card time text" if values["published_at"] else None,
                "voteup": None,
                "comments": "dom:card counts" if counts.get("comments") is not None else None,
                "likes": "dom:card counts" if counts.get("likes") is not None else None,
                "reposts": "dom:card counts" if counts.get("reposts") is not None else None,
                "author": "dom:card a.name" if author else None}
    return rec.make_record(values=values, evidence=evidence,
                           collected_at=collected_at, source=source,
                           not_applicable=("root_comment_id",))


def extract_cards(cards, *, collected_at: str, limit: int = 5,
                  source: str = "weibo:search:status") -> dict:
    """卡片数组 -> 记录（去重、拒绝计数、缺项保留）。"""
    cards = list(cards or [])
    records: list[dict] = []
    details: list[dict] = []
    seen_ids: set[str] = set()
    seen_containers: set[str] = set()
    rejected: dict[str, int] = {}
    for card in cards:
        reason = _check(card)
        if reason is None:
            container = str(card.get("container_id") or "")
            if container and container in seen_containers:
                reason = "duplicate_container"
            elif str(card["id"]) in seen_ids:
                reason = "duplicate_id"
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        record = _record(card, collected_at=collected_at, source=source)
        seen_ids.add(record["native_id"])
        if card.get("container_id"):
            seen_containers.add(str(card["container_id"]))
        records.append(record)
        counts = card.get("counts") or {}
        meta = card.get("count_meta") or {}
        count_fields = ("reposts", "comments", "likes")
        missing = list(record["missing"])
        for field in count_fields:
            if counts.get(field) is None and field not in missing:
                missing.append(field)
        details.append({
            "native_id": record["native_id"],
            "id_source": card.get("id_source") or "url",
            "author": rec.collapse(card.get("author")) or None,
            "text_len": len(record["text"] or ""),
            "published_at": record["published_at"],
            "reposts": counts.get("reposts"),
            "comments": record["comments"],
            "likes": record["likes"],
            "count_source": {f: (meta.get(f) or {}).get("source") for f in count_fields},
            "count_unit": {f: (meta.get(f) or {}).get("unit") for f in count_fields},
            "url": record["url"],
            "missing": missing,
        })
        if len(records) >= limit:
            break
    stop = None
    if not records:
        stop = "empty" if cards else "unknown"
    return {"records": records, "stop": stop, "structure": "dom:cards",
            "diagnostics": {"cards_in": len(cards), "records": len(records),
                            "rejected": rejected},
            "details": details,
            "assumptions": list(ASSUMED_SELECTORS)}


def extract_detail(card, *, collected_at: str) -> dict:
    """详情：与 search 同一套 `_check`；**任何**拒绝原因都返回 unsupported 且无记录。"""
    if card is None:
        return {"record": None, "stop": "unsupported", "structure": "dom:detail",
                "diagnostics": {"reason": "no_card"},
                "assumptions": list(ASSUMED_SELECTORS)}
    reason = _check({**card, "container_id": card.get("container_id", "")})
    if reason is not None:
        return {"record": None, "stop": "unsupported", "structure": "dom:detail",
                "diagnostics": {"reason": reason},
                "assumptions": list(ASSUMED_SELECTORS)}
    record = _record(card, collected_at=collected_at, source="weibo:detail:status")
    return {"record": record, "stop": None, "structure": "dom:detail",
            "diagnostics": {"reason": None, "text_len": len(record["text"] or "")},
            "assumptions": list(ASSUMED_SELECTORS)}
