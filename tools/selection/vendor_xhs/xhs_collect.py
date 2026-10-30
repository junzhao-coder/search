#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""xhs_collect.py —— 单账号保守采集器（CDP 驱动真实 Chrome）

设计原则：**不封号优先于产量**。所有参数按实测风控阈值再打 2 倍安全余量。

实测依据（xhs_rate_limit.py）
    同一 profile 间隔 1.5s 连打 → 第 10 次触发 300012
    → 推断令牌桶约 10 个，回填速率 3~5s/个
    → 本采集器默认 10s/请求（约 2 倍余量），带 ±30% 抖动

三道熔断
    1. 单次会话上限 150 请求 → 强制休息 15 分钟
    2. 每日上限 600 请求 → 当日停止
    3. 任何风控信号 → 立即停机并记录

用法
----
# 0. 首次登录（有头 Chrome，扫码，profile 落盘）
python xhs_collect.py login --profile profiles/xhs_13900000000

# 1. 检查登录态
python xhs_collect.py check --profile profiles/xhs_13900000000

# 2. 抓推荐流元数据（最省，1 次加载 = 30 条）
python xhs_collect.py explore --profile profiles/xhs_13900000000 --pages 5

# 3. 抓笔记详情 + 评论（1 次加载 = 1 篇 + 10 条评论）
python xhs_collect.py note --profile profiles/xhs_13900000000 --ids id1,id2

# 4. 从 DB 里取未抓详情的笔记，批量补全
python xhs_collect.py fill --profile profiles/xhs_13900000000 --limit 100

# 5. 抓用户主页
python xhs_collect.py user --profile profiles/xhs_13900000000 --ids uid1

# 6. 关键词搜索（需登录态）
python xhs_collect.py search --profile profiles/xhs_13900000000 --kw 露营 --pages 3

# 7. 看进度
python xhs_collect.py stats
"""
import argparse
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import websockets.sync.client as ws

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

CST = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DEFAULT = os.path.join(ROOT, "crawler", "xhs_data.db")

# ---------------------------------------------------------------- 安全参数
SAFE = {
    "min_interval": 10.0,     # 秒，实测阈值 1.5s×10 次，这里留 2 倍余量
    "jitter": 0.3,            # ±30%
    "session_max": 150,       # 单会话请求上限
    "session_rest": 900,      # 会话间休息 15 分钟
    "daily_max": 600,         # 每日请求上限
    "page_wait": 6.0,         # 页面加载后等待 SSR
    "quiet_start": 1,         # 凌晨 1 点后不跑
    "quiet_end": 7,           # 早 7 点前不跑
}

# 风控信号 → 命中即停
RISK_SIGNALS = (
    "website-login/error",
    "IP存在风险",
    "安全限制",
    "error_code=300012",
)

# ---------------------------------------------------------------- 工具
def now():
    return time.time()


def ts(t=None):
    return datetime.fromtimestamp(t or now(), CST).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now(CST).strftime("%Y-%m-%d")


def unwrap(v, depth=0):
    """拆 Vue3 ref / reactive 包装，返回裸值。"""
    if depth > 6:
        return v
    if isinstance(v, dict):
        for k in ("_rawValue", "_value", "value"):
            if k in v and len(v) <= 6:
                return unwrap(v[k], depth + 1)
        return {k: unwrap(x, depth + 1) for k, x in v.items()}
    if isinstance(v, list):
        return [unwrap(x, depth + 1) for x in v]
    return v


def clean(s, limit=None):
    """去代理对（Windows 控制台/JSON 都会炸）、压空白。"""
    if not isinstance(s, str):
        s = str(s) if s is not None else ""
    s = re.sub(r"[\ud800-\udfff]", "", s)
    s = " ".join(s.split())
    return s[:limit] if limit else s


def log(*a):
    print(f"[{datetime.now(CST).strftime('%H:%M:%S')}]", *a, flush=True)


# ---------------------------------------------------------------- 存储
SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id           TEXT PRIMARY KEY,
    title        TEXT,
    desc         TEXT,
    type         TEXT,
    user_id      TEXT,
    user_name    TEXT,
    liked        TEXT,
    collected    TEXT,
    comment_cnt  TEXT,
    share_cnt    TEXT,
    publish_time REAL,
    tags         TEXT,
    images       TEXT,
    xsec         TEXT,
    url          TEXT,
    detail       INT DEFAULT 0,   -- 0=只有卡片元数据 1=已抓详情
    feed_from    TEXT,
    fetched_at   REAL
);
CREATE TABLE IF NOT EXISTS users (
    id         TEXT PRIMARY KEY,
    nickname   TEXT,
    desc       TEXT,
    fans       TEXT,
    follows    TEXT,
    likes      TEXT,
    avatar     TEXT,
    fetched_at REAL
);
CREATE TABLE IF NOT EXISTS comments (
    id          TEXT PRIMARY KEY,
    note_id     TEXT,
    user_id     TEXT,
    user_name   TEXT,
    content     TEXT,
    like_count  TEXT,
    ip_location TEXT,
    create_time REAL,
    sub_count   INT,
    fetched_at  REAL
);
CREATE TABLE IF NOT EXISTS runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    day        TEXT,
    mode       TEXT,
    target     TEXT,
    req_count  INT,
    note_count INT,
    status     TEXT,
    started_at REAL,
    ended_at   REAL
);
CREATE INDEX IF NOT EXISTS idx_notes_detail ON notes(detail);
CREATE INDEX IF NOT EXISTS idx_comments_note ON comments(note_id);
"""


