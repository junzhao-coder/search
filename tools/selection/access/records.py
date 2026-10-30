"""Canonical record schema + URL hygiene, shared by every access adapter.

Two different jobs, deliberately kept apart:

- `make_record` — build a record from parsed values. Every field carries the
  path it came from in `field_evidence`; a field with no evidence is `null`.
- `normalize_record` — re-shape a record that already exists on disk for
  export. This is a **whitelist**: only `EXPORT_FIELDS` survive, nothing is
  copied from the input, so a stray `cookies`/`password`/`nickname`/nested
  credential blob can never reach an export file.
"""

from __future__ import annotations

import html as _html
import json
import pathlib
import re
import urllib.parse
from html.parser import HTMLParser

FIELDS = ("native_id", "type", "parent_id", "url", "title", "text", "published_at",
          "collected_at", "voteup", "comments", "likes", "reposts", "author",
          "root_comment_id")

#: only these keys are ever written by export; anything else in the input dies.
EXPORT_FIELDS = FIELDS + ("missing", "not_applicable", "supported", "author_redacted",
                          "field_evidence", "source", "evidence_missing",
                          "evidence_rejected")

#: evidence values must start with one of these, or they are dropped.
EVIDENCE_PREFIXES = ("json:", "html:", "meta:", "url:", "input:", "derived:",
                     "heuristic:", "constant:")

#: only the search term survives URL normalization; tokens/cookies never do.
KEPT_QUERY_KEYS = ("q",)

#: source tags are per adapter. Anything not listed under its own prefix is
#: rewritten to `redacted`, so an unknown/credential-ish tag cannot leak out.
SOURCE_RULES = {
    "zhihu:": ("html:links", "search_v3:answer", "search_v3:article",
               "search_v3:zvideo", "detail:answer", "detail:article",
               "detail:zvideo", "comment_v5", "detail:question"),
    "weibo:": ("html:links", "search:status", "detail:status", "comment:hotflow"),
    "douyin:": ("html:links", "search:video", "detail:video"),
}

#: Zhihu entry kept for existing callers.
SOURCE_PREFIX = "zhihu:"
SOURCE_ALLOWED_SUFFIXES = SOURCE_RULES["zhihu:"]


def collapse(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def strip_tags(markup: str) -> str:
    """Visible text only: script/style bodies and tags removed, entities decoded."""
    text = str(markup or "")
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1\s*>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    return collapse(_html.unescape(text))


def sanitize_url(url) -> str | None:
    """Drop query/fragment unless the key is a search term; lowercase the host.

    The port is dropped too: Zhihu serves on default ports, and keeping a port
    would mean trusting an untrusted integer just to reproduce the same page.
    """
    if not url:
        return None
    parts = urllib.parse.urlsplit(str(url).strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    kept = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=False)
            if k in KEPT_QUERY_KEYS]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urllib.parse.urlunsplit((parts.scheme, parts.hostname.lower(), path,
                                    urllib.parse.urlencode(kept), ""))


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


def meta_tags(html: str) -> dict:
    parser = _Meta()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup must not kill a parse
        pass
    return {"meta": parser.meta, "title": collapse(parser.title)}


class Links(HTMLParser):
    """Anchors whose path matches `pattern`; counts every anchor it sees.

    Shared by the adapters: each site supplies its own content-path pattern, so
    the diagnostics can report total/recognized/rejected instead of silently
    dropping the links it did not understand.
    """

    def __init__(self, pattern=None) -> None:
        super().__init__(convert_charrefs=True)
        self.pattern = pattern or re.compile(
            r"/(?:question/\d+(?:/answer/\d+)?|p/\d+|zvideo/\d+)$")
        self.items: list[dict] = []
        self.total = 0
        self.rejected = 0
        self._cur: dict | None = None
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        self.total += 1
        if not self.pattern.search(urllib.parse.urlsplit(href).path):
            self.rejected += 1
            return
        self._cur = {"href": href}
        self._buf = ""

    def handle_data(self, data):
        if self._cur is not None:
            self._buf += data

    def handle_endtag(self, tag):
        if tag == "a" and self._cur is not None:
            self._cur["text"] = collapse(self._buf)
            self.items.append(self._cur)
            self._cur = None
            self._buf = ""


