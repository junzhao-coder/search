"""review.py 单测（纯标准库 unittest）。

覆盖：正常四指标 / 零成交 / 耗时 0 / na 值 / 非法数字行报错 / --json 字段齐全。
运行：python -m unittest discover -s tests -t . -v   （在 b25 目录下）
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

B25 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B25))

import review  # noqa: E402

HEADER = "日期,单号,渠道,曝光,询单,成交,退款,实际售价,到手,人工耗时分钟,交付方式,备注\n"


def write_csv(text: str) -> pathlib.Path:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="")
    tmp.write(text)
    tmp.close()
    return pathlib.Path(tmp.name)


def run(csv_path, *args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = review.main([str(csv_path), *args])
    return code, buf.getvalue()


class ReviewTests(unittest.TestCase):
    def test_normal_four_metrics(self):
        """正常行：四指标都算出来，且高退款率触发「修描述」。"""
        path = write_csv(HEADER + "2026-10-24,wo:x,xianyu,na,10,4,1,19.9,400,300,站内文件,test\n")
        code, out = run(path)
        self.assertEqual(code, 0, out)
        self.assertIn("询单转化率      40.0 %", out)
        self.assertIn("单件净利        100.0 元", out)
        self.assertIn("折算时薪        20.0 元/小时", out)
        self.assertIn("退款率          25.0 %", out)
        self.assertIn("【修描述】", out)

    def test_zero_orders_is_insufficient(self):
        """成交=0 → 样本不足，且不崩溃。"""
        path = write_csv(HEADER + "2026-10-24,wo:x,xianyu,na,5,0,0,19.9,0,60,站内文件,test\n")
        code, out = run(path)
        self.assertEqual(code, 0, out)
        self.assertIn(review.INSUFFICIENT, out)
        self.assertIn("成交 ÷ 询单", out)  # 摘要仍然打印

    def test_zero_minutes_is_insufficient(self):
        """耗时=0 → 时薪不可算 → 样本不足。"""
        path = write_csv(HEADER + "2026-10-24,wo:x,xianyu,na,8,3,0,19.9,150,0,站内文件,test\n")
        code, out = run(path)
        self.assertEqual(code, 0, out)
        self.assertIn(review.INSUFFICIENT, out)
        self.assertIn("na", out)

    def test_na_values_skipped(self):
        """na 值跳过、不报错：到手 na → 净利/时薪 na；曝光 na 不影响。"""
        path = write_csv(HEADER + "2026-10-24,wo:x,xianyu,na,6,2,0,19.9,na,120,站内文件,test\n")
        code, out = run(path)
        self.assertEqual(code, 0, out)
        self.assertIn("单件净利        na", out)
        self.assertIn("折算时薪        na", out)

    def test_invalid_number_reports_line_and_field(self):
        """非法数字：给出 行号 + 字段名，退出码 2，但仍打印已解析摘要。"""
        path = write_csv(HEADER
                         + "2026-10-24,wo:a,xianyu,na,10,4,0,19.9,400,300,站内文件,ok\n"
                         + "2026-10-24,wo:b,xianyu,na,abc,2,0,19.9,100,60,站内文件,bad\n")
        code, out = run(path)
        self.assertEqual(code, 2, out)
        self.assertIn("第 3 行", out)
        self.assertIn("询单", out)
        self.assertIn("不是数字", out)
        self.assertIn("=== 一周复盘（4 个数字） ===", out)  # 摘要仍在

    def test_json_mode_fields_complete(self):
        """--json：指标、建议、假设、合计、错误清单字段齐全。"""
        path = write_csv(HEADER + "2026-10-24,wo:x,xianyu,na,10,4,0,19.9,400,300,站内文件,test\n")
        code, out = run(path, "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        for key in ("csv", "rows_parsed", "assumptions", "totals", "metrics", "recommendation", "errors"):
            self.assertIn(key, data)
        for key in ("询单转化率%", "单件到手元", "单件净利元", "折算时薪元", "退款率%"):
            self.assertIn(key, data["metrics"])
        self.assertIn("label", data["recommendation"])
        self.assertIn("reasons", data["recommendation"])
        self.assertIn("阈值", data["assumptions"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