def db(path=DB_DEFAULT):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cx = sqlite3.connect(path)
    cx.row_factory = sqlite3.Row
    cx.executescript(SCHEMA)
    return cx


def save_note(cx, n, detail=False):
    cx.execute("""INSERT INTO notes(id,title,desc,type,user_id,user_name,liked,collected,
                  comment_cnt,share_cnt,publish_time,tags,images,xsec,url,detail,feed_from,fetched_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(id) DO UPDATE SET
                    title=COALESCE(excluded.title,title),
                    desc=COALESCE(NULLIF(excluded.desc,''),desc),
                    type=COALESCE(excluded.type,type),
                    user_id=COALESCE(excluded.user_id,user_id),
                    user_name=COALESCE(excluded.user_name,user_name),
                    liked=COALESCE(excluded.liked,liked),
                    collected=COALESCE(excluded.collected,collected),
                    comment_cnt=COALESCE(excluded.comment_cnt,comment_cnt),
                    share_cnt=COALESCE(excluded.share_cnt,share_cnt),
                    publish_time=COALESCE(excluded.publish_time,publish_time),
                    tags=COALESCE(NULLIF(excluded.tags,''),tags),
                    images=COALESCE(NULLIF(excluded.images,''),images),
                    xsec=COALESCE(excluded.xsec,xsec),
                    url=COALESCE(excluded.url,url),
                    detail=MAX(excluded.detail,detail),
                    fetched_at=excluded.fetched_at""",
                (n["id"], n.get("title"), n.get("desc"), n.get("type"),
                 n.get("user_id"), n.get("user_name"), n.get("liked"),
                 n.get("collected"), n.get("comment_cnt"), n.get("share_cnt"),
                 n.get("publish_time"), n.get("tags"), n.get("images"),
                 n.get("xsec"), n.get("url"), 1 if detail else 0,
                 n.get("feed_from"), now()))
    cx.commit()


def save_comment(cx, c):
    cx.execute("""INSERT INTO comments(id,note_id,user_id,user_name,content,like_count,
                  ip_location,create_time,sub_count,fetched_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(id) DO UPDATE SET
                    like_count=excluded.like_count, content=excluded.content,
                    fetched_at=excluded.fetched_at""",
               (c["id"], c["note_id"], c.get("user_id"), c.get("user_name"),
                c.get("content"), c.get("like_count"), c.get("ip_location"),
                c.get("create_time"), c.get("sub_count"), now()))
    cx.commit()


def save_user(cx, u):
    cx.execute("""INSERT INTO users(id,nickname,desc,fans,follows,likes,avatar,fetched_at)
                  VALUES(?,?,?,?,?,?,?,?)
                  ON CONFLICT(id) DO UPDATE SET
                    nickname=COALESCE(excluded.nickname,nickname),
                    desc=COALESCE(NULLIF(excluded.desc,''),desc),
                    fans=COALESCE(excluded.fans,fans),
                    follows=COALESCE(excluded.follows,follows),
                    likes=COALESCE(excluded.likes,likes),
                    avatar=COALESCE(excluded.avatar,avatar),
                    fetched_at=excluded.fetched_at""",
               (u["id"], u.get("nickname"), u.get("desc"), u.get("fans"),
                u.get("follows"), u.get("likes"), u.get("avatar"), now()))
    cx.commit()


