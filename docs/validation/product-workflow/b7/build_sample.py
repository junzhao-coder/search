"""生成 C 路线首选品类样品：学习计划 / 考试复习 Excel（纯自制，无第三方素材）。

只写 docs/validation/product-workflow/b7/ 下的文件。
用 openpyxl 3.1.5（bundled python 3.12）；字体只用系统默认（宋体/Calibri），
填充为纯色、边框为细线；无图片、无图标、无外链、无宏。
"""

from __future__ import annotations

import datetime
import pathlib

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT_DIR = pathlib.Path(r"D:\桌面\two\docs\validation\product-workflow\b7")
OUT = OUT_DIR / "sample-study-planner-v1.xlsx"

FONT_CN = "宋体"
FONT_EN = "Calibri"

TITLE_FILL = PatternFill("solid", fgColor="DDEBF7")
HEAD_FILL = PatternFill("solid", fgColor="BDD7EE")
SUM_FILL = PatternFill("solid", fgColor="FFF2CC")
RED_FILL = PatternFill("solid", fgColor="FFC7CE")
ORANGE_FILL = PatternFill("solid", fgColor="FFD8A8")
YELLOW_FILL = PatternFill("solid", fgColor="FFEB9C")
GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")

THIN = Side(style="thin", color="B7B7B7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, row: int, cols: int) -> None:
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(name=FONT_CN, bold=True, size=11)
        cell.fill = HEAD_FILL
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def style_block(ws, r1: int, r2: int, c1: int, c2: int) -> None:
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = BORDER
            if cell.font is None or cell.font.name is None:
                cell.font = Font(name=FONT_CN, size=11)
            cell.alignment = Alignment(vertical="center", wrap_text=True)


def page_setup(ws, area: str, orientation: str = "portrait") -> None:
    ws.print_area = area
    ws.page_setup.orientation = orientation
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.5


def sheet_usage(wb: Workbook) -> None:
    ws = wb.active
    ws.title = "使用说明"
    ws.merge_cells("A1:D1")
    ws["A1"] = "学习计划 / 考试复习表（v1 · 纯自制示例）"
    ws["A1"].font = Font(name=FONT_CN, bold=True, size=14)
    ws["A1"].fill = TITLE_FILL
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    blocks = [
        ("A3", "B3", "版本", "v1（示例，未定价、未上架）"),
        ("A4", "B4", "包含", "5 个工作表：使用说明 / 课程与考试 / 考试倒计时 / 周计划 / 复习进度"),
        ("A5", "B5", "不含", "第三方字体、图片、图标、模板；不含自动化脚本、AI 生成、提醒推送；不含代做与持续更新"),
        ("A6", "B6", "数据口径", "所有课程、考试、知识点均为虚构示例；表中任何“需求/关注度”数字都不是销量或成交"),
        ("A7", "B7", "打印", "各表已设打印区域；「周计划」为 A4 纵向、按宽度缩放"),
    ]
    for lc, vc, label, value in blocks:
        ws[lc] = label
        ws[lc].font = Font(name=FONT_CN, bold=True, size=11)
        ws[vc] = value
        ws[vc].font = Font(name=FONT_CN, size=11)
        ws[vc].alignment = Alignment(wrap_text=True, vertical="top")

    ws["A9"] = "怎么改（3 步）"
    ws["A9"].font = Font(name=FONT_CN, bold=True, size=12)
    steps = [
        "1. 打开「课程与考试」，把示例课程改成你自己的课程；考试日期是日期格式，直接选日期即可。",
        "2. 打开「周计划」，在周一至周日 × 时段的格子里填安排；打印前可在「页面布局」确认方向与缩放。",
        "3. 打开「复习进度」，按知识点逐行记录；「掌握度」是下拉选项（生疏/一般/熟练），「状态」由公式自动判断。",
    ]
    for i, text in enumerate(steps, start=10):
        ws[f"A{i}"] = text
        ws.merge_cells(f"A{i}:D{i}")
        ws[f"A{i}"].font = Font(name=FONT_CN, size=11)
        ws[f"A{i}"].alignment = Alignment(wrap_text=True, vertical="top")

    ws["A15"] = "字段一览"
    ws["A15"].font = Font(name=FONT_CN, bold=True, size=12)
    heads = ["工作表", "字段", "说明"]
    for c, h in enumerate(heads, start=1):
        ws.cell(row=16, column=c, value=h)
    style_header(ws, 16, 3)
    rows = [
        ("课程与考试", "课程名称 / 教师 / 学分 / 考试日期 / 考试地点 / 备注", "一门课一行；考试日期可为空（空则不参与倒计时）"),
        ("考试倒计时", "剩余天数 / 状态", "剩余天数 = 考试日期 − 今天；状态按 已过期/紧急(≤3)/临近(≤7)/正常 自动判断"),
        ("周计划", "时段 × 周一…周日", "自由填写；A4 纵向打印"),
        ("复习进度", "掌握度 / 复习次数 / 下次复习 / 状态", "状态按 下次复习 ≤ 今天 自动判断为“今日复习”"),
    ]
    for r, (a, b, c) in enumerate(rows, start=17):
        ws.cell(row=r, column=1, value=a)
        ws.cell(row=r, column=2, value=b)
        ws.cell(row=r, column=3, value=c)
    style_block(ws, 17, 20, 1, 3)

    ws["A22"] = "版本与日期"
    ws["A22"].font = Font(name=FONT_CN, bold=True, size=12)
    ws["A23"] = "生成日期"
    ws["A23"].font = Font(name=FONT_CN, bold=True, size=11)
    ws["B23"] = "=TODAY()"
    ws["B23"].number_format = "yyyy-mm-dd"
    ws["A24"] = "文件版本"
    ws["A24"].font = Font(name=FONT_CN, bold=True, size=11)
    ws["B24"] = "v1"
    for col, width in (("A", 14), ("B", 46), ("C", 52), ("D", 18)):
        ws.column_dimensions[col].width = width
    page_setup(ws, "A1:D24")


def sheet_courses(wb: Workbook) -> None:
    ws = wb.create_sheet("课程与考试")
    ws["A1"] = "课程与考试（示例数据，可整行删改）"
    ws["A1"].font = Font(name=FONT_CN, bold=True, size=13)
    ws["A1"].fill = TITLE_FILL
    ws.merge_cells("A1:G1")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")

    heads = ["序号", "课程名称", "教师", "学分", "考试日期", "考试地点", "备注"]
    for c, h in enumerate(heads, start=1):
        ws.cell(row=2, column=c, value=h)
    style_header(ws, 2, len(heads))

    today = datetime.date.today()
    samples = [
        ("高等数学（示例）", "A 老师", 5, today + datetime.timedelta(days=12), "教学楼 101", "闭卷"),
        ("大学英语（示例）", "B 老师", 3, today + datetime.timedelta(days=5), "教学楼 203", "含听力"),
        ("数据结构（示例）", "C 老师", 4, today + datetime.timedelta(days=2), "机房 305", "上机考试"),
        ("线性代数（示例）", "D 老师", 3, today + datetime.timedelta(days=20), "教学楼 102", ""),
        ("体育（示例）", "E 老师", 1, None, "操场", "随堂考核"),
        ("选修·写作（示例）", "F 老师", 2, today - datetime.timedelta(days=3), "线上", "已过期示例"),
    ]
    for i, (name, teacher, credit, exam, place, note) in enumerate(samples, start=1):
        r = 2 + i
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=3, value=teacher)
        ws.cell(row=r, column=4, value=credit)
        if exam is not None:
            ws.cell(row=r, column=5, value=exam).number_format = "yyyy-mm-dd"
        else:
            ws.cell(row=r, column=5, value="")
        ws.cell(row=r, column=6, value=place)
        ws.cell(row=r, column=7, value=note)
    style_block(ws, 3, 8, 1, 7)

    ws["A10"] = "统计"
    ws["A10"].font = Font(name=FONT_CN, bold=True, size=11)
    ws["B10"] = "=COUNTA(B3:B8)"
    ws["C10"] = "门课程"
    ws["D10"] = "=SUM(D3:D8)"
    ws["E10"] = "学分合计"
    ws["F10"] = "=COUNT(E3:E8)"
    ws["G10"] = "门有考试日期"
    for cell in ("A10", "B10", "C10", "D10", "E10", "F10", "G10"):
        ws[cell].fill = SUM_FILL
        ws[cell].border = BORDER
        ws[cell].font = Font(name=FONT_CN, bold=(cell in ("A10", "C10", "E10", "G10")), size=11)

    for col, width in (("A", 6), ("B", 22), ("C", 10), ("D", 8), ("E", 13), ("F", 14), ("G", 20)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A3"
    page_setup(ws, "A1:G10")


def sheet_countdown(wb: Workbook) -> None:
    ws = wb.create_sheet("考试倒计时")
    ws["A1"] = "今天"
    ws["A1"].font = Font(name=FONT_CN, bold=True, size=11)
    ws["B1"] = "=TODAY()"
    ws["B1"].number_format = "yyyy-mm-dd"
    ws["B1"].fill = SUM_FILL
    ws["B1"].border = BORDER
    ws["C1"] = "（打开文件时自动更新；倒计时随日期变化）"
    ws["C1"].font = Font(name=FONT_CN, size=10)

    heads = ["课程名称", "考试日期", "剩余天数", "状态", "考试地点"]
    for c, h in enumerate(heads, start=1):
        ws.cell(row=3, column=c, value=h)
    style_header(ws, 3, len(heads))

    for i in range(6):
        r = 4 + i
        src = 3 + i
        ws.cell(row=r, column=1, value=f"=IF('课程与考试'!B{src}=\"\",\"\",'课程与考试'!B{src})")
        cell_date = ws.cell(row=r, column=2, value=f"=IF('课程与考试'!E{src}=\"\",\"\",'课程与考试'!E{src})")
        cell_date.number_format = "yyyy-mm-dd"
        ws.cell(row=r, column=3, value=f'=IF($B{r}="","",$B{r}-$B$1)')
        ws.cell(row=r, column=4, value=(
            f'=IF($B{r}="","未排期",IF($C{r}<0,"已过期",IF($C{r}<=3,"紧急",IF($C{r}<=7,"临近","正常"))))'
        ))
        ws.cell(row=r, column=5, value=f"=IF('课程与考试'!F{src}=\"\",\"\",'课程与考试'!F{src})")
    style_block(ws, 4, 9, 1, 5)

    ws["A11"] = "汇总"
    ws["A11"].font = Font(name=FONT_CN, bold=True, size=11)
    ws["B11"] = "紧急（≤3 天）"
    ws["C11"] = '=COUNTIF(D4:D9,"紧急")'
    ws["D11"] = "已过期"
    ws["E11"] = '=COUNTIF(D4:D9,"已过期")'
    for cell in ("A11", "B11", "C11", "D11", "E11"):
        ws[cell].fill = SUM_FILL
        ws[cell].border = BORDER
        ws[cell].font = Font(name=FONT_CN, bold=(cell in ("A11", "B11", "D11")), size=11)

    ws.conditional_formatting.add("C4:C9", CellIsRule(operator="lessThan", formula=["0"], fill=RED_FILL))
    ws.conditional_formatting.add(
        "C4:C9", CellIsRule(operator="between", formula=["0", "3"], fill=ORANGE_FILL)
    )
    ws.conditional_formatting.add(
        "C4:C9", CellIsRule(operator="between", formula=["4", "7"], fill=YELLOW_FILL)
    )
    ws.conditional_formatting.add("C4:C9", CellIsRule(operator="greaterThan", formula=["7"], fill=GREEN_FILL))
    ws.conditional_formatting.add(
        "D4:D9", FormulaRule(formula=['$D4="已过期"'], fill=RED_FILL)
    )

    for col, width in (("A", 22), ("B", 13), ("C", 10), ("D", 10), ("E", 14)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A4"
    page_setup(ws, "A1:E11")


def sheet_week(wb: Workbook) -> None:
    ws = wb.create_sheet("周计划")
    ws.merge_cells("A1:H1")
    ws["A1"] = "每周计划（周一至周日 × 时段；打印 A4 纵向）"
    ws["A1"].font = Font(name=FONT_CN, bold=True, size=13)
    ws["A1"].fill = TITLE_FILL
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")

    heads = ["时段"] + ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for c, h in enumerate(heads, start=1):
        ws.cell(row=3, column=c, value=h)
    style_header(ws, 3, len(heads))

    slots = [
        "07:00–08:00", "08:00–09:00", "09:00–10:00", "10:00–11:00",
        "11:00–12:00", "12:00–13:00", "14:00–15:00", "15:00–16:00",
        "16:00–17:00", "17:00–18:00", "19:00–20:00", "20:00–21:00",
    ]
    for i, slot in enumerate(slots):
        r = 4 + i
        ws.cell(row=r, column=1, value=slot)
        for c in range(2, 9):
            ws.cell(row=r, column=c, value="")
    style_block(ws, 4, 15, 1, 8)

    samples = {
        (4, 2): "高等数学", (6, 3): "大学英语", (8, 4): "数据结构",
        (10, 5): "实验课", (11, 6): "复习：线代", (13, 7): "周复盘",
    }
    for (r, c), text in samples.items():
        ws.cell(row=r, column=c, value=text)

    ws["A17"] = "提示：格子内容可自由填；打印前在「页面布局 → 纸张方向」确认纵向、缩放为「1 页宽」。"
    ws.merge_cells("A17:H17")
    ws["A17"].font = Font(name=FONT_CN, size=10)

    ws.column_dimensions["A"].width = 13
    for c in range(2, 9):
        ws.column_dimensions[get_column_letter(c)].width = 13
    ws.freeze_panes = "A4"
    ws.print_title_rows = "3:3"
    page_setup(ws, "A1:H15", orientation="portrait")


def sheet_review(wb: Workbook) -> None:
    ws = wb.create_sheet("复习进度")
    ws["A1"] = "复习进度（掌握度下拉；状态自动判断）"
    ws["A1"].font = Font(name=FONT_CN, bold=True, size=13)
    ws["A1"].fill = TITLE_FILL
    ws.merge_cells("A1:G1")

    heads = ["序号", "知识点", "所属课程", "掌握度", "复习次数", "下次复习", "状态"]
    for c, h in enumerate(heads, start=1):
        ws.cell(row=2, column=c, value=h)
    style_header(ws, 2, len(heads))

    today = datetime.date.today()
    samples = [
        ("极限的定义", "高等数学（示例）", "一般", 2, today + datetime.timedelta(days=1)),
        ("导数与微分", "高等数学（示例）", "生疏", 1, today),
        ("定积分换元", "高等数学（示例）", "熟练", 3, today + datetime.timedelta(days=6)),
        ("英语长难句", "大学英语（示例）", "一般", 2, today - datetime.timedelta(days=1)),
        ("二叉树遍历", "数据结构（示例）", "生疏", 1, today),
        ("排序复杂度", "数据结构（示例）", "熟练", 4, today + datetime.timedelta(days=9)),
        ("矩阵初等变换", "线性代数（示例）", "一般", 2, today + datetime.timedelta(days=3)),
        ("论文结构", "选修·写作（示例）", "生疏", 1, ""),
    ]
    for i, (point, course, level, times, nxt) in enumerate(samples, start=1):
        r = 2 + i
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=point)
        ws.cell(row=r, column=3, value=course)
        ws.cell(row=r, column=4, value=level)
        ws.cell(row=r, column=5, value=times)
        if nxt:
            ws.cell(row=r, column=6, value=nxt).number_format = "yyyy-mm-dd"
        else:
            ws.cell(row=r, column=6, value="")
        ws.cell(row=r, column=7, value=(
            f'=IF($F{r}="","未排期",IF($F{r}<=TODAY(),"今日复习","待复习"))'
        ))
    style_block(ws, 3, 10, 1, 7)

    dv = DataValidation(type="list", formula1='"生疏,一般,熟练"', allow_blank=True, showDropDown=False)
    dv.error = "请从下拉中选择：生疏 / 一般 / 熟练"
    dv.errorTitle = "掌握度"
    dv.prompt = "选择掌握度"
    dv.promptTitle = "掌握度"
    ws.add_data_validation(dv)
    dv.add("D3:D10")

    ws["A12"] = "统计"
    ws["A12"].font = Font(name=FONT_CN, bold=True, size=11)
    stats = [
        ("B12", "知识点数", "C12", "=COUNTA(B3:B10)"),
        ("D12", "熟练", "E12", '=COUNTIF(D3:D10,"熟练")'),
        ("B13", "今日复习", "C13", '=COUNTIF(G3:G10,"今日复习")'),
        ("D13", "待复习", "E13", '=COUNTIF(G3:G10,"待复习")'),
        ("B14", "平均复习次数", "C14", "=IFERROR(AVERAGE(E3:E10),0)"),
    ]
    for lc, label, vc, formula in stats:
        ws[lc] = label
        ws[vc] = formula
        for cell in (lc, vc):
            ws[cell].fill = SUM_FILL
            ws[cell].border = BORDER
            ws[cell].font = Font(name=FONT_CN, bold=(cell == lc), size=11)
    ws["C14"].number_format = "0.0"

    ws.conditional_formatting.add("G3:G10", FormulaRule(formula=['$G3="今日复习"'], fill=ORANGE_FILL))
    ws.conditional_formatting.add("G3:G10", FormulaRule(formula=['$G3="待复习"'], fill=YELLOW_FILL))
    ws.conditional_formatting.add("G3:G10", FormulaRule(formula=['$G3="未排期"'], fill=PatternFill("solid", fgColor="D9D9D9")))

    for col, width in (("A", 6), ("B", 20), ("C", 20), ("D", 10), ("E", 10), ("F", 13), ("G", 11)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A3"
    page_setup(ws, "A1:G14")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    sheet_usage(wb)
    sheet_courses(wb)
    sheet_countdown(wb)
    sheet_week(wb)
    sheet_review(wb)
    wb.properties.creator = "self-made sample (b7)"
    wb.properties.title = "学习计划 / 考试复习表 v1"
    wb.properties.description = "纯自制示例：无第三方字体/图片/图标；需求数字非销量"
    wb.active = 0
    wb.save(OUT)
    print(f"WROTE {OUT} bytes={OUT.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
