# D1：synthetic 全链路走查记录（选品 → 复盘）

> **数据说明**：本次全部在**系统临时库**（`WORKBENCH_WORKFLOW_DB` / `WORKBENCH_SECRET_FILE` 指向临时目录）执行；
> 单名 **`[SYNTHETIC] D1 学习计划模板`**；平台证据为 `synthetic://d1/walkthrough-only`；发布为 `https://example.invalid/…`；
> **未登录平台、未发布真实商品、未采购**。生产库与业务库未被写入。
> 证据：`walkthrough.json`（9 步 + 10 条守卫，`all_ok=true`）、`ui.json`、`logs/`、`feedback-log.csv`。

## 一、逐环节记录（入口 → 操作 → 期望 → 实际 → 证据）

| # | 环节 | 入口 | 操作 | 期望 | 实际 | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| ① | 选品 | `GET /pick` → `POST /worksheet/new` | 点第一个商品组的「选这个」 | 200/303，生成 `wo:yyyymmdd-8hex` | **200**，单号 `wo:20261024-33da03de`（格式合规） | `walkthrough.json.steps[0]` |
| ② | 选源 | `GET /source?wo=` → 两个 POST | 新增候选（自制，synthetic）→ 采用 | 200/200，`selected_supply_id=sc:…` | **200/200**，候选 `sc:66857000` | `steps[1]` |
| ③ | 验货 | `POST /worksheet/<id>/sample/check` | 对 b7 样品做结构自检 | 200，`sample_status=verified` | **200**，`verified`（**结构自检，非真实 Excel 打开**） | `steps[2]` |
| ④ | 写介绍 | `POST /worksheet/<id>/copy/save` | 填成本 300 分/售价 1990 分/卖点/FAQ/交付/售后 | 200/303，生成文案版本 | **200**，`copy_version=copy-d1`，版本 1 条 | `steps[3]` |
| ⑤ | 就绪 | `GET /copy?wo=` | 先不填平台 → 6/7；补 `synthetic://…` → 7/7 | 页面显示「已就绪（服务端判定）」 | **是**；未填平台时导出 **409**（`ok_chips=6`） | `steps[4]`、`guards[0]` |
| ⑥ | 导出（GET） | `GET /export?format=md|json` | 各取一次 | 200，**导出表行数不变** | **200/200**，`workorder_export` **0→0**（零写）；买家字段 8 项；内部字段 0 命中 | `steps[5]` |
| ⑦ | 记录导出（POST） | `POST /export/record` ×2 | 首次记录 + 重复记录 | 首次 +1 行；重复 `dedup=true` 不增行 | **200/200**，行数 `0→1→1`，第二次 `X-WB-Deduplicated: true` | `steps[6]`、`guards[1]` |
| ⑧ | 发布回填 | `POST /worksheet/<id>/publish` | 已发布 / `https://example.invalid/…` / 已售 0 | 200/303，页面显示「已发布」 | **200**，状态与链接可见 | `steps[7]` |
| ⑨ | 复盘 | 写 `feedback-log.csv` → `b25/review.py` | 追加一行 synthetic，跑四指标 | 脚本 rc=0，输出四指标与建议 | **rc=0**；四指标全 `na`（询单/成交 0）→ 建议「样本不足，保留观察期」 | `steps[8]`、`walkthrough.json.review` |

## 二、守卫实测（10 条，全部符合预期）

| 守卫 | 操作 | 期望 | 实际 |
| --- | --- | --- | --- |
| 未就绪导出 | 平台证据为空时 `GET /export` | **409** | **409**（`ok_chips=6`） |
| 重复记录去重 | 同版本戳再 `POST /export/record` | 行数不变 + `dedup=true` | 行数 1→1，`X-WB-Deduplicated: true` |
| 发布·状态非法 | `status=上架` | 400 | **400** |
| 发布·URL 非 http | `published_url=ftp://y/x` | 400 | **400** |
| 发布·销量负数 | `sold_count=-1` | 400 | **400** |
| 越权 `status=ready` | `POST /edit` | 4xx | **403** |
| 越权 `status=verified` | `POST /edit` | 4xx | **403** |
| 篡改 `selected_supply_id` | `POST /edit` 带 `selected_supply_id=sc:deadbeef` | 4xx | **403** |
| 越权后库未变 | 比较 `selected_supply_id/revision/status` | 完全一致 | **一致**（`sc:66857000 / 6 / pending_supply`） |
| 改已选许可传导 | 把 `resale` 改 `no` | 样品与成本失效、readiness 下降、导出转 409 | `sample_status=NULL`、`cost_minor=NULL`、导出 **409** |

