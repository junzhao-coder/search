"""Deterministic local single-thread fixture for the engine trial.

The DOM mirrors the tieba thread/comment shape already used by
`tools.selection.access.tieba` (`pb-text-wrapper`, `pb-comment-item[data-id]`,
`pb-lzl-item`), but every value here is local and synthetic.  The page records
its own click / wheel / scroll / expand events in `window.__events`, so the
collector can assert page activity instead of trusting a driver's own log.

The page deliberately declares 12 comments while only 9 can be revealed.  That
is what makes the "no growth" stop an honest partial result instead of a
fabricated "complete" one.
"""

from __future__ import annotations

import html
import json
import pathlib

THREAD_ID = "900000001"
THREAD_TITLE = "单帖采集基线：本地 fixture"
THREAD_BODY = (
    "这是用于 Playwright 与 nodriver 对照的本地单帖正文。"
    "正文、评论、点赞数与发布时间都只从当前页面读取；"
    "读不到的字段标记未知，不用零或接口数据补齐。"
)
THREAD_AUTHOR = "楼主甲"
THREAD_TIME = "2026-10-01 12:00"
THREAD_LIKES = 37
DECLARED_COMMENTS = 12

COMMENTS = [
    {"id": "910000001", "author": "评论者乙", "text": "第一条评论：滚轮与展开都要留下页面事件。",
     "time": "2026-10-01 12:01", "likes": 5},
    {"id": "910000002", "author": "评论者丙", "text": "第二条评论：点赞数和发布时间分开归属。",
     "time": "2026-10-01 12:02", "likes": 0},
    {"id": "910000003", "author": "评论者丁", "text": "第三条评论：没有读到就标未知，不填零。",
     "time": "2026-10-01 12:03", "likes": 12},
    {"id": "910000004", "author": "评论者戊", "text": "第四条评论：滚动后才出现。",
     "time": "2026-10-01 12:04", "likes": 3},
    {"id": "910000005", "author": "评论者己", "text": "第五条评论：按原生 ID 增量去重。",
     "time": "2026-10-01 12:05", "likes": 8},
    {"id": "910000006", "author": "评论者庚", "text": "第六条评论：没有到底证据就标部分。",
     "time": "2026-10-01 12:06", "likes": 1},
    {"id": "910000007", "author": "评论者辛", "text": "第七条评论：加载更多后出现。",
     "time": "2026-10-01 12:07", "likes": 2},
    {"id": "910000008", "author": "评论者壬", "text": "第八条评论：展开楼中楼不串字段。",
     "time": "2026-10-01 12:08", "likes": 4},
    {"id": "910000009", "author": "评论者癸", "text": "第九条评论：页面声明 12 条，只看到 9 条。",
     "time": "2026-10-01 12:09", "likes": 6},
]

LZL = [
    {"id": "920000001", "parent": "910000001", "author": "楼中楼甲",
     "text": "楼中楼第一条：父评论是 910000001。", "time": "2026-10-01 12:01",
     "likes": 1},
    {"id": "920000002", "parent": "910000001", "author": "楼中楼乙",
     "text": "楼中楼第二条：没有稳定 ID 时不能合成。", "time": "2026-10-01 12:02",
     "likes": 0},
]


def ground_truth() -> dict:
    """What a complete read of this fixture should contain."""
    comment_ids = [c["id"] for c in COMMENTS]
    lzl_ids = [c["id"] for c in LZL]
    return {
        "thread_id": THREAD_ID,
        "thread_title": THREAD_TITLE,
        "thread_body": THREAD_BODY,
        "thread_author": THREAD_AUTHOR,
        "thread_time": THREAD_TIME,
        "thread_likes": THREAD_LIKES,
        "declared_comments": DECLARED_COMMENTS,
        "comment_ids": comment_ids,
        "lzl_ids": lzl_ids,
        "ids": [THREAD_ID, *comment_ids, *lzl_ids],
        "comment_likes": {c["id"]: c["likes"] for c in COMMENTS},
        "comment_times": {c["id"]: c["time"] for c in COMMENTS},
        "lzl_parent": {c["id"]: c["parent"] for c in LZL},
    }


def _comment_html(item: dict, *, lzl: bool = False, extra: str = "") -> str:
    cls = "pb-lzl-item" if lzl else "pb-comment-item"
    likes = int(item["likes"])
    return f"""
      <div class="{cls}" data-id="{html.escape(item['id'])}">
        <a class="head-name" href="/u/{html.escape(item['id'][-1])}">{html.escape(item['author'])}</a>
        <div class="comment-desc-left"><span>{html.escape(item['time'])}</span></div>
        <span class="pb-text-wrapper">{html.escape(item['text'])}</span>
        <div class="pb-agree"><span class="pb-agree-num" data-likes="{likes}">{likes}</span> 赞</div>{extra}
      </div>"""


def _thread_html() -> str:
    return f"""
    <div class="image-text" data-tid="{THREAD_ID}">
      <div class="thread-head">
        <a class="head-name" href="/u/1">{html.escape(THREAD_AUTHOR)}</a>
        <span class="post-num">{html.escape(THREAD_TIME)}</span>
      </div>
      <h1><span class="pb-title">{html.escape(THREAD_TITLE)}</span></h1>
      <div class="d_post_content">
        <span class="pb-text-wrapper" tid="{THREAD_ID}" order-id="0">{html.escape(THREAD_BODY)}</span>
      </div>
      <div class="pb-agree"><span class="pb-agree-num" data-likes="{THREAD_LIKES}">{THREAD_LIKES}</span> 赞</div>
      <a id="tab-全部回复 ({DECLARED_COMMENTS})" href="/p/{THREAD_ID}">全部回复 ({DECLARED_COMMENTS})</a>
    </div>"""


