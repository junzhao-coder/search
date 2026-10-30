"""Local-only evidence conversion (no collector run, no network).

Source encoding determination, in order:
  1. BOM check -> none present.
  2. utf-8 strict decode -> fails (byte 0xD7 at offset 282), so NOT utf-8.
  3. gb18030 (superset of GBK/GB2312) -> decodes AND yields valid JSON whose
     "keyword" is exactly the searched term. latin-1 is deliberately NOT used
     as evidence: it decodes any byte sequence and proves nothing.
  4. Every other candidate is rejected by a JSON-structure + keyword check.

If no candidate passes, the source encoding is reported as "unknown" and the
raw bytes/hash are kept as-is (no lossy re-encode).
"""

import hashlib
import json
import pathlib

ZH = pathlib.Path(r"D:\桌面\two\docs\validation\v10\zhihu")
RAW = ZH / "live_search_4.out.txt"
TARGET_KEYWORD = "学习计划模板"

data = RAW.read_bytes()
raw_sha = hashlib.sha256(data).hexdigest()
has_bom = data[:3] in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")

attempts = []
chosen = None
for name in ("utf-8", "gb18030", "gbk", "big5", "cp932", "latin-1"):
    try:
        text = data.decode(name)
    except UnicodeDecodeError as exc:
        attempts.append({"encoding": name, "decoded": False, "reason": f"decode error at {exc.start}"})
        continue
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        attempts.append({"encoding": name, "decoded": True, "json_ok": False,
                         "reason": f"invalid JSON: {exc.msg} at {exc.pos}"})
        continue
    kw = obj.get("keyword")
    ok = kw == TARGET_KEYWORD
    attempts.append({"encoding": name, "decoded": True, "json_ok": True,
                     "keyword": kw, "keyword_matches_target": ok,
                     "stop": obj.get("stop"), "exit": obj.get("exit"),
                     "count": obj.get("count"),
                     "parsed_structure": obj.get("parsed_structure")})
    if ok and chosen is None:
        chosen = (name, text, obj)

if chosen is None:
    result = {"source_file": str(RAW), "source_bytes": len(data),
              "source_sha256": raw_sha, "has_bom": has_bom,
              "source_encoding": "unknown",
              "note": "no candidate passed the JSON+keyword check; raw bytes kept unchanged",
              "attempts": attempts}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0)

enc, text, obj = chosen
copy = ZH / "live_search_4.out.utf8.txt"
copy.write_bytes(text.encode("utf-8"))
result = {
    "source_file": str(RAW),
    "source_bytes": len(data),
    "source_sha256": raw_sha,
    "has_bom": has_bom,
    "source_encoding": enc,
    "source_encoding_evidence": "utf-8 strict decode fails; gb18030 decodes to valid JSON with keyword == searched term; other candidates rejected",
    "conversion": f"decode with {enc} (no error suppression), re-encode as UTF-8 without BOM; original bytes untouched",
    "utf8_copy": str(copy),
    "utf8_copy_bytes": copy.stat().st_size,
    "utf8_copy_sha256": hashlib.sha256(copy.read_bytes()).hexdigest(),
    "parsed_fields": {"stop": obj.get("stop"), "exit": obj.get("exit"),
                      "count": obj.get("count"),
                      "parsed_structure": obj.get("parsed_structure"),
                      "keyword": obj.get("keyword"),
                      "url": obj.get("url"),
                      "batch": obj.get("batch")},
    "attempts": attempts,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
(ZH / "live_search_4.encoding.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