# ---------------------------------------------------------------- 熔断
class Guard:
    """三道熔断：会话上限 / 每日上限 / 风控信号。"""

    def __init__(self, cx, session_max=SAFE["session_max"],
                 daily_max=SAFE["daily_max"], min_interval=SAFE["min_interval"]):
        self.cx = cx
        self.session_max = session_max
        self.daily_max = daily_max
        self.min_interval = min_interval
        self.session_count = 0
        self.total_count = 0
        self.last = 0.0
        self.started = now()
        self.tripped = None
        self.day_count = self._today_count()

    def _today_count(self):
        r = self.cx.execute("SELECT COALESCE(SUM(req_count),0) c FROM runs WHERE day=?",
                            (today(),)).fetchone()
        return r["c"] or 0

    def check_quiet(self):
        h = datetime.now(CST).hour
        if SAFE["quiet_start"] <= h < SAFE["quiet_end"]:
            raise SystemExit(
                f"现在是 {h} 点，处于静默时段（{SAFE['quiet_start']}-{SAFE['quiet_end']} 点）。"
                f"夜间高频访问是典型机器人特征，请白天运行。")

    def before(self):
        """每次请求前调用：限速 + 预算检查。"""
        if self.tripped:
            raise SystemExit(f"已熔断：{self.tripped}")
        if self.session_count >= self.session_max:
            log(f"本会话已达 {self.session_max} 请求上限，休息 "
                f"{SAFE['session_rest']//60} 分钟")
            time.sleep(SAFE["session_rest"])
            self.session_count = 0
        if self.day_count >= self.daily_max:
            raise SystemExit(
                f"今日已达 {self.daily_max} 请求上限。明天再跑，或调 --daily-max。")

        gap = time.time() - self.last
        wait = self.min_interval * (1 + random.uniform(-SAFE["jitter"], SAFE["jitter"]))
        if gap < wait:
            time.sleep(wait - gap)
        self.last = time.time()

    def after(self, page_state=None):
        self.session_count += 1
        self.total_count += 1
        self.day_count += 1
        if page_state:
            self.inspect(page_state)

    def inspect(self, st):
        """检查风控信号，命中立即熔断。"""
        blob = json.dumps(st, ensure_ascii=False) if isinstance(st, dict) else str(st)
        for sig in RISK_SIGNALS:
            if sig in blob:
                self.tripped = f"风控信号 `{sig}`"
                raise SystemExit(
                    f"\n{'!'*60}\n触发风控：{sig}\n"
                    f"已立即停机，共发出 {self.total_count} 请求。\n"
                    f"处理建议：\n"
                    f"  1. 立刻停止该账号所有操作，静置 24 小时\n"
                    f"  2. 用有头模式打开小红书，人工浏览 10 分钟确认是否正常\n"
                    f"  3. 恢复后把 --interval 调到 20s 以上\n"
                    f"{'!'*60}\n")


# ---------------------------------------------------------------- CDP
class Browser:
    def __init__(self, profile_dir, headed=False, proxy=None, port=None):
        # 必须绝对路径：Chrome 对 --user-data-dir 的相对路径解析不可靠
        self.profile = os.path.abspath(profile_dir)
        os.makedirs(self.profile, exist_ok=True)
        self.port = port or random.randint(9500, 9899)
        self.proc = None
        self.ws = None
        self.i = 0
        self._start(headed, proxy)

    @staticmethod
    def _bin():
        for p in CHROME_CANDIDATES:
            if os.path.exists(p):
                return p
        raise SystemExit("找不到 chrome.exe")

    def _start(self, headed, proxy):
        args = [
            self._bin(),
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile}",
            "--no-first-run", "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1440,900",
            "--lang=zh-CN",
        ]
        if not headed:
            args.append("--headless=new")
        if proxy:
            args.append(f"--proxy-server={proxy}")
        else:
            # 显式禁用代理继承，避免系统 v2rayN 污染出口
            args.append("--no-proxy-server")
        args.append("about:blank")

        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        ready = False
        for _ in range(120):
            if self.proc.poll() is not None:
                raise SystemExit(
                    f"Chrome 启动后立即退出（code={self.proc.returncode}）。\n"
                    f"常见原因：profile 目录被另一个 Chrome 实例占用，或路径含特殊字符。\n"
                    f"profile: {self.profile}")
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/json/version", timeout=1):
                    ready = True
                    break
            except Exception:
                time.sleep(0.25)
        if not ready:
            self.proc.terminate()
            raise SystemExit(f"Chrome 调试端口 {self.port} 30 秒未就绪。"
                             f"换个 --port 或检查杀软拦截。")

        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/json/list", timeout=3) as r:
            tabs = json.load(r)
        target = next(t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page")
        self.ws = ws.connect(target, max_size=128 * 1024 * 1024)
        self.call("Page.enable")
        self.call("Runtime.enable")

    def call(self, method, **params):
        self.i += 1
        mid = self.i
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv(timeout=90))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, expr, await_promise=True):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                      awaitPromise=await_promise, userGesture=True)
        res = r.get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError(res.get("description", "js error"))
        return res.get("value")

    def goto(self, url, wait=SAFE["page_wait"]):
        self.call("Page.navigate", url=url)
        time.sleep(wait)

    def close(self):
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()


