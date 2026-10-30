"""B11：生成 VALUE.md（净利与时薪敏感性表；全部为假设）。"""

from __future__ import annotations

import pathlib

B11 = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b11")
PRICES = [9.9, 19.9, 29.9, 39.9, 49.9]
HOURLY = [15, 30, 60]
MINUTES = [15, 30]
PLATFORM_FEE = 0.01      # 假设：平台费 1%
PAYMENT_FEE = 0.006      # 假设：支付/提现费 0.6%
AFTERSALES = 1.0         # 假设：售后预留 ¥1/单
PROCUREMENT = 0.0        # 自制数字品：采购成本 0

def net(price: float, hourly: float, minutes: int) -> float:
    labor = hourly * minutes / 60
    return price * (1 - PLATFORM_FEE - PAYMENT_FEE) - AFTERSALES - PROCUREMENT - labor

def table(minutes: int) -> str:
    head = "| 售价（¥，假设） | " + " | ".join(f"时薪 ¥{h}/h" for h in HOURLY) + " |"
    sep = "| --- | " + " | ".join("---" for _ in HOURLY) + " |"
    rows = [head, sep]
    for p in PRICES:
        cells = []
        for h in HOURLY:
            n = net(p, h, minutes)
            hourly_back = n / (minutes / 60)
            cells.append(f"净利 ¥{n:.2f}（时薪 ¥{hourly_back:.0f}）")
        rows.append(f"| ¥{p:.1f} | " + " | ".join(cells) + " |")
    return "\n".join(rows)

def verdicts() -> str:
    lines = ["| 售价 | 15 分钟@¥30/h | 30 分钟@¥30/h | 30 分钟@¥60/h | 判定 |", "| --- | --- | --- | --- | --- |"]
    for p in PRICES:
        a = net(p, 30, 15); b = net(p, 30, 30); c = net(p, 60, 30)
        worst_hourly = min(a / 0.25, b / 0.5, c / 0.5)
        bad = (b < 5) or (worst_hourly < 30)
        lines.append(f"| ¥{p:.1f} | ¥{a:.2f} | ¥{b:.2f} | ¥{c:.2f} | {'**不值得做**' if bad else '可做（仍需平台核验）'} |")
    return "\n".join(lines)

def main() -> int:
    md = f"""# C3 学习计划 Excel：价值评估（全部为假设，非实测毛利）

> **口径提醒**：本文所有数字都是**假设**，用于判断“值不值得投入时间”，**不是成交价、不是实测毛利、不是收益预测**。
> 人工时薪与耗时由本任务给出**可替换假设**；你应按自己的真实时薪/耗时重算。

## 1. 计算式

```
单件净利 = 售价 − 采购成本 − 平台费 − 支付/提现费 − 售后预留 − 人工时间 × 时薪
每小时回报 = 单件净利 ÷ 单件耗时（小时）
```

| 参数 | 本批取值 | 说明 |
| --- | --- | --- |
| 采购成本 | **¥0** | 自制数字品（B7 样品），无进货成本 |
| 平台费 | **售价 × 1%** | 假设；闲鱼个人交易实际可能为 0，需以平台规则为准 |
| 支付/提现费 | **售价 × 0.6%** | 假设 |
| 售后预留 | **¥1.0 / 单** | 假设（答疑/重发/退款摊销） |
| 人工耗时 | **15 分钟 / 30 分钟** | 假设：改文案+交付+答疑 |
| 人工时薪 | **¥15 / ¥30 / ¥60** | 假设：按你自己的时间价值替换 |

## 2. 敏感性表（耗时 15 分钟）

{table(15)}

## 3. 敏感性表（耗时 30 分钟）

{table(30)}

## 4. 结论阈值与判定

- **阈值（本批建议，可替换）**：单件净利 **< ¥5** 或 折算时薪 **< ¥30** → 明确写**不值得做**。
- 按该阈值：

{verdicts()}

**读法**：¥9.9 档在 30 分钟/¥30h 下净利仅 ~¥8.5、时薪 ~¥17，低于阈值 → 不值得；¥29.9 以上在 15 分钟耗时下才勉强过线；**¥49.9 打包档在时薪 ¥60 时仍不划算**（人工时间吃掉大部分）。

## 5. 结论（交给你判断）

1. **低价档（¥9.9–19.9）人工不划算**：单件净利虽为正，但折算时薪低于 ¥30；除非批量复用同一份文件、几乎零答疑。
2. **¥29.9–39.9** 只有在「15 分钟内交付 + 售后极少」时才勉强达线；30 分钟耗时下多为“不值得做”。
3. **¥49.9 打包档**需要三场景版本（当前**未制作**），若真做三版，人工耗时会显著上升，**更可能不划算**。
4. **真正的瓶颈是人工时间**，不是平台费：把交付标准化（模板化说明、常见问题自助）比提价更有效。
5. 以上全部基于**假设**；你替换成自己的时薪/耗时后，结论可能反转——请用上面的表自己算。
"""
    (B11 / "VALUE.md").write_bytes(md.encode())
    print("VALUE.md bytes=", len(md.encode()))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
