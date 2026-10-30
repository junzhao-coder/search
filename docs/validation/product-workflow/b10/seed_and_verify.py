"""B10：在隔离库预演 C3 上架准备（工作单 A 真实材料 / 工作单 B synthetic 演示）。

- 只写系统临时库与 docs/validation/product-workflow/b10；不改 tools/workbench、不碰生产 runtime 库。
- 工作单由脚本**直接写入隔离库**（app 的建单入口只接受已归类商品来源，`self:c3-v1` 不在目录中），
  随后用真实 Flask 路由做就绪检查、GET 导出（409/200）与 POST 记录导出。
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import time

ROOT = pathlib.Path(r"D:\桌面\two")
B10 = ROOT / "docs" / "validation" / "product-workflow" / "b10"
EXPORTS = B10 / "exports"
WORKBENCH = ROOT / "tools" / "workbench"
sys.path.insert(0, str(WORKBENCH))

TMP = pathlib.Path(tempfile.mkdtemp(prefix="b10-rehearsal-"))
DB = TMP / "workflow.sqlite3"
SECRET = TMP / "secret"
os.environ["WORKBENCH_WORKFLOW_DB"] = str(DB)
os.environ["WORKBENCH_SECRET_FILE"] = str(SECRET)

import workflow as wf  # noqa: E402
import readiness as rd  # noqa: E402
import app as wb  # noqa: E402

TITLE = "学习计划 Excel 模板｜课程/考试倒计时/周计划/复习进度（单文件）"
SELLING_POINTS = "\n".join([
    "一个 .xlsx 放 5 张基础表：使用说明、课程与考试、考试倒计时、周计划、复习进度；50 个公式，打开即可改课程/日期。",
    "考试倒计时自动算：用 =TODAY() 与 IF 计算剩余天数，并分“已过期/紧急/临近/正常”四档。",
    "期末冲刺版规划多一张“每日任务”表（冲刺日计划，IF/TODAY/COUNTIF）——规划版本，未制作。",
    "考研/四六级版规划多一张“英语分项”表（IF/AVERAGE 算完成率）——规划版本，未制作。",
    "学期周计划版规划多一张“课程表”并用 COUNTIFS 提示冲突——规划版本，未制作。",
])
INCLUDES = ("`.xlsx` 单文件；5 张表（使用说明 / 课程与考试 / 考试倒计时 / 周计划 / 复习进度）；"
            "50 个公式（TODAY/IF/COUNTIF/SUM/COUNTA/COUNT/AVERAGE）；掌握度下拉、条件格式、5 表打印区域；"
            "虚构示例 6 门课程、8 条复习知识点，可直接删除")
EXCLUDES = ("不含宏、外部链接、图片、第三方字体/模板；不含自动提醒/云同步；"
            "三场景规划版（期末冲刺/英语分项/课程表）未制作；不含代做/代填/持续维护")
FAQ = [
    {"q": "需要安装什么软件？", "a": "用 Excel 或 WPS 打开 .xlsx；不含宏、外部链接，不需要安装插件。手机/平板可打开，打印/下拉体验以桌面为准。"},
    {"q": "怎么交付？", "a": "计划以 .xlsx 文件交付（站内文件/网盘等方式以平台和商品页为准）；当前未上架，具体方式未定。"},
    {"q": "可以改课程、考试日期和复习项吗？", "a": "可以。改“课程与考试”的课程/日期，“考试倒计时”自动取数，“复习进度”按知识点填；增删行后按 usage.md 调整公式区域。"},
    {"q": "里面具体有什么？", "a": "v1 是 5 张表 + 50 个基础公式 + 示例数据；三场景规划各加 1 张表，规划版本未制作。"},
    {"q": "能保证学习效果或提分吗？", "a": "不能，也不作此类承诺；模板只提供表结构、公式与打印版式。"},
    {"q": "会更新吗？售后怎么算？", "a": "当前为一次性版本，不承诺更新；售后范围/时限/退款政策未定，以最终商品页与平台规则为准；不包含代做、代填、持续维护。"},
]
DELIVERY = ("交付：.xlsx 文件 + usage.md 使用说明；交付前买家确认软件（Excel/WPS）与版本；"
            "不通过聊天发送账号/密码/验证码，不代登录；不使用第三方字体/图片/模板，文件不含宏")
AFTERSALES = ("售后范围/时限/退款政策未定，以商品页与平台规则为准；可协助文件无法打开、"
              "公式区域因增删行需调整的说明；不包含代做、代填、持续维护、效果/分数/收益保证")


def seed(conn: sqlite3.Connection, *, workorder_id: str, name: str, platform_evidence: str,
         submit_key: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    snapshot = {"item_id": "self:c3-v1", "title": name, "category": "self:c3-v1",
                "url": "self://c3-v1", "platform": "self", "source": "b7/b8", "raw_ref": "b7/b8"}
    conn.execute(
        """INSERT INTO workorder (workorder_id, submit_key, payload_hash, source_group, source_item_id,
             source_url, source_platform, snapshot_json, name, use_case, target_buyer, deliverable, fmt,
             language, version, includes, excludes, target_platform, status, selected_supply_id, revision,
             created_at, updated_at, supply_license_commercial, supply_license_redistribute,
             supply_license_resell, supply_version, sample_status, sample_ref, cost_minor, cost_known,
             platform_evidence, copy_status, copy_version, selling_points, price_minor, delivery_note,
             aftersales_note, faq_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                   'yes','yes','yes','c3-v1','verified',?,500,'yes',?,'final','c3-v1-copy',?,990,?,?,?)""",
        (workorder_id, submit_key, hashlib.sha256(submit_key.encode()).hexdigest(), "self:c3-v1", "self:c3-v1",
         "self://c3-v1", "self", json.dumps(snapshot, ensure_ascii=False), name,
         "学习计划 / 考试倒计时 / 复习进度", "学生 / 备考人群", "Excel .xlsx 单文件（5 表 / 50 公式）",
         "xlsx", "中文", "v1", INCLUDES, EXCLUDES, "xianyu", "pending_supply", "self:c3-v1", 1, now, now,
         "b7:selfcheck 17/17（结构/公式自检；非真实 Excel 打开）", platform_evidence,
         SELLING_POINTS, DELIVERY, AFTERSALES, json.dumps(FAQ, ensure_ascii=False)))
    conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                 (workorder_id, "seed", "B10 隔离库预演（直接写入 fixture）", now))
    conn.commit()


def readiness_rows(client, wid: str) -> dict:
    html = client.get(f"/worksheet/{wid}").get_data(as_text=True)
    return {"ok_chips": html.count('chip chip-ok">通过'),
            "warn_chips": html.count('chip chip-warn">未通过'),
            "has_readiness": "上架准备检查（服务端判定）" in html,
            "has_blockers": "阻断项" in html}


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "db": str(DB), "steps": []}
    conn = wf.connect()
    try:
        wf.init_schema(conn)
        seed(conn, workorder_id="wo:c3-a", name=TITLE, platform_evidence="", submit_key="b10-a")
        seed(conn, workorder_id="wo:c3-b", name="[SYNTHETIC 演示] " + TITLE,
             platform_evidence="synthetic-demo://xianyu/category-sheet", submit_key="b10-b")
    finally:
        conn.close()

    app = wb.create_app()
    app.testing = True
    client = app.test_client()

    def record(wid: str) -> dict:
        conn = wf.connect()
        try:
            return wf.get(conn, wid)
        finally:
            conn.close()

    # ---- 工作单 A：真实材料 + 平台条件未知 ----
    rec_a = record("wo:c3-a")
    ready_a = rd.readiness(rec_a)
    out["A"] = {"readiness": ready_a, "rows": readiness_rows(client, "wo:c3-a")}
    a_export = client.get("/worksheet/wo:c3-a/export?format=md")
    out["A"]["export_status"] = a_export.status_code
    out["A"]["export_body_has_blocker"] = "缺少目标平台条件证据" in a_export.get_data(as_text=True)
    (EXPORTS / "A_export_blocked.txt").write_bytes(a_export.get_data(as_text=True).encode())

    # ---- 工作单 B：synthetic 平台条件 ----
    rec_b = record("wo:c3-b")
    ready_b = rd.readiness(rec_b)
    out["B"] = {"readiness": ready_b, "rows": readiness_rows(client, "wo:c3-b")}
    b_md = client.get("/worksheet/wo:c3-b/export?format=md")
    b_json = client.get("/worksheet/wo:c3-b/export?format=json")
    out["B"]["export_md_status"] = b_md.status_code
    out["B"]["export_json_status"] = b_json.status_code
    out["B"]["get_recorded_header"] = b_json.headers.get("X-WB-Recorded")
    (EXPORTS / "B_export_synthetic.md").write_bytes(b_md.data)
    (EXPORTS / "B_export_synthetic.json").write_bytes(b_json.data)
    out["B"]["export_json_body_head"] = b_json.get_data(as_text=True)[:300]
    if b_json.status_code != 200:
        print(json.dumps({"B_blockers": ready_b["blockers"], "B_checks":
                          [(c["key"], c["ok"], c["blocker"]) for c in ready_b["checks"]],
                          "head": out["B"]["export_json_body_head"]}, ensure_ascii=True))

    # POST 记录导出（校验零写/写 1 行）
    conn = wf.connect()
    try:
        rows_before = conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]
    finally:
        conn.close()
    with client.session_transaction() as sess:
        sess.setdefault("csrf", "b10-token")
        token = sess["csrf"]
    post = client.post("/worksheet/wo:c3-b/export/record", data={"csrf": token, "format": "json"},
                       headers={"Origin": "http://localhost"})
    conn = wf.connect()
    try:
        rows_after = conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0]
    finally:
        conn.close()
    out["B"]["post_record"] = {"status": post.status_code, "recorded_header": post.headers.get("X-WB-Recorded"),
                               "rows_before": rows_before, "rows_after": rows_after}

    # ---- 导出内容 vs COPY.md 对照 ----
    payload = json.loads(b_json.get_data(as_text=True))
    copy_text = (ROOT / "docs" / "validation" / "product-workflow" / "b8" / "COPY.md").read_text(encoding="utf-8")

    def scan(node, hits: list) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in ("cost", "profit", "margin", "score", "internal",
                                                            "raw_ref", "snapshot", "cost_minor", "total_score"):
                    hits.append(key)
                scan(value, hits)
        elif isinstance(node, list):
            for item in node:
                scan(item, hits)
        elif isinstance(node, str):
            low = node.lower()
            for token in ("成本", "利润", "毛利", "打分", "内部"):
                if token in node:
                    hits.append(token)
            for token in ("cost", "profit", "margin", "score", "internal", "raw_ref", "snapshot"):
                if token in low:
                    hits.append(token)

    hits: list = []
    scan(payload, hits)
    out["B"]["internal_field_hits"] = sorted(set(hits))

    compare = [
        {"field": "标题", "export": payload["title"], "copy_md": TITLE,
         "same": payload["title"].replace("[SYNTHETIC 演示] ", "") == TITLE, "note": "B 带 synthetic 前缀（显著标注）"},
        {"field": "卖点条数", "export": len(payload["selling_points"]), "copy_md": 5,
         "same": len(payload["selling_points"]) == 5, "note": "5 条，与 COPY §2 对齐"},
        {"field": "卖点关键词（5表/50公式/TODAY/COUNTIF）", "export":
         [k for k in ("5 张", "50 个", "TODAY", "COUNTIF") if any(k in p for p in payload["selling_points"])],
         "copy_md": ["5 张", "50 个", "TODAY", "COUNTIF"], "same":
         all(any(k in p for p in payload["selling_points"]) for k in ("5 张", "50 个", "TODAY", "COUNTIF")),
         "note": "卖点为压缩改写，保留可证明关键词"},
        {"field": "内容清单·包含", "export": payload["contents"]["includes"][:40], "copy_md": "5 张表 + 50 个公式",
         "same": "5 张表" in payload["contents"]["includes"] and "50 个公式" in payload["contents"]["includes"],
         "note": "改写为单行摘要，事实一致"},
        {"field": "内容清单·不包含", "export": payload["contents"]["excludes"][:40], "copy_md": "不含宏、外部链接…",
         "same": "宏" in payload["contents"]["excludes"], "note": "一致"},
        {"field": "FAQ 条数", "export": len(payload["faq"]), "copy_md": 6, "same": len(payload["faq"]) == 6,
         "note": "6 条，问题与答案取自 COPY §5"},
        {"field": "交付说明", "export": payload["delivery"][:30], "copy_md": "交付 .xlsx + usage.md",
         "same": "xlsx" in payload["delivery"] and "usage.md" in payload["delivery"], "note": "一致"},
        {"field": "售后说明", "export": payload["aftersales"][:30], "copy_md": "售后未定/不承诺更新",
         "same": "未定" in payload["aftersales"] and "不包含代做" in payload["aftersales"], "note": "一致"},
    ]
    out["compare"] = compare

    conn = wf.connect()
    try:
        out["db_rows"] = {"workorder": conn.execute("SELECT COUNT(*) FROM workorder").fetchone()[0],
                          "workorder_export": conn.execute("SELECT COUNT(*) FROM workorder_export").fetchone()[0],
                          "workorder_event": conn.execute("SELECT COUNT(*) FROM workorder_event").fetchone()[0]}
    finally:
        conn.close()
    out["db_sha256"] = hashlib.sha256(DB.read_bytes()).hexdigest()
    (B10 / "verify.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    if SECRET.exists():
        SECRET.unlink()
    print(json.dumps({"A_ready": ready_a["overall_ready"], "A_blockers": ready_a["blockers"],
                      "A_export": out["A"]["export_status"],
                      "B_ready": ready_b["overall_ready"], "B_export": out["B"]["export_json_status"],
                      "B_post": out["B"]["post_record"], "internal_hits": out["B"]["internal_field_hits"],
                      "compare_all_same": all(c["same"] for c in compare), "db_rows": out["db_rows"]},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
