"""B11：在生产工作单库建 C3 一单（g5）并产出 synthetic 导出样例。

- 生产库 `tools/workbench/runtime/workflow.sqlite3`：不存在时按 `workflow.init_schema()` 建（不改结构），
  直接 INSERT 一条 `source=self:c3-v1` 的工作单（app 建单入口只接受已归类商品来源），
  字段语义完全复用 workflow.py 的 schema；platform_evidence **留空**（刻意呈现“只差平台条件”）。
- synthetic 导出：在系统临时库建同规格但带 synthetic 平台证据的另一单，走真实路由 GET/POST 导出，
  产物写入 b11/exports/（仅演示结构，不代表真实平台许可）。
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
B11 = ROOT / "docs" / "validation" / "product-workflow" / "b11"
EXPORTS = B11 / "exports"
WORKBENCH = ROOT / "tools" / "workbench"
PROD_DB = WORKBENCH / "runtime" / "workflow.sqlite3"

TITLE = "学习计划 Excel 模板｜课程/考试倒计时/周计划/复习进度（单文件）"
SELLING = "\n".join([
    "一个 .xlsx 放 5 张基础表：使用说明、课程与考试、考试倒计时、周计划、复习进度；50 个公式，打开即可改课程/日期。",
    "考试倒计时自动算：用 =TODAY() 与 IF 算剩余天数，并分“已过期/紧急/临近/正常”四档。",
    "复习进度按知识点记录，掌握度下拉 + 条件格式，一眼看出薄弱项。",
    "周计划按周排任务并可直接打印（A4 纵向、1 页宽）。",
    "示例数据为虚构占位（6 门课程、8 条复习知识点），可直接删除改成自己的。",
])
INCLUDES = ("`.xlsx` 单文件；5 张表（使用说明 / 课程与考试 / 考试倒计时 / 周计划 / 复习进度）；"
            "50 个公式（TODAY/IF/COUNTIF/SUM/COUNTA/COUNT/AVERAGE）；掌握度下拉、条件格式、5 表打印区域；"
            "虚构示例 6 门课程、8 条复习知识点")
EXCLUDES = ("不含宏、外部链接、图片、第三方字体/模板；不含自动提醒/云同步；"
            "三场景规划版（期末冲刺/英语分项/课程表）未制作；不含代做/代填/持续维护")
FAQ = [
    {"q": "需要安装什么软件？", "a": "用 Excel 或 WPS 打开 .xlsx；不含宏、外部链接，不需要安装插件。手机/平板可打开，打印/下拉体验以桌面为准。"},
    {"q": "怎么交付？", "a": "计划以 .xlsx 文件 + usage.md 说明交付（站内文件/网盘等方式以平台和商品页为准）；当前未上架，具体方式未定。"},
    {"q": "可以改课程、考试日期和复习项吗？", "a": "可以。改“课程与考试”的课程/日期，“考试倒计时”自动取数，“复习进度”按知识点填；增删行后按 usage.md 调整公式区域。"},
    {"q": "里面具体有什么？", "a": "v1 是 5 张表 + 50 个基础公式 + 示例数据；三场景规划各加 1 张表，规划版本未制作。"},
    {"q": "能保证学习效果或提分吗？", "a": "不能，也不作此类承诺；模板只提供表结构、公式与打印版式。"},
    {"q": "会更新吗？售后怎么算？", "a": "当前为一次性版本，不承诺更新；售后范围/时限/退款政策未定，以最终商品页与平台规则为准；不包含代做、代填、持续维护。"},
]
DELIVERY = ("交付：.xlsx 文件 + usage.md 使用说明；交付前买家确认软件（Excel/WPS）与版本；"
            "不通过聊天发送账号/密码/验证码，不代登录；不使用第三方字体/图片/模板，文件不含宏")
AFTERSALES = ("售后范围/时限/退款政策未定，以商品页与平台规则为准；可协助文件无法打开、"
              "公式区域因增删行需调整的说明；不包含代做、代填、持续维护、效果/分数/收益保证")


def seed(conn: sqlite3.Connection, *, workorder_id: str, name: str, submit_key: str,
         platform_evidence: str) -> None:
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
         SELLING, DELIVERY, AFTERSALES, json.dumps(FAQ, ensure_ascii=False)))
    conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                 (workorder_id, "seed", "B11 五阶段走查（直接写入，字段语义同 workflow.py）", now))
    conn.commit()


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    WORKBENCH.joinpath("runtime").mkdir(parents=True, exist_ok=True)
    existed = PROD_DB.exists()
    os.environ["WORKBENCH_WORKFLOW_DB"] = str(PROD_DB)
    os.environ["WORKBENCH_SECRET_FILE"] = str(WORKBENCH / "runtime" / "secret_key")
    sys.path.insert(0, str(WORKBENCH))
    import workflow as wf
    import readiness as rd
    import app as wb

    conn = wf.connect()
    try:
        wf.init_schema(conn)
        wid = "wo:c3-prod-" + time.strftime("%Y%m%d")
        if conn.execute("SELECT 1 FROM workorder WHERE workorder_id=?", (wid,)).fetchone():
            conn.execute("DELETE FROM workorder WHERE workorder_id=?", (wid,))
        seed(conn, workorder_id=wid, name=TITLE, submit_key="b11-prod-" + wid, platform_evidence="")
        out["production"] = {"db": str(PROD_DB), "db_existed_before": existed, "workorder_id": wid,
                             "workorders": conn.execute("SELECT COUNT(*) FROM workorder").fetchone()[0]}
    finally:
        conn.close()

    # 生产单：真实路由核对（就绪 6/7、导出 409）
    app = wb.create_app()
    app.testing = True
    client = app.test_client()
    page = client.get("/worksheet").get_data(as_text=True)
    detail = client.get(f"/worksheet/{wid}").get_data(as_text=True)
    export = client.get(f"/worksheet/{wid}/export?format=md")
    rec = None
    conn = wf.connect()
    try:
        rec = wf.get(conn, wid)
    finally:
        conn.close()
    ready = rd.readiness(rec)
    out["production"].update({
        "list_contains": wid in page,
        "detail_ok_chips": detail.count('chip chip-ok">通过'),
        "detail_warn_chips": detail.count('chip chip-warn">未通过'),
        "ready": ready["overall_ready"],
        "blockers": ready["blockers"],
        "export_status": export.status_code,
    })
    (EXPORTS / "production_export_blocked.txt").write_bytes(export.data)

    # synthetic 导出样例（临时库）
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="b11-synth-"))
    os.environ["WORKBENCH_WORKFLOW_DB"] = str(tmp / "workflow.sqlite3")
    os.environ["WORKBENCH_SECRET_FILE"] = str(tmp / "secret")
    conn = wf.connect()
    try:
        wf.init_schema(conn)
        seed(conn, workorder_id="wo:c3-synthetic", name="[SYNTHETIC 演示] " + TITLE,
             submit_key="b11-synth", platform_evidence="synthetic-demo://xianyu/category-sheet")
    finally:
        conn.close()
    app2 = wb.create_app()
    app2.testing = True
    c2 = app2.test_client()
    md = c2.get("/worksheet/wo:c3-synthetic/export?format=md")
    jsx = c2.get("/worksheet/wo:c3-synthetic/export?format=json")
    (EXPORTS / "listing_synthetic.md").write_bytes(md.data)
    (EXPORTS / "listing_synthetic.json").write_bytes(jsx.data)
    with c2.session_transaction() as sess:
        sess.setdefault("csrf", "b11-token")
        token = sess["csrf"]
    post = c2.post("/worksheet/wo:c3-synthetic/export/record", data={"csrf": token, "format": "md"},
                   headers={"Origin": "http://localhost"})
    payload = json.loads(jsx.get_data(as_text=True))
    hits: list = []

    def scan(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in ("cost", "profit", "margin", "score", "internal",
                                                            "raw_ref", "snapshot", "cost_minor", "total_score"):
                    hits.append(key)
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)
        elif isinstance(node, str):
            for token_ in ("成本", "利润", "毛利", "打分", "内部", "cost", "profit", "margin", "score",
                           "internal", "raw_ref", "snapshot"):
                if token_ in node:
                    hits.append(token_)

    scan(payload)
    out["synthetic"] = {"md_status": md.status_code, "json_status": jsx.status_code,
                        "post_status": post.status_code, "recorded_header": post.headers.get("X-WB-Recorded"),
                        "internal_hits": sorted(set(hits)), "faq_count": len(payload["faq"]),
                        "selling_points": len(payload["selling_points"])}
    if (tmp / "secret").exists():
        (tmp / "secret").unlink()
    out["db_sha256_prod"] = hashlib.sha256(PROD_DB.read_bytes()).hexdigest()
    (B11 / "production_verify.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    print(json.dumps(out, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