# ---------------------------------------------------------------- 页面探测
PAGE_STATE = r"""(() => {
  const s = window.__INITIAL_STATE__;
  const out = {
    url: location.href.slice(0, 160),
    title: document.title,
    wall: location.href.indexOf('website-login/error') > -1,
    errcode: (location.href.match(/error_code=(\d+)/) || [])[1] || null,
    hasState: !!s,
    bodyHead: document.body.innerText.slice(0, 80)
  };
  const f = s && s.feed && s.feed.feeds;
  const a = f && (f._rawValue || f.value || f);
  out.feed = Array.isArray(a) ? a.length : -1;
  const n = s && s.note && s.note.noteDetailMap;
  const nv = n && (n._rawValue || n.value || n);
  out.detail = nv ? Object.keys(nv).filter(Boolean).length : 0;
  const u = s && s.user;
  out.userPage = !!(u && u.userPageData);
  const sr = s && s.search;
  out.searchFeed = sr && sr.feeds ? Object.keys(sr.feeds).length : 0;
  return out;
})()"""


def page_state(b):
    return b.eval(PAGE_STATE) or {}


# ---------------------------------------------------------------- 抽取
EXTRACT_FEED = r"""(() => {
  const s = window.__INITIAL_STATE__;
  if (!s || !s.feed) return [];
  const f = s.feed.feeds;
  const a = f && (f._rawValue || f.value || f);
  const arr = Array.isArray(a) ? a : [];
  return arr.map(x => {
    const nc = x.noteCard || {};
    const u = nc.user || {};
    const it = nc.interactInfo || {};
    const cv = nc.cover || {};
    const img = cv.urlDefault || cv.urlPre ||
      ((cv.infoList || [])[0] || {}).url || '';
    return {
      id: x.id, xsec: x.xsecToken || '',
      title: nc.displayTitle || '', type: nc.type || '',
      user_id: u.userId || '', user_name: u.nickname || u.nickName || '',
      user_xsec: u.xsecToken || '',
      liked: it.likedCount || '', cover: img
    };
  });
})()"""

EXTRACT_NOTE = r"""(() => {
  const s = window.__INITIAL_STATE__;
  if (!s || !s.note) return null;
  const raw = s.note.noteDetailMap;
  const v = raw && (raw._rawValue || raw.value || raw);
  if (!v) return null;
  const keys = Object.keys(v).filter(Boolean);
  if (!keys.length) return null;
  const box = v[keys[0]] || {};
  const n = box.note || {};
  const it = n.interactInfo || {};
  const u = n.user || {};
  const cm = box.comments;
  const cv = cm && (cm._rawValue || cm.value || cm);
  const list = (cv && (cv.list || cv)) || [];
  const arr = Array.isArray(list) ? list : Object.values(list || {});
  return {
    note: {
      id: n.noteId || keys[0],
      title: n.title || '', desc: n.desc || '', type: n.type || '',
      time: n.time || null,
      user_id: u.userId || '', user_name: u.nickname || u.nickName || '',
      liked: it.likedCount || '', collected: it.collectedCount || '',
      comment_cnt: it.commentCount || '', share_cnt: it.shareCount || '',
      tags: (n.tagList || []).map(t => t.name).filter(Boolean),
      images: (n.imageList || []).map(i => i.urlDefault || i.urlPre || '').filter(Boolean)
    },
    comments: arr.map(c => {
      const cu = c.userInfo || {};
      return {
        id: c.id || '', note_id: n.noteId || keys[0],
        user_id: cu.userId || '', user_name: cu.nickname || '',
        content: c.content || '', like_count: c.likeCount || '',
        ip_location: c.ipLocation || '', create_time: c.createTime || null,
        sub_count: c.subCommentCount || 0
      };
    }),
    hasMore: cv ? !!cv.hasMore : false
  };
})()"""

EXTRACT_USER = r"""(() => {
  const s = window.__INITIAL_STATE__;
  if (!s || !s.user) return null;
  const up = s.user.userPageData;
  const d = up && (up._rawValue || up.value || up);
  if (!d) return null;
  const bi = d.basicInfo || d;
  const inter = d.interactions;
  const iv = inter && (inter._rawValue || inter.value || inter);
  const arr = Array.isArray(iv) ? iv : Object.values(iv || {});
  const pick = t => { const x = arr.find(a => a && a.type === t); return x ? x.count : ''; };
  const nv = s.user.notes;
  const notes = nv && (nv._rawValue || nv.value || nv);
  const flat = [];
  if (notes && typeof notes === 'object') {
    Object.values(notes).forEach(group => {
      const g = group && (group._rawValue || group.value || group);
      if (!g || typeof g !== 'object') return;
      Object.values(g).forEach(x => {
        const it = x && (x._rawValue || x.value || x);
        if (it && it.id) flat.push({
          id: it.id, xsec: it.xsecToken || '',
          title: (it.noteCard && it.noteCard.displayTitle) || '',
          type: (it.noteCard && it.noteCard.type) || ''
        });
      });
    });
  }
  return {
    user: {
      id: bi.userId || '', nickname: bi.nickname || bi.nickName || '',
      desc: bi.desc || '', avatar: bi.image || bi.avatar || '',
      fans: pick('fans'), follows: pick('follows'), likes: pick('interaction')
    },
    notes: flat
  };
})()"""

