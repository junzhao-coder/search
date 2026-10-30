"""微博评论入口：调用页面自身端点 `/ajax/statuses/buildComments`，解析为统一记录。

设计要点：
- **只走页面自身端点**（`weibo.com/ajax/statuses/buildComments`），不自造批量抓取；
- 每次调用由 CLI 预扣预算（`comments`），翻页用响应里的 `max_id` + `flow`；
- 解析只保留字段与计数，**不把响应原文落盘**。

响应形状（实测）：
`{ok, data: [...], total_number, max_id, rootComment?, tip_msg?, trendsText?}`；
`data[i]` 顶层评论，`data[i].comments` 为其子回复（楼中楼）。
"""

from __future__ import annotations

import html
import re

TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def clean_text(raw) -> str:
    """去标签、解实体、压缩空白（评论正文可能带 <a> 与表情标签）。"""
    text = TAG.sub(" ", str(raw or ""))
    text = html.unescape(text)
    return SPACE.sub(" ", text).strip()


def _author(item) -> str | None:
    user = item.get("user") or {}
    name = user.get("screen_name") or item.get("screen_name")
    return str(name).strip() if name else None


def _one(item, *, parent_id: str | None, root_id: str | None) -> dict | None:
    if not isinstance(item, dict):
        return None
    cid = str(item.get("idstr") or item.get("id") or "").strip()
    if not cid:
        return None
    text = clean_text(item.get("text_raw") or item.get("text"))
    return {
        "comment_id": cid,
        "parent_id": parent_id,
        "author": _author(item),
        "text": text,
        "text_len": len(text),
        "published_at": (str(item.get("created_at")).strip()
                         if item.get("created_at") else None),
        "like_counts": item.get("like_counts"),
        "root_comment_id": root_id if root_id is not None else (
            str(item.get("rootid")) if item.get("rootid") else None),
        "floor": item.get("floor_number") or item.get("floor"),
    }


def parse_page(payload) -> dict:
    """一页响应 -> {ok, records, total_number, max_id, page_count, child_count}。"""
    if not isinstance(payload, dict):
        return {"ok": False, "records": [], "total_number": None, "max_id": None,
                "page_count": 0, "child_count": 0, "reason": "not_a_dict"}
    ok = payload.get("ok")
    ok_flag = bool(ok) if not isinstance(ok, str) else ok.lower() in ("1", "true")
    data = payload.get("data")
    if not isinstance(data, list):
        data = []
    records: list[dict] = []
    for item in data:
        top = _one(item, parent_id=None, root_id=None)
        if top is None:
            continue
        records.append(top)
        children = item.get("comments") if isinstance(item, dict) else None
        if isinstance(children, list):
            for child in children:
                rec = _one(child, parent_id=top["comment_id"],
                           root_id=top["comment_id"])
                if rec is not None:
                    records.append(rec)
    tops = sum(1 for r in records if r["parent_id"] is None)
    return {
        "ok": ok_flag,
        "records": records,
        "total_number": payload.get("total_number"),
        "max_id": payload.get("max_id") or None,
        "page_count": tops,
        "child_count": len(records) - tops,
        "reason": None if ok_flag else "ok_false",
    }


def merge_pages(pages: list[dict]) -> dict:
    """多页合并（按 comment_id 去重，保留首次出现顺序）。"""
    seen: set[str] = set()
    records: list[dict] = []
    total = None
    last_max = None
    for page in pages:
        if total is None and page.get("total_number") is not None:
            total = page.get("total_number")
        last_max = page.get("max_id")
        for rec in page.get("records") or []:
            if rec["comment_id"] in seen:
                continue
            seen.add(rec["comment_id"])
            records.append(rec)
    return {"records": records, "total_number": total, "max_id": last_max,
            "pages": len(pages),
            "parents": sum(1 for r in records if r["parent_id"] is None),
            "children": sum(1 for r in records if r["parent_id"] is not None)}


def to_records(records: list[dict], *, post_url: str, collected_at: str,
               source: str = "weibo:comment") -> list[dict]:
    """评论记录 -> 统一导出记录（`records.FIELDS` 列集合与帖子一致）。

    映射：`comment_id→native_id`、`like_counts→likes`、`parent_id` 原样保留、
    `root_comment_id` 单独一列、`type="comment"`、`url` 指向所属微博。
    缺项由 `make_record` 自动写进 `missing`（`like_counts=0` 不算缺失）。
    """
    from tools.selection.access import records as rec

    out: list[dict] = []
    for item in records:
        cid = str(item.get("comment_id") or "").strip()
        if not cid:
            continue
        likes = item.get("like_counts")
        values = {
            "native_id": cid,
            "type": "comment",
            "parent_id": item.get("parent_id") or None,
            "url": post_url,
            "title": None,
            "text": item.get("text") or None,
            "published_at": item.get("published_at") or None,
            "voteup": None,
            "comments": None,
            "likes": likes,
            "reposts": None,
            "author": item.get("author") or None,
            "root_comment_id": item.get("root_comment_id") or None,
        }
        evidence = {
            "native_id": "json:data[].idstr",
            "type": "constant:comment",
            "parent_id": "json:data[].comments[].idstr" if values["parent_id"] else None,
            "url": "input:post_url",
            "text": "json:data[].text_raw" if values["text"] else None,
            "published_at": "json:data[].created_at" if values["published_at"] else None,
            "likes": "json:data[].like_counts" if likes is not None else None,
            "author": "json:data[].user.screen_name" if values["author"] else None,
            "root_comment_id": ("json:data[].rootid" if values["root_comment_id"] else None),
        }
        na = ["reposts", "comments", "root_comment_id", "title", "voteup"]
        if not values["parent_id"]:
            na.append("parent_id")     # 顶层评论：没有父评论，不是"没读到"
        out.append(rec.make_record(values=values, evidence=evidence,
                                   collected_at=collected_at, source=source,
                                   not_applicable=na))
    return out


def page_url(mid: str, *, count: int = 20, max_id: str | None = None,
             flow: str = "0") -> str:
    """页面自身端点 URL（参数与实测一致；翻页追加 max_id 与 flow）。"""
    parts = [
        "is_reload=1",
        f"id={mid}",
        "is_show_bulletin=2",
        "is_mix=0",
        f"count={int(count)}",
        "fetch_level=0",
        "locale=zh-CN",
    ]
    if max_id:
        parts.append(f"max_id={max_id}")
        parts.append(f"flow={flow}")
    return "/ajax/statuses/buildComments?" + "&".join(parts)
