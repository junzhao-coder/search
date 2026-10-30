# D2：修三处卡点（反馈表头 / 双入口语义 / 一键重记导出）

> 来源：D1 走查记录的前三条摩擦。**未改**就绪判定、导出白名单、字段校验；未登录平台、未采购、未发布。

## 1) 反馈表头：可复制 + 脚本给出可操作报错

**文档**（`b24/FEEDBACK-CARD.md`）：在「C3 反馈字段」下新增**可直接复制的两行代码块**（表头 + 一行 synthetic 示例），并注明英文表头也支持、拼错时会打印可复制表头。

**脚本**（`b25/review.py`）：
- 新增 `HEADER_ALIASES`（12 列全部有英文/别名映射，如 `date→日期`、`orders→成交`、`manual_minutes→人工耗时分钟`）；
- 解析前自动映射表头；非 JSON 输出打印 `表头别名已自动映射：date→日期；…`，`--json` 里在 `header.mapped` 可查；
- 表头缺列时输出**检测到的表头 / 期望的表头（可直接复制）/ 修正建议**，并打印**退出码含义**（0＝可解析；2＝缺列或非数字行）；
- `b25/README.md` 增补**中英映射表**与退出码说明。

**实测**：

| 输入 | 结果 |
| --- | --- |
| 英文表头（12 列） | **rc=0**；打印映射行；四指标：转化率 25.0%、净利 18.5 元、时薪 24.67 元/h → 建议「提价」 |
| 缺列表头（`日期,错误列`） | **rc=2**；打印「检测到的表头：日期,错误列」「期望的表头：日期,单号,…」「修正建议：改成这行表头即可…」+ 退出码说明 |
| `b25/feedback-log.csv`（原中文表头 2 行） | **rc=0**，未受影响（转化率 20.0%、净利 17.91 元、时薪 4.48 元/h → 「提价」） |

日志：`d2/logs/review_en_header.log`、`review_bad_header.log`、`review_b25_default.log`；样例 CSV：`d2/feedback-en.csv`、`feedback-bad.csv`。

## 2) 双入口语义：`/worksheet` 明确“本页不生成文案版本”

采用**提示 + 说明**方案（任务允许二选一）。理由：
- 让 `/worksheet` 也生成版本需要复用 `copy_snapshot/_insert_version` 并额外消耗一个 `revision`（证据保存本身已 +1），会让“一次保存 +2 revision”的行为出现在更多入口，**与 `/copy` 的既有提示冲突**；
- 提示方案零风险、不改写入语义，且 `/copy` 才是文案编辑的正门（有版本历史与回滚）。

实现：`views_worksheet.render_readiness()` 证据表单标题下新增一句：
> 文案字段（卖点/价格/交付/售后/FAQ）与**文案版本**请在「起草介绍」页编辑；**本页保存不生成文案版本**。（带 `?wo=` 链接）

线上核对：`/worksheet/wo:20261023-88ef9a66` **200**，`本页保存不生成文案版本` 与 `/copy?wo=…` 链接均存在。

## 3) 发布变更提示旁加“一键重记导出”

`views_worksheet.render_publish()`：当 `publish_changed()` 判定为变更时，提示条内直接内嵌一个 `POST /worksheet/<id>/export/record`（复用既有路由，含 `csrf` + `format=md`）的按钮「**重新记录本次导出**」。

实测截图：`shots/worksheet_publish_rerecord.png`（1160×286，PNG，`has_rerecord_button=true`；隔离库单 `wo:20261024-cee6de56`，先记录导出再改发布信息造出变更态）。

## 4) 测试与回归

| suite | 命令（cwd） | rc | summary |
| --- | --- | --- | --- |
| `tests.test_copy_publish` | `python -X utf8 -m unittest tests.test_copy_publish -v`（`tools/workbench`） | **0** | `Ran 12 tests — OK` |
| `workbench_all` | `… discover -s tests -t .` | **0** | `Ran 215 tests — OK` |
| `project_full` | `… discover -s tests`（仓库根，`APP_DB_PATH=%TEMP%\d2_full.db`） | **0** | `Ran 334 tests — OK`（48.7s） |

新增两例：
- `test_publish_change_banner_has_rerecord_button`：变更横幅含「重新记录本次导出」与 `/worksheet/<id>/export/record`；
- `test_worksheet_evidence_page_points_copy_versions_to_wizard`：详情页含「本页保存不生成文案版本」与 `/copy?wo=<id>` 链接。

`review.py` 的行为用真实进程实测（见第 1 节日志），未塞进 workbench 测试套件（它属文档目录脚本）。

## 5) 部署与守卫

- 只停本工具父子进程后分离重启 5015：**父 PID 96704 / 监听 PID 99804**；`/healthz` 含 `app_id=workbench-opportunity/1`。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`。

## 6) 改动摘要（diff）

- `docs/validation/product-workflow/b24/FEEDBACK-CARD.md`：+可复制表头与示例行、+英文别名说明。
- `docs/validation/product-workflow/b25/review.py`：+`HEADER_ALIASES`、+`HEADER_EXAMPLE`；`parse_rows()` 返回 `header_info` 并做表头归一；`print_human()` 增「检测/期望/建议」与「已映射」行、退出码说明；`main()` 把 `header` 写入结果。
- `docs/validation/product-workflow/b25/README.md`：+中英映射表、+退出码与报错说明。
- `tools/workbench/views_worksheet.py`：证据表单加“文案版本在 /copy”提示；发布变更横幅内嵌「重新记录本次导出」表单。
- `tools/workbench/tests/test_copy_publish.py`：+2 例。

## 7) 未覆盖 / 限制

1. `/worksheet` **仍不会**生成文案版本（选了提示方案），所以两处填写文案时只有 `/copy` 会推进版本号——这是刻意的语义统一，不是遗漏。
2. 英文别名只覆盖常见写法；未识别的列会照原样保留并触发“缺列”提示（仍可从提示行复制正确表头）。
3. 「重新记录本次导出」固定以 `md` 格式记录（与 `/copy` 页按钮一致）；若要 json 可去 `/copy` 或详情页导出区操作。
4. `review.py` 的英文表头行为靠真实进程验证（日志留存），未加入 workbench 单元测试套件。