## 三、界面核对（`ui.json`）

- **三栏仅三项**：6 个页面/视口组合中主导航均为 `[选品, 选源, 起草介绍]`（无旧栏目）。
- **继续区块**：`/pick` 含「继续已有工作单」，且 `/source?wo=<该单>`、`/copy?wo=<该单>` 链接指向本单（`continue_links_to_wo=true`）。
- **无横向溢出**（`scrollW == innerW`）：

| 视口 | 页面 | innerW | scrollW | overflowX | 页面高 |
| --- | --- | --- | --- | --- | --- |
| 1440×900 | /pick | 1440 | 1440 | false | 1292 |
| 1440×900 | /source?wo=… | 1440 | 1440 | false | 985 |
| 1440×900 | /copy?wo=… | 1440 | 1440 | false | 1401 |
| 390×844 | /pick | 390 | 390 | false | 2251 |
| 390×844 | /source?wo=… | 390 | 390 | false | 1261 |
| 390×844 | /copy?wo=… | 390 | 390 | false | 2148 |

- **提示友好**：`/source` 无 `wo` → **400** 且含“还没有…/请先…”；`/copy?wo=wo:deadbeef` → **404** 且有不存在提示；`/` 跟随重定向后 **200**（落到 `/pick`）。

## 四、问题 / 不顺手清单（只记录，未修）

1. **反馈 CSV 列名是中文且强校验**：`b25/review.py` 只认 `日期/单号/渠道/曝光/询单/成交/退款/实际售价/到手/人工耗时分钟/交付方式/备注`；我第一次用英文表头 → **rc=2**（“存在非数字行”）。对用户来说“表头必须一模一样”是个坑，`FEEDBACK-CARD.md` 里只写字段名、没给可直接复制的表头行。
2. **`/copy` 与 `/worksheet/<id>` 存在字段重叠**：`platform_evidence` 两处都能填（B23 后在 `/copy` 新增），但**文案版本只在 `/copy` 保存时生成**，在 `/worksheet` 保存证据不会产生版本号——同一动作两个入口，行为不一致。
3. **发布回填的“变更提示”依赖版本号比较**：填完发布信息后若之前记录过导出，页面提示“建议重核就绪并重新导出”，但**没有一键重新记录**的按钮，需要再滚到导出区点一次。
4. **`/pick` 的“继续已有工作单”只列前 10 条**：单子多了之后，第 11 条起的单在 `/pick` 找不到，只能去 `/worksheet`（已不在侧栏，需要记 URL 或从向导页底部链接进入）。
5. **样品自检通过 ≠ 真实可打开**：页面写“已核对”，但依据是结构自检（openpyxl 缺失时还回退到 zip/XML 解析）；对用户来说“已核对”四个字容易被理解为“真的打开过”。
6. **步骤 ⑨ 的复盘是人工导出 CSV**：工作台里已有的发布回填数据（sold_count 等）**没有自动流入 feedback-log.csv**，需要手工再抄一遍，容易不一致。
7. **无 `wo` 时侧栏的“选源/起草介绍”是禁用灰项**：新用户点不动，也看不到“为什么不能点”以外的操作路径（除 `/pick` 顶部外没有额外引导）。
8. **`/` 是 302 而不是直接渲染选品页**：对外分享根地址时，某些工具/预览会显示“重定向”而不是页面内容（本次 `urllib` 跟随后 200，但多一跳）。

## 五、回归（真实 exit）

| suite | 命令（cwd） | rc | summary |
| --- | --- | --- | --- |
| `workbench_all` | `python -X utf8 -m unittest discover -s tests -t .`（`tools/workbench`） | **0** | `Ran 213 tests — OK` |
| `project_full` | `python -X utf8 -m unittest discover -s tests`（仓库根，`APP_DB_PATH=%TEMP%\d1_full.db`） | **0** | `Ran 334 tests — OK`（49.5s） |

守卫哈希未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`。
复跑命令：`python -X utf8 docs\validation\product-workflow\d1\walkthrough.py`（隔离库自动建、跑完删密钥）与 `…\ui_metrics.py`。