def build_html() -> str:
    nested = "".join(_comment_html(c, lzl=True) for c in LZL)
    extra = f"""
        <div class="show-more-lzl" role="button" tabindex="0">展开楼中楼（{len(LZL)}）</div>
        <div class="pb-lzl-list" style="display:none">{nested}
        </div>"""
    initial = "".join(
        _comment_html(c, extra=extra if c["id"] == COMMENTS[0]["id"] else "")
        for c in COMMENTS[:3]
    )
    later = "".join(_comment_html(c) for c in COMMENTS[3:])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(THREAD_TITLE)}_百度贴吧</title>
  <style>
    body {{ margin: 0; font: 15px/1.6 "Microsoft YaHei", sans-serif; background: #f4f4f4; }}
    #page {{ max-width: 820px; margin: 0 auto; padding: 16px 16px 40px; background: #fff; }}
    .image-text {{ border-bottom: 2px solid #ddd; padding-bottom: 12px; }}
    .thread-head {{ display: flex; gap: 12px; color: #666; }}
    .pb-title {{ font-size: 22px; }}
    .pb-comment-item {{ border-bottom: 1px solid #eee; padding: 12px 0; }}
    .pb-lzl-list {{ margin: 8px 0 0 28px; padding-left: 10px; border-left: 2px solid #e5e5e5; }}
    .pb-lzl-item {{ padding: 6px 0; color: #444; }}
    .pb-agree {{ color: #888; font-size: 13px; }}
    .show-more-lzl {{ display: inline-block; margin-top: 6px; color: #1a6fb5; cursor: pointer; }}
    #load-more {{ margin: 16px 0; padding: 8px 16px; cursor: pointer; }}
  </style>
</head>
<body>
  <div id="page">
    {_thread_html()}
    <div class="pc-pb-comments" id="comments">{initial}
    </div>
    <button id="load-more" type="button">加载更多评论</button>
  </div>
  <template id="comment-templates">{later}
  </template>
  <script>
  (() => {{
    window.__events = [];
    const log = (type, detail) => window.__events.push({{
      type: type, detail: detail || null,
      y: Math.round(window.scrollY), t: Math.round(performance.now())
    }});
    document.addEventListener('click', (e) => {{
      const el = e.target.closest('button, [role="button"]');
      log('click', {{
        id: el ? el.id : null,
        cls: el ? String(el.className) : null,
        text: el ? (el.innerText || '').slice(0, 24) : null,
        trusted: e.isTrusted
      }});
    }}, true);
    window.addEventListener('wheel', (e) => log('wheel', {{dy: Math.round(e.deltaY),
      trusted: e.isTrusted}}), {{passive: true}});
    window.addEventListener('scroll', (e) => log('scroll', {{y: Math.round(window.scrollY),
      trusted: e.isTrusted}}), {{passive: true}});

    const pool = Array.from(document.getElementById('comment-templates').content
      .querySelectorAll('.pb-comment-item'));
    const comments = document.getElementById('comments');
    const present = new Set(Array.from(comments.querySelectorAll('.pb-comment-item'))
      .map((el) => el.getAttribute('data-id')));
    const addBatch = (count) => {{
      let added = 0;
      while (pool.length && added < count) {{
        const node = pool.shift().cloneNode(true);
        comments.appendChild(node);
        present.add(node.getAttribute('data-id'));
        added += 1;
      }}
      if (added) log('comments_added', {{count: added, total: present.size}});
      return added;
    }};

    document.getElementById('load-more').addEventListener('click', (e) => {{
      const added = addBatch(3);
      log('load_more', {{added: added, total: present.size, trusted: e.isTrusted}});
    }});

    const expand = document.querySelector('.show-more-lzl');
    if (expand) {{
      expand.addEventListener('click', (e) => {{
        const list = document.querySelector('.pb-lzl-list');
        const opening = list.style.display === 'none';
        list.style.display = opening ? 'block' : 'none';
        e.currentTarget.innerText = opening ? '收起楼中楼' : '展开楼中楼（{len(LZL)}）';
        log('expand', {{open: opening,
          count: list.querySelectorAll('.pb-lzl-item').length, trusted: e.isTrusted}});
      }});
    }}

    let lazyDone = false;
    window.addEventListener('scroll', (e) => {{
      if (!lazyDone && window.scrollY > 200) {{
        lazyDone = true;
        const added = addBatch(3);
        log('lazy_load', {{added: added, total: present.size, trusted: e.isTrusted}});
      }}
    }}, {{passive: true}});
  }})();
  </script>
</body>
</html>
"""


def build_fixture(path) -> dict:
    """Write the fixture and return `{path, url, ground_truth}`."""
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_html(), encoding="utf-8")
    return {"path": str(target), "url": target.resolve().as_uri(),
            "ground_truth": ground_truth()}


def write_ground_truth(path, truth: dict) -> dict:
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(truth, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return {"path": str(target)}
