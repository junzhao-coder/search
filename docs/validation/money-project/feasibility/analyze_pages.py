"""分析已存证的 HTML（不联网），判定拦截类型并抽取可读条目。

输入：pages/*.html（probe 阶段保存的 document.documentElement.outerHTML）
输出：data/analysis.json、data/items.jsonl、logs/analyze.log
只用 stdlib（re/html），不引入依赖、不联网。
"""

from __future__ import annotations

import hashlib
import html as htmlmod
import json
import pathlib
import re
import sys
import time

BASE = pathlib.Path(__file__).resolve().parent
PAGES = BASE / "pages"
DATA = BASE / "data"
LOGS = BASE / "logs"
DATA.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)

MARKERS = {
    "login": ["登录", "扫码登录", "手机号登录", "请先登录", "立即登录", "登录后查看"],
    "captcha": ["安全验证", "滑动验证", "验证码", "captcha", "人机验证", "异常访问", "访问过于频繁"],
    "empty": ["暂无内容", "没有找到", "无相关结果", "内容不存在"],
}
CARD_PATTERNS = {
    "xianyu": [r'class="[^"]*feeds[^"]*"', r'class="[^"]*feed-item[^"]*"', r'class="[^"]*cardWarp[^"]*"',
               r'class="[^"]*item[^"]*"'],
    "xiaohongshu": [r'class="[^"]*note-item[^"]*"', r'<section[^>]*note-item', r'class="[^"]*note[^"]*"'],
}
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def strip_tags(s: str) -> str:
    s = SCRIPT_RE.sub(" ", s)
    s = TAG_RE.sub(" ", s)
    s = htmlmod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def ctx(text: str, needle: str, width: int = 60) -> list[str]:
    out = []
    for m in re.finditer(re.escape(needle), text):
        a, b = max(0, m.start() - width), min(len(text), m.end() + width)
        out.append(text[a:b].strip())
        if len(out) >= 3:
            break
    return out


def main() -> int:
    t0 = time.time()
    analysis = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pages": []}
    items_out = []
    for f in sorted(PAGES.glob("*.html")):
        raw = f.read_text(encoding="utf-8", errors="replace")
        title = TITLE_RE.search(raw)
        title = strip_tags(title.group(1)) if title else ""
        text = strip_tags(raw)
        platform = "xianyu" if f.name.startswith("xianyu") else "xiaohongshu"
        found = {k: [m for m in v if m in text or m.lower() in raw.lower()] for k, v in MARKERS.items()}
        contexts = {k: {m: ctx(text, m) for m in found[k][:2]} for k in found if found[k]}
        counts = {f"pat{i}": len(re.findall(pat, raw, re.I)) for i, pat in enumerate(CARD_PATTERNS[platform])}
        has_initial = "__INITIAL_STATE__" in raw
        has_next = "__NEXT_DATA__" in raw
        # 可读"卡片"候选：含足够中文长度且像标题的块（用可见文本按分隔符切分近似）
        chunks = [c for c in re.split(r"(?<=[。！？!?])\s+| {2,}|\n", text) if len(c) >= 12]
        candidates = [c[:160] for c in chunks[:20]]
        verdict = ("captcha" if found["captcha"] else
                   "login_wall" if found["login"] else
                   "empty_result" if found["empty"] else
                   "content_visible" if len(text) > 300 else "unclassified")
        analysis["pages"].append({
            "file": f.name, "platform": platform, "bytes": len(raw.encode("utf-8", "replace")),
            "sha256": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest(),
            "title": title, "visible_text_len": len(text), "verdict": verdict,
            "markers_found": found, "marker_contexts": contexts, "card_pattern_counts": counts,
            "has_initial_state": has_initial, "has_next_data": has_next,
            "visible_sample": text[:400], "candidate_texts": candidates,
        })
        for c in candidates:
            items_out.append({"page": f.name, "platform": platform, "text": c, "source": "visible_dom"})
    analysis["item_total"] = len(items_out)
    (DATA / "analysis.json").write_bytes(json.dumps(analysis, ensure_ascii=False, indent=2).encode("utf-8"))
    with (DATA / "items.jsonl").open("w", encoding="utf-8") as fh:
        for it in items_out:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    (LOGS / "analyze.log").write_bytes(json.dumps(
        {"cmd": "python analyze_pages.py", "cwd": str(BASE), "utc": analysis["generated_utc"],
         "pages": len(analysis["pages"]), "items": len(items_out), "elapsed_s": round(time.time() - t0, 2),
         "exit": 0}, ensure_ascii=False, indent=2).encode("utf-8"))
    for p in analysis["pages"]:
        print(f"{p['platform']:12s} {p['file']:45s} verdict={p['verdict']:16s} text_len={p['visible_text_len']:6d} "
              f"cards={p['card_pattern_counts']} initial={p['has_initial_state']} next={p['has_next_data']}")
    print("ITEM_TOTAL", len(items_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
