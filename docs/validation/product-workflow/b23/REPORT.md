# B23：平台准入核对清单 + 结论登记模板 + /copy 取证提示

> 本轮**不替你判断平台是否允许**。只给“怎么核对、怎么留证、怎么登记结论”，并降低第一次核对的门槛。
> 生产单 `wo:20261023-88ef9a66` 仍 **6/7**，`platform_evidence` **保持为空**，导出按设计 **409**。

## 1. 交付物

| 文件 | 内容 |
| --- | --- |
| [PLATFORM-CHECKLIST.md](PLATFORM-CHECKLIST.md) | 面向非技术用户的 **5 个核对点**：①最接近类目与路径 ②该类目是否允许虚拟商品/文件交付 ③是否需资质/保证金/类目权限 ④价格/交付/售后限制 ⑤常见违规样例。每点给出「在哪里看 / 看到什么算确认 / 留证方式 / 常见误区」，并规定留证命名 `yyyyMMdd-序号-内容`、记录日期与页面标题 |
| [PLATFORM-DECISION.md](PLATFORM-DECISION.md) | 结论登记模板：**三选一**（允许发布 / 需资质 / 不允许），每项含「下一步动作 + 停止条件」；留「证据编号/链接、确认时间、确认人」字段；**明确由用户本人填写**，执行者不代填结论 |

关键约束（写进了两份文档）：
- 文案克制：**填了证据 ≠ 平台已批准**；核对未完成前 `platform_evidence` 保持为空、导出维持 409。
- 截图留证要求打码账号/手机号/订单号；示例文件名是**虚构**的（`20261024-01-类目页截图.png`），未使用任何他人后台截图。
- 不允许为了“先发出去”而改类目/改描述规避审核（写入 DECISION 的停止条件）。

## 2. /copy 页面取证提示（只加文案 + 一个既有字段的输入框）

- 现状核查发现：`/copy` 页此前**没有** `platform_evidence` 输入框（该字段只在 `/worksheet/<id>` 的完整证据表单里）。为让提示有落点，本次在 `/copy` 表单中加入该字段（提交仍走既有 `copy/save → readiness.save_evidence`，**未改就绪判定、导出白名单或字段校验**）。
- 提示文案（位于输入框下方）：
  > 请填**条款链接或截图编号**；未核对前请保持为空，导出会被阻止。填了只代表“有证据”，**不代表平台已批准**。核对方法与结论登记见本地文件 `docs/validation/product-workflow/b23/PLATFORM-CHECKLIST.md` 与 `PLATFORM-DECISION.md`。
- 未做站外链接（文档在本地仓库，页面只写路径文本）。

## 3. 测试与部署

| suite | 命令（cwd） | rc | summary |
| --- | --- | --- | --- |
| `workbench_all` | `python -X utf8 -m unittest discover -s tests -t .`（`tools/workbench`） | **0** | `Ran 210 tests — OK` |
| `project_full` | `python -X utf8 -m unittest discover -s tests`（仓库根，`APP_DB_PATH=%TEMP%\b23_full.db`） | **0** | `Ran 334 tests — OK`（82.0s） |

新增断言 `test_copy_page_has_platform_evidence_hint`：`/copy` 存在 `name="platform_evidence"`、包含「未核对前请保持为空，导出会被阻止」「不代表平台已批准」「PLATFORM-CHECKLIST.md」。

- 部署：只停本工具父子进程后分离重启 5015 —— **父 PID 101052 / 监听 PID 111368**。
- 线上核对：`/copy?wo=wo:20261023-88ef9a66` **200**，`FIELD=True`、`HINT=True`；`/healthz` 含 `app_id=workbench-opportunity/1`。
- 截图：`shots/copy_platform_hint.jpg` 1440×900 / 108,699 B / `60c6632214…`（`hint_visible_in_dom=true`；隔离库示例单 `wo:20261024-ed17db2c`）。

## 4. 守卫

`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…` 未变；未登录平台、未采购、未发布；未改评分/货源 CSV、业务库/冻结文件。

## 5. 限制与未覆盖

1. **不代替你下结论**：清单与模板只给方法与字段，结论必须你本人填；生产单 `platform_evidence` 仍为空，导出仍 409。
2. 清单里的“类目路径/条款”是**方法**，不是已核验的闲鱼事实——需要你按 ①–⑤ 实际去平台查。
3. `/copy` 新增的 `platform_evidence` 输入框只影响“能否记录证据”，**不代表平台审核结果**；填错内容（如随便一个链接）会通过就绪检查但发布仍可能被拒。
4. 截图示例为虚构文件名，未采集任何真实后台页面。
