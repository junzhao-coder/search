"""S2-C executable JS behaviour checks (Node vm harness; no browser, no new dependencies)."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HARNESS = pathlib.Path(__file__).resolve().parent / "ui_behavior.mjs"
UI_JS = ROOT / "app" / "static" / "ui.js"
TEMPLATES = ROOT / "app" / "templates"
TMP_ROOT = pathlib.Path(__file__).resolve().parent / "_tmp"
ARTIFACT = TMP_ROOT / "feedback_payloads.json"

REFUND_CSV = (
    "title,data_origin,sale_price,demand_source,demand_url,demand_excerpt\n"
    "示例-退款链路,synthetic,9.90,xianyu,https://example.com/demand/ui-refund,求模板\n"
)


def _run_harness() -> str:
    node = shutil.which("node") or os.environ.get("NODE_BIN")
    if node is None:
        raise unittest.SkipTest("未找到 node：JS 行为验证需要 Node.js 运行时")
    proc = subprocess.run(
        [node, str(HARNESS)], cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=300
    )
    return (proc.stdout or "") + (proc.stderr or ""), proc.returncode


class UiBehaviourTest(unittest.TestCase):
    def test_node_behaviour_harness_passes(self):
        output, returncode = _run_harness()
        self.assertEqual(returncode, 0, output)
        self.assertIn("0 failed", output)
        self.assertIn("PASS import", output)
        self.assertIn("PASS home", output)
        self.assertIn("PASS feedback", output)

    def test_every_element_id_used_by_js_exists_in_templates(self):
        script = UI_JS.read_text(encoding="utf-8")
        used = set(re.findall(r'qs\("([a-z0-9-]+)"\)', script))
        self.assertTrue(used, "ui.js 应通过 qs() 引用模板元素")
        html = "\n".join(path.read_text(encoding="utf-8") for path in TEMPLATES.glob("*.html"))
        missing = sorted(element_id for element_id in used if f'id="{element_id}"' not in html)
        self.assertEqual(missing, [], f"模板缺少 JS 依赖的元素 id：{missing}")


class CapturedFeedbackPayloadTest(unittest.TestCase):
    """把 JS 实际组装的载荷交给真实 Flask 端点：201 通过 + 旧形状 422 反证。"""

    def test_js_refund_payload_is_accepted_by_real_endpoint(self):
        output, returncode = _run_harness()
        self.assertEqual(returncode, 0, output)
        self.assertTrue(ARTIFACT.exists(), "行为验证应产出捕获载荷")
        captured = json.loads(ARTIFACT.read_text(encoding="utf-8"))

        refund_keys = captured["refund"]["keys"]
        for key in ("kind", "amount_minor", "related_feedback_id", "refund_state"):
            self.assertIn(key, refund_keys)
        self.assertNotIn("actual_minutes", refund_keys)

        from app import create_app  # noqa: PLC0415 - 局部导入，避免无 node 时导入路径失败

        TMP_ROOT.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix="ui_feedback_", dir=str(TMP_ROOT))
        client = create_app({"db_path": str(pathlib.Path(tmp) / "app.db")}).test_client()

        imported = client.post(
            "/api/imports?format=csv&mode=atomic", data=REFUND_CSV.encode("utf-8"), content_type="text/csv"
        )
        self.assertEqual(imported.status_code, 201, imported.get_data(as_text=True))
        candidate_id = client.get("/api/candidates").get_json()["items"][0]["id"]

        sale = client.post(
            f"/api/candidates/{candidate_id}/feedback",
            json={"kind": "sale", "amount_minor": captured["sale"]["payload"]["amount_minor"]},
        )
        self.assertEqual(sale.status_code, 201, sale.get_data(as_text=True))
        sale_id = sale.get_json()["id"]

        refund_payload = {
            "kind": "refund",
            "amount_minor": captured["refund"]["payload"]["amount_minor"],
            "related_feedback_id": sale_id,
            "refund_state": "settled",
        }
        self.assertEqual(sorted(refund_payload.keys()), refund_keys, "载荷键应与 JS 捕获的形状一致")
        refund = client.post(f"/api/candidates/{candidate_id}/feedback", json=refund_payload)
        self.assertEqual(refund.status_code, 201, refund.get_data(as_text=True))
        self.assertEqual(refund.get_json()["kind"], "refund")

        # 反证：修复前的形状（无 amount_minor）必须被真实端点拒绝，并给出字段原因。
        legacy = {"kind": "refund", "related_feedback_id": sale_id, "refund_state": "pending"}
        rejected = client.post(f"/api/candidates/{candidate_id}/feedback", json=legacy)
        self.assertEqual(rejected.status_code, 422)
        details = rejected.get_json()["error"]["details"]
        self.assertTrue(any(item.get("field") == "amount_minor" for item in details), details)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
