"""B11-追加：流程通用性验证——第二个交付形态（AI 提示词包，纯文本）走同一套就绪/导出。

在系统临时库建一单（标注 synthetic/自拟），对比七项就绪判定、缺项提示、导出字段与 C3 的差异，
输出 generality.json 与导出样例（b11/exports/）。
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

TMP = pathlib.Path(tempfile.mkdtemp(prefix="b11-generality-"))
os.environ["WORKBENCH_WORKFLOW_DB"] = str(TMP / "workflow.sqlite3")
os.environ["WORKBENCH_SECRET_FILE"] = str(TMP / "secret")
sys.path.insert(0, str(WORKBENCH))

import workflow as wf  # noqa: E402
import readiness as rd  # noqa: E402
import app as wb  # noqa: E402

NAME = "[SYNTHETIC 自拟] AI 提示词包｜会议纪要与周报 10 条模板（纯文本）"
PROMPTS = [
    "把 60 分钟会议记录压缩成 5 条结论 + 3 个待办（含负责人/截止日）。",
    "把散乱笔记改写成周报：本周完成 / 下周计划 / 风险与需要的支持。",
    "把客户反馈原话归并成 3 类主题，并给出每类可执行的改进项。",
    "把长文档提炼成 1 页摘要：3 个要点 + 1 个决策建议 + 风险。",
    "把需求描述改写成验收标准（Given/When/Then 格式）。",
    "把技术方案改写成给非技术同事看的说明（不超过 300 字）。",
    "从会议录音转写文本中提取决策、争议点与未决事项。",
    "把项目延期原因写成对外沟通话术（不甩锅、给方案）。",
    "把竞品功能列表整理成对比表（功能/是否支持/差异点）。",
    "把季度目标拆成本月可执行任务清单（含优先级与预计工时）。",
]
SELLING = "\n".join([
    "10 条可直接套用的提示词模板，覆盖会议纪要、周报、反馈归类、摘要、验收标准等高频场景。",
    "每条都写成「输入什么 → 输出什么」，替换方括号内容即可用。",
    "纯文本交付（.md/.txt），不需要任何软件或插件。",
    "不含代写服务、不承诺效果；输出质量取决于你给的材料。",
    "可自行复制到任意对话式 AI 工具中使用。",
])
INCLUDES = ("纯文本文件（.md 或 .txt）一份，含 10 条提示词模板与使用说明；"
            "每条含用途、输入示例、输出结构；不含任何第三方付费模板内容")
EXCLUDES = ("不含代写/代运营服务；不含账号/订阅；不含图片素材；不承诺效果或收益；"
            "不含特定平台专属玩法（可能随平台规则变化）")
FAQ = [
    {"q": "需要什么软件？", "a": "任意文本编辑器即可；使用时复制到你所用的对话式 AI 工具。"},
    {"q": "能在手机上用吗？", "a": "可以，纯文本无格式依赖。"},
    {"q": "会更新吗？", "a": "当前为一次性版本，不承诺更新。"},
    {"q": "能保证效果吗？", "a": "不能；输出质量取决于你提供的材料与所用模型。"},
    {"q": "可以商用吗？", "a": "自用/团队内使用可以；再分发或转售需另行确认。"},
    {"q": "怎么交付？", "a": "以文本文件交付（站内文件/网盘等方式以平台规则为准）。"},
]
DELIVERY = "交付：单个 .md/.txt 文件；不含账号/订阅；不代填不代写"
AFTERSALES = "不承诺更新与效果；售后范围/时限/退款政策未定，以平台规则为准；不含代运营"


def seed(conn: sqlite3.Connection, *, workorder_id: str, platform_evidence: str, submit_key: str) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    snapshot = {"item_id": "self:prompt-pack-v1", "title": NAME, "category": "self:prompt-pack-v1",
                "url": "self://prompt-pack-v1", "platform": "self", "source": "B11 自拟", "raw_ref": "b11"}
    conn.execute(
        """INSERT INTO workorder (workorder_id, submit_key, payload_hash, source_group, source_item_id,
             source_url, source_platform, snapshot_json, name, use_case, target_buyer, deliverable, fmt,
             language, version, includes, excludes, target_platform, status, selected_supply_id, revision,
             created_at, updated_at, supply_license_commercial, supply_license_redistribute,
             supply_license_resell, supply_version, sample_status, sample_ref, cost_minor, cost_known,
             platform_evidence, copy_status, copy_version, selling_points, price_minor, delivery_note,
             aftersales_note, faq_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                   'yes','yes','yes','pp-v1','verified',?,300,'yes',?,'final','pp-v1-copy',?,1990,?,?,?)""",
        (workorder_id, submit_key, hashlib.sha256(submit_key.encode()).hexdigest(),
         "self:prompt-pack-v1", "self:prompt-pack-v1", "self://prompt-pack-v1", "self",
         json.dumps(snapshot, ensure_ascii=False), NAME, "会议纪要与周报提示词", "职场人 / 小团队",
         "纯文本 .md 文件（10 条提示词模板）", "md", "中文", "v1", INCLUDES, EXCLUDES, "xianyu",
         "pending_supply", "self:prompt-pack-v1", 1, now, now,
         "自拟草稿（未实机跑过；非真实平台核验）", platform_evidence,
         SELLING, DELIVERY, AFTERSALES, json.dumps(FAQ, ensure_ascii=False)))
    conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                 (workorder_id, "seed", "B11 通用性验证（自拟提示词包）", now))
    conn.commit()


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    out: dict = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cases": {}}
    conn = wf.connect()
    try:
        wf.init_schema(conn)
        seed(conn, workorder_id="wo:pp-blocked", platform_evidence="", submit_key="b11-pp-blocked")
        seed(conn, workorder_id="wo:pp-synthetic", platform_evidence="synthetic-demo://xianyu/text-digital",
             submit_key="b11-pp-synthetic")
    finally:
        conn.close()

    app = wb.create_app()
    app.testing = True
    client = app.test_client()

    def rec(wid: str) -> dict:
        c = wf.connect()
        try:
            return wf.get(c, wid)
        finally:
            c.close()

    for wid, label in (("wo:pp-blocked", "blocked"), ("wo:pp-synthetic", "synthetic")):
        record = rec(wid)
        ready = rd.readiness(record)
        detail = client.get(f"/worksheet/{wid}").get_data(as_text=True)
        entry = {"ready": ready["overall_ready"], "checks": [
            {"key": c["key"], "ok": c["ok"], "blocker": c["blocker"]} for c in ready["checks"]],
            "ok_chips": detail.count('chip chip-ok">通过'),
            "warn_chips": detail.count('chip chip-warn">未通过')}
        if ready["overall_ready"]:
            md = client.get(f"/worksheet/{wid}/export?format=md")
            jsx = client.get(f"/worksheet/{wid}/export?format=json")
            entry.update({"md_status": md.status_code, "json_status": jsx.status_code})
            (EXPORTS / "prompt_pack_synthetic.md").write_bytes(md.data)
            (EXPORTS / "prompt_pack_synthetic.json").write_bytes(jsx.data)
            payload = json.loads(jsx.get_data(as_text=True))
            entry["buyer_fields"] = list(payload["buyer_visible_fields"])
            entry["faq_count"] = len(payload["faq"])
            entry["selling_points"] = len(payload["selling_points"])
            entry["format_block"] = payload["format"]
        else:
            exp = client.get(f"/worksheet/{wid}/export?format=md")
            entry["export_status"] = exp.status_code
            entry["export_body_has_platform_blocker"] = "缺少目标平台条件证据" in exp.get_data(as_text=True)
            (EXPORTS / "prompt_pack_blocked.txt").write_bytes(exp.data)
        out["cases"][label] = entry

    # 与 C3 的通用性对比（字段层面）
    out["generic_compare"] = {
        "七项检查键一致": ["specs", "supply", "license", "sample", "cost", "platform", "copy"],
        "C3（Excel）表现": "6 通过 / 1 未通过（platform）",
        "提示词包（纯文本）表现": "6 通过 / 1 未通过（platform）；补 synthetic 后 7/7",
        "导出买家字段": ["title", "selling_points", "contents", "format", "price", "delivery", "aftersales", "faq"],
        "品类相关（需人工）": ["fmt/version 的取值含义（xlsx vs md）", "sample_ref 的核验方式（真实 Excel 打开 vs 文本通读）",
                              "平台类目与虚拟交付规则", "定价档位（按品类客单价）"],
        "流程通用（系统保证）": ["七项就绪判定与缺项文案", "买家字段白名单与内部标记扫描",
                                  "版本戳与失效判定", "GET 零写 / POST 记录导出", "CSRF 与同源写保护"],
    }
    conn = wf.connect()
    try:
        out["db_rows"] = {"workorder": conn.execute("SELECT COUNT(*) FROM workorder").fetchone()[0]}
    finally:
        conn.close()
    out["db_sha256"] = hashlib.sha256((TMP / "workflow.sqlite3").read_bytes()).hexdigest()
    (B11 / "generality.json").write_bytes(json.dumps(out, ensure_ascii=False, indent=1).encode())
    if (TMP / "secret").exists():
        (TMP / "secret").unlink()
    print(json.dumps({"blocked": out["cases"]["blocked"], "synthetic": out["cases"]["synthetic"]},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
