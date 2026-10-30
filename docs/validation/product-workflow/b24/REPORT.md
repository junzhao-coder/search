# B24：发布操作卡 + 回填/反馈记录卡 + /copy 指引

> **前提**：只在 [b23/PLATFORM-DECISION.md](../b23/PLATFORM-DECISION.md) 勾了「**A. 允许发布**」之后才用这两张卡。
> 未拿到平台准入结论前，**不得宣称可发布**；工作台 `platform_evidence` 为空时导出仍是 **409**。

## 1. 两份卡

| 文件 | 内容 | 口语化 / 每步“你应该看到什么” |
| --- | --- | --- |
| [PUBLISH-CARD.md](PUBLISH-CARD.md) | **发布前 5 秒自检**（七项全绿、导出已记录、标题详情未改动、图片无第三方素材、售后口径已写）+ **8 步发布**：①打开导出包 ②确认类目（与 b23 结论一致）③粘贴标题 ④粘贴详情 ⑤定价与“虚拟商品”标注 ⑥上传图片（仅自制/已授权）⑦交付方式与时效 ⑧发布并立刻回填 | ✅ 每步都写“你应该看到什么”，并附“出问题怎么办”表 |
| [FEEDBACK-CARD.md](FEEDBACK-CARD.md) | 回填工作台的 6 个动作（状态/链接/发布时间/备注/已售/保存）+ **C3 反馈字段清单**（日期、单号、渠道、曝光、询单、成交、退款、实际售价、到手、人工耗时、交付方式、备注）+ **一周复盘 4 个数字**（询单转化率、单件净利、折算时薪、退款率） | ✅ 含“零成交写 0 并保留观察期”；明确**数据只记不发**、不索取买家信息、不在聊天里要账号密码；含四条红线 |

不重复 b23 的核对内容，只**引用**它（类目路径、交付方式、资质结论都指向 b23）。

## 2. /copy 页指引（一行，本地文件路径，无站外链接）

- `/copy` 新增**「发布回填」**小区块：**始终**显示当前发布状态（未发布/已发布/已下架）；**链接与已售数只在「发布后」有记录时才显示**（条件渲染、只读）——未发布时该区只显示「未发布」，不渲染空链接与空已售。另有指向该单详情页 `#h-pub` 表单的链接。
- 指引原文：
  > 发布与回填步骤见本地文件 `docs/validation/product-workflow/b24/PUBLISH-CARD.md` 与 `FEEDBACK-CARD.md`；填表入口在**该单详情页的「发布回填」**。系统不代发、不登录、不改平台设置。
- 未新增导航项；**未改**发布字段校验（三档状态、http/https、非负已售）、就绪判定与导出语义。

## 3. 测试与部署

| suite | 命令（cwd） | rc | summary |
| --- | --- | --- | --- |
| `tests.test_wizard` | `python -X utf8 -m unittest tests.test_wizard -v`（`tools/workbench`） | **0** | `Ran 63 tests — OK` |
| `workbench_all` | `… discover -s tests -t .` | **0** | `Ran 213 tests — OK` |
| `project_full` | `… discover -s tests`（仓库根，`APP_DB_PATH=%TEMP%\b24_full.db`） | **0** | `Ran 334 tests — OK`（81.0s） |

新增 `test_copy_page_has_publish_guidance`：`/copy` 含「发布回填」「PUBLISH-CARD.md」「FEEDBACK-CARD.md」「系统不代发、不登录、不改平台设置」与 `#h-pub` 链接。

- 部署：只停本工具父子进程后分离重启 5015 —— **父 PID 125412 / 监听 PID 113348**。
- 线上核对：`/copy?wo=wo:20261023-88ef9a66` **200**，`PUB_SECTION=True`、`GUIDE=True`、`NOAUTO=True`；侧栏仍 `选品,选源,起草介绍`；`/healthz` 含 `app_id=workbench-opportunity/1`。
- 截图：`shots/copy_publish_guide.jpg` 1440×900 / 88,890 B / `d32b4d0d52…`（`guide_visible_in_dom=true`）。

## 4. 守卫

`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…` 未变；未登录平台、未发布、未采购；未改评分/货源 CSV、业务库/冻结文件。

## 5. 限制

1. 两张卡是**操作指引**，不代替平台审核，也不保证发布成功；平台是否通过由平台决定。
2. 反馈卡里的“曝光/到手金额”等若平台不显示，请写 `na`，**不要估算**；“人工耗时”允许估整数。
3. `/copy` 的发布区块只显示状态（**发布后**才连带显示链接与已售）与跳转，**表单仍在详情页**（避免在 /copy 误导为“可一键发布”）。
4. 未实现：自动抓取平台数据、自动回填、发布提醒；这些都需要登录平台，本轮明确不做。
5. 生产单 `wo:20261023-88ef9a66` 仍 **6/7**、`platform_evidence` 为空、导出 **409**——本轮没有改动这一状态。