EXTRACT_SEARCH = r"""(() => {
  const s = window.__INITIAL_STATE__;
  if (!s || !s.search) return [];
  const f = s.search.feeds;
  const a = f && (f._rawValue || f.value || f);
  const arr = Array.isArray(a) ? a : Object.values(a || {});
  return arr.map(x => {
    const it = x && (x._rawValue || x.value || x);
    if (!it || !it.id) return null;
    const nc = it.noteCard || {};
    const u = nc.user || {};
    const inf = nc.interactInfo || {};
    return {
      id: it.id, xsec: it.xsecToken || '',
      title: nc.displayTitle || '', type: nc.type || '',
      user_id: u.userId || '', user_name: u.nickname || u.nickName || '',
      user_xsec: u.xsecToken || '', liked: inf.likedCount || '', cover: ''
    };
  }).filter(Boolean);
})()"""


def login_state(b):
    """从页面 __INITIAL_STATE__ 读登录态。

    注意：不要用 /api/sns/web/v2/user/me 判断 —— 该接口需要 X-s 签名头，
    裸 fetch 会返回 406，看起来像"未登录"，实际是签名缺失。
    页面状态里的 user.loggedIn 才是准的。
    """
    return b.eval(r"""(() => {
      const s = window.__INITIAL_STATE__ || {};
      const g = v => (v && typeof v === 'object' && '_value' in v) ? v._value
                   : (v && typeof v === 'object' && '_rawValue' in v) ? v._rawValue : v;
      const u = s.user || {};
      const info = u.userInfo;
      const iv = info && (info._rawValue || info.value || info);
      return {
        loggedIn: !!g(u.loggedIn),
        activated: !!g(u.activated),
        nick: iv ? (iv.nickname || iv.nickName || '') : '',
        userId: iv ? (iv.userId || '') : '',
        redId: iv ? (iv.redId || '') : '',
        guest: iv ? iv.guest : null
      };
    })()""") or {}


def risk_probe(b):
    """探测账号当前能力边界：浏览 / 搜索 / 详情。

    300011 = 账号异常（可浏览，不可搜索）
    -104  = 无权限
    """
    return b.eval(r"""(async () => {
      const out = {};

      // 1. 搜索（最敏感）
      try {
        const api = '/api/sns/web/v1/search/notes';
        const payload = {keyword:"露营", page:1, page_size:20, search_id:"probe",
                         sort:"general", note_type:0, ext_flags:[],
                         image_formats:["jpg","webp","avif"]};
        const sig = window._webmsxyw(api, payload);
        const r = await fetch('https://edith.xiaohongshu.com'+api, {
          method:'POST', credentials:'include',
          headers:{'Content-Type':'application/json',
                   'X-s':sig['X-s'], 'X-t':String(sig['X-t'])},
          body: JSON.stringify(payload)});
        const j = await r.json();
        out.search = {code: j.code, msg: j.msg,
                      n: j.data && j.data.items && j.data.items.length};
      } catch(e) { out.search = {err: String(e)}; }

      // 2. 推荐流（页面已渲染的直接读）
      try {
        const s = window.__INITIAL_STATE__;
        const f = s && s.feed && s.feed.feeds;
        const a = f && (f._rawValue || f.value || f);
        out.feed = Array.isArray(a) ? a.length : -1;
      } catch(e) { out.feed = -1; }

      return out;
    })()""") or {}


def note_url(nid, xsec, src="pc_feed"):
    u = f"https://www.xiaohongshu.com/explore/{nid}"
    if xsec:
        from urllib.parse import quote
        u += f"?xsec_token={quote(xsec)}&xsec_source={src}"
    return u


def user_url(uid, xsec=None):
    u = f"https://www.xiaohongshu.com/user/profile/{uid}"
    if xsec:
        from urllib.parse import quote
        u += f"?xsec_token={quote(xsec)}&xsec_source=pc_feed"
    return u


