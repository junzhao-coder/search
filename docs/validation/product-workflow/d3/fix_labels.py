import pathlib
import sys

target = pathlib.Path(r"D:\桌面\two\tools\workbench\tests\test_wizard.py")
s = target.read_text(encoding="utf-8")
pairs = [
    ('for label in ("选品", "选源", "起草介绍"):', 'for label in ("选品", "找货源", "写文案"):'),
    ("（选品/选源/起草介绍）", "（选品/找货源/写文案）"),
    ('self.assertEqual(labels, ["选品", "选源", "起草介绍"])', 'self.assertEqual(labels, ["选品", "找货源", "写文案"])'),
    ('self.assertEqual(html.count("继续选源"), 2)', 'self.assertEqual(html.count("继续找货源"), 2)'),
    ('self.assertEqual(html.count("继续起草介绍"), 2)', 'self.assertEqual(html.count("继续写文案"), 2)'),
]
for old, new in pairs:
    s = s.replace(old, new)
target.write_text(s, encoding="utf-8")
print("remaining_old=", any(x in s for x in ("选源", "起草介绍")))
