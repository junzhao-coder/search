# 互动字段（转发/评论/赞）重写：按位置解析 + 区分真实 0 与未渲染

- 时间：2026-10-30T07:02Z 起（UTC）；cwd `D:\桌面\two`；解释器 `C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe`。
- **本轮零网络、零额度**：只用本地 fixture + 真实 Chrome（local 模式、DNS 全不解析 + CDP 封网）；平台账本 mtime 仍是 `2026-10-30 14:51:45`（上一轮 weibo-rpa-9 写入），本轮未动。

## 1. 改了什么

`session.DESKTOP_CARD_JS` 里 `div.card-act` 的解析整体重写：

1. 取 `div.card-act` 内**可见的 `a`**，按 DOM 顺序编号；
2. 每个 `a` 先判类型（`href`/`class`/`title` 含 `repost|forward|转发` → 转发；`comment|评论` → 评论；`like|praise|attitude|赞` → 赞）；
3. 再解析数字：纯数字 `12`、带标签 `转发 12`、带单位 `1.2万`（→ `12000`，并记 `unit="万"`、`raw="1.2万"`）；
4. **归属顺序**：先按类型占位（`count_source="type"`）；剩下没归位的按位置补（第 1 个=转发、第 2 个=评论、第 3 个=赞，`count_source="position"`）；位置用尽或该 `a` 没有数字 → 该字段 `null` + `count_source="unknown"`；`div.card-act` 缺失 → `null` + `count_source="absent"`；
5. **真实 0 与未渲染分开**：文本 `0` → `0`（不算缺失）；没有该位置或文本无数字 → `null` 且写进 `missing`。

`extract.extract_cards` 的 `details[]` 增加 `count_source`（每字段 position/type/unknown/absent）、`count_unit`，并把为 `null` 的互动字段去重后并入 `missing`。
正文/作者/时间/链接提取未动；隐藏节点、跨域、id↔链接一致性校验保持原样。

## 2. 四类 fixture 的实际输出（真实浏览器）

| fixture | 场景 | reposts | comments | likes | count_source | count_unit | missing（互动部分） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `counts-a.html` | 三值齐全含一个 0（`12 / 0 / 1.2万`） | **12** | **0** | **12000** | position / position / position | – / – / **万** | 无 |
| `counts-b.html` | 只渲染 1–2 个（`5` + `评论 7`） | **5** | **7** | **null** | position / **type** / unknown | – | `likes` |
| `counts-c.html` | 三个全为 0（`0 / 0 / 0`） | **0** | **0** | **0** | position / position / position | – | 无 |
| `counts-d.html` | 完全未渲染（没有 `div.card-act`） | **null** | **null** | **null** | absent / absent / absent | – | `reposts, comments, likes` |

（`missing` 里其余 `parent_id/title/voteup` 是记录 schema 的既有缺项，与互动无关。）

原始产物：`logs/counts-check.json`、`logs/counts-check.stdout.log`；脚本 `checks/counts_check.py`；fixture `checks/fixtures/counts-{a,b,c,d}.html`。

## 3. 测试

| 项 | 结果 |
| --- | --- |
| `tests.test_selection_rpa` | **129 tests OK**（新增 `CountMappingTests` 3 例：真实 0 不入 missing、未渲染写 null 且 missing 只出现一次、count_source 透出） |
| 四套全量 | **364 tests OK**（`logs/tests-all-counts.log`），无跳过 |
| `counts_check`（新） | **exit 0**，四类断言全过 |
| `desktop_extract_check`（回归） | **exit 0**（2 条记录、rejected `{foreign_host:1,bad_id:1}`） |
| `live_search_smoke`（回归） | **exit 0**（2 条记录，互动 12/3/45 仍读到） |
| `probe_smoke`（回归） | **exit 0** |

## 4. 预期效果与未验证项

- 预期：真实页 `div.card-act` 若是无标签的三个纯数字链接，现在会得到 `position` 归属的 `转发/评论/赞`；`0` 会保留为 0，不再和"没渲染"混淆。
- **未验证**：本轮零网络，真实页面的互动数字是否真的按 `转发→评论→赞` 顺序排列，只能等下一次真实搜索（需新批次额度）确认；若真实顺序不同，`count_source=position` 会让这一点一眼可见，便于下一轮按类型/`href` 校正。

## 5. 未做

未读/打印 cookie 值；未对真实页面截图；未重试、未消耗额度、未改账本；未改业务库/CSV/契约/小红书；未提交 git。