# ---------------------------------------------------------------- 采集流程
def cmd_login(a):
    b = Browser(a.profile, headed=True, proxy=a.proxy)
    try:
        log("打开小红书登录页，请扫码或手机号登录（有 5 分钟）")
        b.goto("https://www.xiaohongshu.com/explore", 4)
        for i in range(60):
            time.sleep(5)
            lg = login_state(b)
            if lg.get("loggedIn") and not lg.get("guest"):
                log(f"登录成功：{clean(lg.get('nick'))}  (ID {lg.get('userId')})")
                # 立刻测账号能力边界
                rp = risk_probe(b)
                sr = rp.get("search") or {}
                log(f"推荐流：{rp.get('feed')} 条")
                if sr.get("code") == 0:
                    log(f"搜索接口：可用（{sr.get('n')} 条）")
                elif sr.get("code") == 300011:
                    log(f"⚠ 搜索接口：300011 账号异常 —— 可浏览，搜索被限")
                elif sr.get("code") == -104:
                    log(f"⚠ 搜索接口：-104 无权限")
                else:
                    log(f"搜索接口：code={sr.get('code')} {clean(sr.get('msg'))}")
                log(f"profile 已落盘：{b.profile}")
                return 0
            if i % 6 == 0:
                log(f"等待登录... {i*5}s  loggedIn={lg.get('loggedIn')}")
        log("超时未检测到登录态")
        return 1
    finally:
        b.close()


def cmd_check(a):
    b = Browser(a.profile, headed=a.headed, proxy=a.proxy)
    cx = db(a.db)
    try:
        b.goto("https://www.xiaohongshu.com/explore", 9)
        st = page_state(b)
        lg = login_state(b)
        rp = risk_probe(b)
        today_req = cx.execute("SELECT COALESCE(SUM(req_count),0) c FROM runs WHERE day=?",
                               (today(),)).fetchone()["c"]

        sr = rp.get("search") or {}
        caps = {
            "浏览推荐流": rp.get("feed", -1) > 0,
            "搜索": sr.get("code") == 0,
            "笔记详情": not st.get("wall"),
        }

        print(json.dumps({
            "登录": lg,
            "能力边界": caps,
            "搜索接口": sr,
            "页面": {"wall": st.get("wall"), "errcode": st.get("errcode"),
                     "feed": st.get("feed")},
            "配额": {"今日已用": today_req,
                     "今日剩余": max(0, SAFE["daily_max"] - today_req),
                     "单会话上限": SAFE["session_max"],
                     "间隔": f"{SAFE['min_interval']}s ±{int(SAFE['jitter']*100)}%"},
        }, ensure_ascii=False, indent=2))

        if not lg.get("loggedIn"):
            log("⚠ 未登录，只能抓公开内容")
            return 2
        if sr.get("code") == 300011:
            log("⚠ 账号被标记异常：推荐流/详情可用，搜索不可用")
            return 3
        return 0
    finally:
        b.close()
        cx.close()


def cmd_explore(a):
    cx = db(a.db)
    g = Guard(cx, a.session_max, a.daily_max, a.interval)
    g.check_quiet()
    b = Browser(a.profile, headed=a.headed, proxy=a.proxy)
    rid = cx.execute("INSERT INTO runs(day,mode,target,req_count,note_count,status,started_at)"
                     " VALUES(?,?,?,0,0,'running',?)",
                     (today(), "explore", a.channel or "homefeed_recommend", now())).lastrowid
    cx.commit()
    total = 0
    try:
        url = "https://www.xiaohongshu.com/explore"
        if a.channel:
            url += f"?channel_id={a.channel}"
        g.before()
        b.goto(url, 9)
        st = page_state(b)
        g.after(st)
        log(f"首屏 feed={st.get('feed')}")

        seen_ids = set()
        for p in range(a.pages):
            rows = b.eval(EXTRACT_FEED) or []
            new = 0
            for r in rows:
                if not r.get("id") or r["id"] in seen_ids:
                    continue
                seen_ids.add(r["id"])
                save_note(cx, {
                    "id": r["id"], "title": clean(r.get("title")),
                    "type": r.get("type"), "user_id": r.get("user_id"),
                    "user_name": clean(r.get("user_name")),
                    "liked": r.get("liked"), "xsec": r.get("xsec"),
                    "images": r.get("cover"), "url": note_url(r["id"], r.get("xsec")),
                    "feed_from": a.channel or "homefeed_recommend",
                }, detail=False)
                new += 1
            total += new
            log(f"第 {p+1}/{a.pages} 屏：新增 {new} 条，累计 {total}，feed={len(rows)}")

            if p + 1 < a.pages:
                g.before()
                b.eval("window.scrollTo(0, document.body.scrollHeight)", await_promise=False)
                time.sleep(random.uniform(3, 6))
                st = page_state(b)
                g.after(st)

        cx.execute("UPDATE runs SET req_count=?,note_count=?,status='done',ended_at=? WHERE id=?",
                   (g.total_count, total, now(), rid))
        cx.commit()
        log(f"完成：新增 {total} 条笔记元数据，请求 {g.total_count} 次")
        return 0
    except SystemExit:
        cx.execute("UPDATE runs SET req_count=?,note_count=?,status='tripped',ended_at=? WHERE id=?",
                   (g.total_count, total, now(), rid))
        cx.commit()
        raise
    finally:
        b.close()
        cx.close()