def make_record(*, values: dict, evidence: dict, collected_at: str, source: str,
                author_redacted: bool = False,
                not_applicable=()) -> dict:
    """构造统一记录。

    `not_applicable`：**结构性不适用**的字段（例如顶层评论没有 parent_id、
    评论没有 reposts/comments、帖子没有 root_comment_id）。这些字段**不进 `missing`**——
    `missing` 只表示"该有但没读到"。两者混在一起会让下游把"顶层评论"误判成"父关系丢失"。
    """
    na = {f for f in not_applicable if f in FIELDS}
    record = {field: values.get(field) for field in FIELDS}
    record["url"] = sanitize_url(record["url"])
    record["collected_at"] = collected_at
    record["author_redacted"] = bool(author_redacted)
    record["field_evidence"] = {field: evidence.get(field) for field in FIELDS}
    record["source"] = source
    record["not_applicable"] = sorted(na)
    record["missing"] = [f for f in FIELDS if record[f] is None and f not in na]
    record["supported"] = bool(
        record["native_id"] and record["field_evidence"].get("native_id")
        and (record["title"] or record["text"])
        and (record["field_evidence"].get("title") or record["field_evidence"].get("text")))
    return record


def clean_evidence(evidence) -> tuple[dict, bool]:
    """Keep only known fields with a known prefix. Anything else is dropped."""
    out = {field: None for field in FIELDS}
    rejected = False
    if not isinstance(evidence, dict):
        return out, True
    for field in FIELDS:
        value = evidence.get(field)
        if value is None:
            continue
        text = str(value)
        if text.startswith(EVIDENCE_PREFIXES) and len(text) <= 200:
            out[field] = text
        else:
            rejected = True
    if set(evidence) - set(FIELDS):
        rejected = True  # unknown evidence keys are themselves a rejection
    return out, rejected


def clean_source(source) -> str:
    """Only a known source tag under a known adapter prefix survives."""
    text = str(source or "")
    for prefix, suffixes in SOURCE_RULES.items():
        if text.startswith(prefix) and text[len(prefix):] in suffixes:
            return text
    return "redacted"


def normalize_record(raw: dict, *, collected_at: str | None = None) -> dict:
    """Whitelist re-shape for export. Never copies unknown keys from `raw`."""
    if not isinstance(raw, dict):
        raw = {}
    values = {field: raw.get(field) for field in FIELDS}
    if collected_at:
        values["collected_at"] = collected_at
    evidence, rejected = clean_evidence(raw.get("field_evidence"))
    has_evidence = any(evidence.values())
    record = {field: values[field] for field in FIELDS}
    record["url"] = sanitize_url(values.get("url"))
    record["field_evidence"] = evidence
    record["source"] = clean_source(raw.get("source"))
    record["author_redacted"] = True
    if rejected:
        record["evidence_rejected"] = True
    if not has_evidence:
        record["evidence_missing"] = True
    record["supported"] = bool(
        values.get("native_id") and has_evidence
        and (values.get("title") or values.get("text")))
    record["missing"] = [f for f in FIELDS if record.get(f) is None]
    return {key: record[key] for key in EXPORT_FIELDS if key in record}


def read_records(path) -> list[dict]:
    """JSONL (one object per line) or a JSON array."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        payload = json.loads(stripped)
        return [x for x in payload if isinstance(x, dict)]
    out = []
    for line in stripped.splitlines():
        line = line.strip()
        if line:
            item = json.loads(line)
            if isinstance(item, dict):
                out.append(item)
    return out


def write_records(records: list[dict], path, *, fmt: str = "jsonl") -> str:
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        target.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    else:
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return str(target)
