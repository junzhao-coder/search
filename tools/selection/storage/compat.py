"""兼容层：既有 14 字段记录 <-> 存储行，以及两种导出。

* ``item_from_record`` 把 ``access.records.make_record`` 产出的记录转成存储行。
  旧记录的 ``published_at`` 是页面原文，落到 ``published_at_raw``，不假装已归一化。
* ``record_from_row`` 把存储行还原成 23 列导出记录，**复用**
  ``records.normalize_record`` 的白名单/证据规则；旧模块一行不改。
* ``export_compat`` 必须指定 platform：23 列里没有平台列，混平台导出会撞 ID。
"""

from __future__ import annotations

import json
import pathlib

from tools.selection.access import records as rec

from . import store

#: 23 列导出里"结构性不适用"的缺省；导入旧记录时保留记录自带的那一份。
DEFAULT_NOT_APPLICABLE = {
    store.POST: ("root_comment_id", "parent_id", "voteup", "reposts"),
    store.COMMENT: ("title", "voteup", "reposts"),
}

_TYPE_TO_KIND = {"thread": store.POST, "post": store.POST, "comment": store.COMMENT}

#: 23 列字段 -> 存储列；没有对应列的字段（voteup/reposts）永远视为未采集。
_FIELD_TO_COLUMN = {
    "native_id": "native_id", "type": "kind", "parent_id": "parent_native_id",
    "url": "url", "title": "title", "text": "text",
    "collected_at": "collected_at", "comments": "comments_count",
    "likes": "likes", "author": "author",
}


def _field_has_value(row: dict, field: str) -> bool:
    if field == "published_at":
        return (row.get("published_at") is not None
                or row.get("published_at_raw") is not None)
    if field == "root_comment_id":
        return (row.get("kind") == store.COMMENT
                and row.get("post_native_id") is not None)
    if field in ("voteup", "reposts"):
        return False
    column = _FIELD_TO_COLUMN.get(field)
    return column is not None and row.get(column) is not None


def clean_not_applicable(row: dict, fields) -> list:
    """实际值优先：字段已有值就不再算"不适用"，保证 missing/不适用互斥。"""
    return [field for field in fields if not _field_has_value(row, field)]


def _id_text(value) -> str | None:
    """旧 JSON 里的数字 ID 按十进制文本保存；空串/None 视为没有 ID。"""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("id_invalid")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    raise ValueError("id_invalid")


def item_from_record(record: dict, *, platform: str) -> store.Item:
    """旧记录 -> 存储行。只认 thread/post/comment；未知类型直接报错，不猜。

    旧 23 列没有独立的"父级已知/未知"标记，只能按证据处理：

    * 评论有 ``parent_id``：视为已知父级（等于所属帖子 ID = 已知顶层）；
    * 只有 ``root_comment_id``、没有 ``parent_id``：父级**未知**，保留帖子归属；
    * 两者都没有：连帖子归属都不确定，直接报错，不猜。
    """
    data = record if isinstance(record, dict) else {}
    kind = _TYPE_TO_KIND.get(str(data.get("type") or "").strip().lower())
    if kind is None:
        raise ValueError("record_type_invalid")
    native_id = _id_text(data.get("native_id"))
    parent_known = None
    if kind == store.POST:
        post_native_id, parent_native_id = native_id, None
    else:
        root = data.get("root_comment_id")
        parent = data.get("parent_id")
        post_native_id = _id_text(root if root is not None else parent)
        if post_native_id is None:
            raise ValueError("comment_requires_post_native_id")
        parent_native_id = _id_text(parent)
        parent_known = parent_native_id is not None
    values = {
        "platform": platform, "kind": kind, "native_id": native_id,
        "post_native_id": post_native_id, "parent_native_id": parent_native_id,
        "parent_known": parent_known,
        "url": data.get("url"), "title": data.get("title"), "text": data.get("text"),
        "text_truncated": data.get("text_truncated"), "author": data.get("author"),
        "likes": data.get("likes"), "comments_count": data.get("comments"),
        "published_at_raw": data.get("published_at"),
        "source": data.get("source"),
        "evidence": data.get("field_evidence") or None,
        "not_applicable": tuple(data.get("not_applicable") or ()),
    }
    # 旧记录没有采集时间时按导入时间记，不伪造一个更早的时间。
    if data.get("collected_at"):
        values["collected_at"] = data["collected_at"]
    return store.Item(**values)


def items_from_records(records, *, platform: str) -> list:
    return [item_from_record(record, platform=platform) for record in records or ()]


def record_from_row(row: dict) -> dict:
    """存储行 -> 23 列记录；``normalize_record`` 负责白名单、missing 与 supported。

    父级未知的评论：``parent_id`` 为空并进 ``missing``，不会伪造成帖子的直接子评论。
    """
    kind = row.get("kind")
    raw = {
        "native_id": row.get("native_id"),
        "type": "thread" if kind == store.POST else "comment",
        "parent_id": row.get("parent_native_id"),
        "url": row.get("url"),
        "title": row.get("title"),
        "text": row.get("text"),
        # 23 列只有一列时间：优先规范化值，没有就保留原文。
        "published_at": row.get("published_at") or row.get("published_at_raw"),
        "collected_at": row.get("collected_at"),
        "voteup": None,
        "comments": row.get("comments_count"),
        "likes": row.get("likes"),
        "reposts": None,
        "author": row.get("author"),
        "root_comment_id": (row.get("post_native_id")
                            if kind == store.COMMENT else None),
        "author_redacted": False,
        "field_evidence": dict(row.get("evidence") or {}),
        "source": row.get("source"),
        "not_applicable": clean_not_applicable(
            row, list(row.get("not_applicable")
                      or DEFAULT_NOT_APPLICABLE[kind])),
    }
    if row.get("text_truncated") is not None:
        raw["text_truncated"] = bool(row["text_truncated"])
    return rec.normalize_record(raw)


def export_compat(storage: store.Storage, path, *, platform: str,
                  fmt: str = "csv") -> dict:
    """按平台导出 23 列兼容视图；平台必填，避免不同平台同 ID 混在一起。"""
    if not str(platform or "").strip():
        raise ValueError("platform_required")
    if fmt not in ("csv", "jsonl"):
        raise ValueError("fmt_invalid:%s" % fmt)
    rows = storage.items(platform=platform)
    records = [record_from_row(row) for row in rows]
    written = rec.write_records(records, path, fmt=fmt)
    return {"count": len(records), "path": written, "format": fmt,
            "columns": len(rec.EXPORT_FIELDS)}


def export_items(storage: store.Storage, path, *, platform: str | None = None) -> dict:
    """完整存储视图（JSONL）：含平台、精度、原始时间、ID 是否可核实。

    ``not_applicable`` 按当前实际值过滤，避免完整视图里也出现"有值又标不适用"。
    """
    rows = storage.items(platform=platform)
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            row["not_applicable"] = tuple(
                clean_not_applicable(row, row.get("not_applicable") or ()))
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"count": len(rows), "path": str(target), "format": "jsonl",
            "platform": platform}


def read_records_file(path) -> list:
    """同 ``records.read_records``，但容忍 Windows 编辑器/PS 写出的 UTF-8 BOM。"""
    text = pathlib.Path(path).read_text(encoding="utf-8-sig")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        payload = json.loads(stripped)
        return [item for item in payload if isinstance(item, dict)]
    out = []
    for line in stripped.splitlines():
        line = line.strip()
        if line:
            item = json.loads(line)
            if isinstance(item, dict):
                out.append(item)
    return out