def cmd_note(a):
    ids = [x.strip() for x in (a.ids or "").split(",") if x.strip()]
    if not ids and a.from_db:
        cx0 = db(a.db)
        rows = cx0.execute("SELECT id,xsec FROM notes WHERE detail=0 "
                           "ORDER BY fetched_at DESC LIMIT ?", (a.limit,)).fetchall()
        cx0.close()
        pairs = [(r["id"], r["xsec"]) for r in rows]
    else:
        pairs = [(i, None) for i in ids]

    if not pairs:
        log("没有待抓的笔记")
        return 0

    cx = db(a.db)
    g = Guard(cx, a.session_max, a.daily_max, a.interval)
    g.check_quiet()
    b = Browser(a.profile, headed=a.headed, proxy=a.proxy)
    rid = cx.execute("INSERT INTO runs(day,mode,target,req_count,note_count,status,started_at)"
                     " VALUES(?,?,?,0,0,'running',?)",
                     (today(), "note", f"{len(pairs)} ids", now())).lastrowid
    cx.commit()
    done = 0
    try:
        for idx, (nid, xsec) in enumerate(pairs, 1):
            if not xsec:
                r = cx.execute("SELECT xsec FROM notes WHERE id=?", (nid,)).fetchone()
                xsec = r["xsec"] if r else None
            g.before()
            b.goto(note_url(nid, xsec), 7)
            st = page_state(b)
            g.after(st)

            data = b.eval(EXTRACT_NOTE)
            if not data or not data.get("note"):
                log(f"[{idx}/{len(pairs)}] {nid} 无数据 wall={st.get('wall')}")
                continue
            n = data["note"]
            save_note(cx, {
                "id": n["id"], "title": clean(n.get("title")),
                "desc": clean(n.get("desc")),
                "type": n.get("type"), "user_id": n.get("user_id"),
                "user_name": clean(n.get("user_name")),
                "liked": n.get("liked"), "collected": n.get("collected"),
                "comment_cnt": n.get("comment_cnt"), "share_cnt": n.get("share_cnt"),
                "publish_time": n.get("time"),
                "tags": json.dumps(n.get("tags") or [], ensure_ascii=False),
                "images": json.dumps(n.get("images") or [], ensure_ascii=False),
                "xsec": xsec, "url": note_url(n["id"], xsec),
            }, detail=True)
            for c in data.get("comments") or []:
                if c.get("id"):
                    c["content"] = clean(c.get("content"), 500)
                    c["user_name"] = clean(c.get("user_name"))
                    save_comment(cx, c)
            done += 1
            log(f"[{idx}/{len(pairs)}] {nid} 详情OK 评论{len(data.get('comments') or [])} "
                f"hasMore={data.get('hasMore')}")

        cx.execute("UPDATE runs SET req_count=?,note_count=?,status='done',ended_at=? WHERE id=?",
                   (g.total_count, done, now(), rid))
        cx.commit()
        log(f"完成：{done} 篇详情，请求 {g.total_count} 次")
        return 0
    except SystemExit:
        cx.execute("UPDATE runs SET req_count=?,note_count=?,status='tripped',ended_at=? WHERE id=?",
                   (g.total_count, done, now(), rid))
        cx.commit()
        raise
    finally:
        b.close()
        cx.close()


def cmd_user(a):
    ids = [x.strip() for x in (a.ids or "").split(",") if x.strip()]
    if not ids:
        log("需要 --ids 用户ID")
        return 1
    cx = db(a.db)
    g = Guard(cx, a.session_max, a.daily_max, a.interval)
    g.check_quiet()
    b = Browser(a.profile, headed=a.headed, proxy=a.proxy)
    total_notes = 0
    try:
        for idx, uid in enumerate(ids, 1):
            g.before()
            b.goto(user_url(uid, a.xsec), 8)
            st = page_state(b)
            g.after(st)
            data = b.eval(EXTRACT_USER)
            if not data or not data.get("user"):
                log(f"[{idx}/{len(ids)}] {uid} 无数据 wall={st.get('wall')}")
                continue
            u = data["user"]
            u["id"] = u.get("id") or uid
            u["nickname"] = clean(u.get("nickname"))
            u["desc"] = clean(u.get("desc"))
            save_user(cx, u)
            notes = data.get("notes") or []
            for n in notes:
                save_note(cx, {
                    "id": n["id"], "title": clean(n.get("title")),
                    "type": n.get("type"), "user_id": u["id"],
                    "user_name": u["nickname"], "xsec": n.get("xsec"),
                    "url": note_url(n["id"], n.get("xsec")),
                    "feed_from": f"user:{uid}",
                }, detail=False)
            total_notes += len(notes)
            log(f"[{idx}/{len(ids)}] {uid} {u['nickname']} 粉丝={u.get('fans')} "
                f"笔记={len(notes)}")
        log(f"完成：{total_notes} 条笔记元数据，请求 {g.total_count} 次")
        return 0
    finally:
        b.close()
        cx.close()


def cmd_search(a):
    if not a.kw:
        log("需要 --kw 关键词")
        return 1
    cx = db(a.db)
    g = Guard(cx, a.session_max, a.daily_max, a.interval)
    g.check_quiet()
    b = Browser(a.profile, headed=a.headed, proxy=a.proxy)
    from urllib.parse import quote
    total = 0
    try:
        for p in range(a.pages):
            g.before()
            url = (f"https://www.xiaohongshu.com/search_result?keyword={quote(a.kw)}"
                   f"&source=web_explore_feed&page={p+1}")
            b.goto(url, 9)
            st = page_state(b)
            g.after(st)
            if st.get("wall"):
                log(f"搜索被拦：{st.get('errcode')}")
                break
            rows = b.eval(EXTRACT_SEARCH) or []
            new = 0
            for r in rows:
                if not r.get("id"):
                    continue
                save_note(cx, {
                    "id": r["id"], "title": clean(r.get("title")),
                    "type": r.get("type"), "user_id": r.get("user_id"),
                    "user_name": clean(r.get("user_name")),
                    "liked": r.get("liked"), "xsec": r.get("xsec"),
                    "url": note_url(r["id"], r.get("xsec")),
                    "feed_from": f"search:{a.kw}",
                }, detail=False)
                new += 1
            total += new
            log(f"搜索第 {p+1}/{a.pages} 页：{new} 条，累计 {total}")
            if not rows:
                log("无结果，可能未登录或该词被限")
                break
        log(f"完成：{total} 条，请求 {g.total_count} 次")
        return 0
    finally:
        b.close()
        cx.close()


def cmd_stats(a):
    cx = db(a.db)
    n = cx.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    nd = cx.execute("SELECT COUNT(*) c FROM notes WHERE detail=1").fetchone()["c"]
    c = cx.execute("SELECT COUNT(*) c FROM comments").fetchone()["c"]
    u = cx.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    today_req = cx.execute("SELECT COALESCE(SUM(req_count),0) c FROM runs WHERE day=?",
                           (today(),)).fetchone()["c"]

    print(f"\n{'='*58}")
    print(f"  小红书采集进度")
    print(f"{'='*58}")
    print(f"  笔记总数      {n}")
    print(f"    ├ 已抓详情  {nd}")
    print(f"    └ 待抓详情  {n - nd}")
    print(f"  评论          {c}")
    print(f"  用户          {u}")
    print(f"  今日请求      {today_req} / {SAFE['daily_max']}")
    print(f"  数据库        {a.db}")

    rows = cx.execute("""SELECT feed_from, COUNT(*) c FROM notes
                         GROUP BY feed_from ORDER BY c DESC LIMIT 8""").fetchall()
    if rows:
        print(f"\n  来源分布：")
        for r in rows:
            print(f"    {str(r['feed_from'])[:40]:<42}{r['c']}")

    runs = cx.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 5").fetchall()
    if runs:
        print(f"\n  最近任务：")
        for r in runs:
            print(f"    {ts(r['started_at'])}  {r['mode']:<8} "
                  f"req={r['req_count']:<4} notes={r['note_count']:<4} {r['status']}")
    print()
    cx.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="小红书单账号保守采集器")
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--profile", default=os.path.join(ROOT, "profiles", "xhs_main"))
    ap.add_argument("--proxy", default=None, help="不填则强制直连（忽略系统代理）")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--interval", type=float, default=SAFE["min_interval"],
                    help=f"请求间隔秒，默认 {SAFE['min_interval']}")
    ap.add_argument("--session-max", type=int, default=SAFE["session_max"])
    ap.add_argument("--daily-max", type=int, default=SAFE["daily_max"])

    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("login")
    sub.add_parser("check")

    p = sub.add_parser("explore")
    p.add_argument("--pages", type=int, default=3)
    p.add_argument("--channel", default=None)

    p = sub.add_parser("note")
    p.add_argument("--ids", default="")
    p.add_argument("--from-db", action="store_true")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("user")
    p.add_argument("--ids", required=True)
    p.add_argument("--xsec", default=None)

    p = sub.add_parser("search")
    p.add_argument("--kw", required=True)
    p.add_argument("--pages", type=int, default=2)

    sub.add_parser("stats")

    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 1
    return {"login": cmd_login, "check": cmd_check, "explore": cmd_explore,
            "note": cmd_note, "user": cmd_user, "search": cmd_search,
            "stats": cmd_stats}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
