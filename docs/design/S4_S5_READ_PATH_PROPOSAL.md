# S4/S5 读路径接入方案提案（设计稿：未实现、未联网、未接公共接口）

> 状态：**设计提案 / 未实现**。本文不修改 `app/**`、`tests/**`、`routes.py`、契约、迁移、台账与业务库；不联网、不加依赖；**不宣称任何方案已批准或可用**。
> 目的：为已验收的只读能力（匹配 `match_supplies`、排序 `rank_candidates`、每日摘要 `daily_digest`）比较三种**读路径接入方式**，给出推荐与全部待用户裁定项。
> 已读原件（只读）：`app/api/routes.py`（**实测 561 行 / 23 条路由**；`GET /api/candidates/<id>` 在 **L266**；**无 `/daily`**；未 import matching/ranking/daily）· `app/core/matching.py`（**实测 240 行**，只读纯函数）· `app/core/ranking.py`（**实测 280 行**，`rank_candidates(conn, *, as_of, limit=5, budget_minutes=30, scenario_params=None, rank_version="rank-v1")`，`as_of` 必填、`limit` **无校验**）· `app/core/daily.py`（**实测 56 行**，`daily_digest`）· [S4_MATCHING_SPEC.md](<S4_MATCHING_SPEC.md>) v2 · [S4_RANKING_SPEC.md](<S4_RANKING_SPEC.md>) v2（§6/§8）· `docs/validation/S4_MATCHING_ACCEPTANCE.md`（84 行）· `S4_RANKING_ACCEPTANCE.md`（83 行，结论"通过（仅限本实现与设计矩阵范围）……排序未接入任何读路径/流水线"）· `S5_DAILY_ACCEPTANCE.md`（79 行）· `CONTRACT.md`（公共接口约束见 §0.x 契约版本/只读条款；**未发现独立"公共 API 清单"章节**——§6 为存储/迁移/备份，执行批前须逐条核对）· `DEVELOPMENT_PLAN.md` · `PRODUCT.md` D04/D09。
> 技能：本会话**未暴露 `skill` 工具**，如实标注未加载。

## 1. 现状（能力已验收、读路径为零）

| 能力 | 代码 | 只读性 | 现状 |
| --- | --- | --- | --- |
| 匹配 | `matching.match_supplies(conn, candidate_id)` | 仅 SELECT；零写入已由 4 表全行快照验证 | **未接入任何 GET** |
| 排序 | `ranking.rank_candidates(conn, *, as_of, ...)` | 仅 SELECT + 只读调用 state/matching/scenario；全表快照验证 | **未接入 GET/流水线** |
| 每日摘要 | `daily.daily_digest(conn, *, as_of, ...)` | 仅调用 ranking；零写 | **未接入 GET/流水线** |
| 路由 | `routes.py` | — | **23 条**，无 matching/ranking/daily 相关端点 |

- 三函数均为**纯读**（不开事务、不建复核、不改状态/金额）；输出的分数/等级明确是"展示次序/提示"，**不是**收益、概率或证据。
- 未实现项：GET 接入、每日定时触发、提醒、界面、`insufficient/excluded` 明细、`budget_minutes` 语义。

## 2. 方案 A：扩展现有 `GET /api/candidates/<id>`

**请求**：沿用现有路径（可选新增查询参数 `include_matching=1`，默认关闭以减负载）。
**响应草案**（新增只读字段，不改既有字段语义）：
```
{"candidate": {...}, "derived_status": "...", ...（既有）,
 "matching": {"level_summary": {...}, "items":[{supply_offer_id, level, is_selected_by_g2,
               dims, reasons, gaps, gate_refs}], "gaps": [...], "display_note": "..."},
 "ranking_hint": {"rank_version":"rank-v1","score":78,"tier":"T2","reasons":[...],"next_action":"..."}}
```
- **错误码**：未知候选沿用既有 `404`；`include_matching` 非法值→`422 invalid_field`。
- **契约影响**：**修改既有公共响应**（向后兼容为"新增可选只读字段"，但契约若声明响应形状则**需契约修订/版本说明**）；需在契约中登记新字段与"分数非证据"的语义。
- **只读保证**：GET 零写（CONTRACT §3.3 读时纯计算）；不触发 `recompute` 写、不建复核。
- **性能**：每次详情请求 +1 次匹配（单候选 O(货源数) 查询）；若同时算排序分，需加载该候选的门槛/情景/matching（约 6–10 次查询/候选），**无需新索引**（均按 `candidate_id` 既有索引/唯一键）；建议 `include_matching` 默认关闭或在详情页懒加载。
- **测试计划**：隔离 DB 快照零写入；既有详情响应**逐字段兼容断言**（C1–C10 兼容矩阵）；新增字段断言；未知候选/非法参数 422/404；回滚 = 移除该查询参数分支（无迁移）。
- **优点**：复用既有路由，无新端点、无鉴权面扩张；单候选视角自然。
- **缺点/风险**：改变既有响应的稳定性预期；详情页变重；跨候选排序在详情里**不可解释**（只能给"该候选的名次/分数"，而名次依赖全库 as_of 与 limit——语义易误读）。

## 3. 方案 B：新增只读 `GET /api/daily?as_of=&limit=`

**请求**：`GET /api/daily?as_of=2026-10-20T00:00:00Z&limit=5`（`as_of` 必填；`limit` 默认 5、取值范围 1–20）。
**响应草案**：
```
{"kind":"daily_digest","as_of":"...","digest_date":"2026-10-20","rank_version":"rank-v1",
 "daily_limit":5,"pools":{...},"top":[{rank,candidate_id,tier,score,reasons,gaps,next_action}],
 "blocked":[...],"observing":[...],"exploring":[...],"omitted":[...],
 "counts":{...},"pending_confirmation":true,"budget_note":"...","display_note":"..."}
```
- **错误码**：`as_of` 缺失/非法→`422 invalid_field`；`limit` 非整数/越界→`422 invalid_field`；空库→`200` 空摘要（不 404）。
- **契约影响**：**新增端点须写入契约的公共 API 清单/版本说明**（若契约含 API 清单——当前**未发现独立清单章节**，执行批前须核对并补登记）；错误码沿用既有 422 风格。
- **只读保证**：同 B 实现只调用 `daily_digest`（纯读）；GET 零写、无 recompute 写、无复核创建。
- **性能**：一次请求 = 全库候选 × (recompute+effective_gate_status+matching+scenario) —— **O(N×各候选货源/成本行)**；N 大时延迟线性增长。**不需新表/索引**；可选进程内结果缓存（按 `as_of`+`limit`+库版本号，TTL 短，无新依赖），或限制 `limit≤20` 与请求频率。
- **测试计划**：隔离 DB + 全表快照零写；`as_of`/`limit` 校验矩阵；空库空摘要；同 `as_of` 确定性；既有 23 路由无回归（新端点不影响旧路径）；回滚 = 下线该路由（无迁移、无数据变更）。
- **优点**：与 D09"每日一次、最多 5 条重点机会、完整池可查"直接对应；读路径专一、语义清晰；无既有响应兼容负担。
- **缺点/风险**：新增公共端点 → 需契约/API 清单变更与鉴权面确认（当前应用无鉴权，**若未来加鉴权须一并设计**）；全库计算成本；`pending_confirmation`/启发式权重须在响应中显式标注。

## 4. 方案 C：仅文件导出（脚本 json/csv）

**形态**：独立运维脚本（如 `tools/export_daily.py`，**本提案不实现**）以固定 `as_of` 调用 `daily_digest`，写 `reports/daily-<date>.json|csv`。
- **输出草案**：与 B 的响应同构的 JSON（含 `kind/as_of/pools/top/blocked/omitted/counts/display_note`）+ CSV 平铺（rank,candidate_id,pool,tier,score,reason,next_action）。
- **错误码**：脚本退出码非 0 + stderr 说明（无 HTTP 错误码）。
- **契约影响**：**不改公共 API、不改契约**；仅新增运维脚本与**输出路径约定**（需用户确认目录、保留期、是否入库）。
- **只读保证**：脚本只读业务库（或只读副本）；不写库、不建复核；输出文件独立于业务数据。
- **性能**：与 B 相同（全库排序），但离线运行、可接受更长耗时；可加 `--limit`/`--as-of` 参数。
- **测试计划**：隔离 DB 跑脚本 → 全表快照零写、输出 JSON schema 断言、空库/非法参数退出码、同 `as_of` 幂等（同文件内容）；回滚 = 删除脚本与输出文件。
- **优点**：**零公共接口风险**、最快拿到"每日 5 条"可读证据、无需前后端改动；便于用户先验证排序质量。
- **缺点/风险**：引入运维脚本与文件路径/保留期约定；非交互（用户须打开文件）；未来若要界面仍要回到 A/B；脚本若误连业务库需只读保护。

## 5. 三方案对照与推荐

| 维度 | A 扩展详情 | B 新 `GET /api/daily` | C 文件导出 |
| --- | --- | --- | --- |
| 公共接口变更 | 有（改既有响应） | 有（新端点） | **无** |
| 契约修订 | 需登记新字段/版本说明 | 需登记端点 | 不需要 |
| 鉴权面 | 不扩张 | 需确认/未来加鉴权 | 无 |
| 实现/联调成本 | 中（改既有响应+兼容回归） | 中（新端点+校验） | **低** |
| 全库排序可解释 | 差（单候选视角） | **好** | 好 |
| 交付速度 | 中 | 中 | **快** |
| 回滚成本 | 低（去分支） | 低（下线路由） | 低（删脚本） |
| 主要风险 | 既有响应稳定性 | 成本/鉴权 | 非交互/路径约定 |

**推荐（组合、分阶段）**：
1. **先 C**：零公共接口风险即可获得"每日 5 条 + blocked + 完整池"的可读证据，用于用户确认排序权重与 `budget_minutes` 语义（也是 p4/p5 收口的快速验证）。
2. **再 B**：在 C 验证排序质量、且契约/鉴权口径确认后，新增只读 `GET /api/daily`（`as_of` 必填、`limit≤20`、零写、`pending_confirmation` 显式标注），作为长期主路径。
3. **A 暂缓**：除非产品明确要求在候选详情内嵌匹配结论；若做，须单独评估既有响应兼容与"名下名次易误读"问题。
- 推荐理由：C→B 的顺序把"公共接口风险"与"排序质量风险"解耦；A 的收益（单候选视角）不足以抵消其兼容与可解释性问题。

## 6. 待用户裁定项（未确认前**不实施**任何方案）

| # | 裁定项 | 默认建议 | 影响面 |
| --- | --- | --- | --- |
| 1 | **读路径方案**（A/B/C 或组合） | **先 C 后 B**（A 暂缓） | 是否改公共接口/契约/鉴权 |
| 2 | **排序权重数值**（`rank-v1` 启发式） | 先按现默认跑 C，观察结果后再调 | 排序次序与每日 5 条内容 |
| 3 | **`budget_minutes` 语义** | 保持"仅展示、不影响排序/条数"；若要求按预算截断须先改设计 §8/§9 | 每日展示条数与截断逻辑 |
| 4 | **每日上限**（5 条） | 按 PRODUCT D09 固定 5；不足按实展示 | 每日摘要内容与 omitted 口径 |
| 5 | **S3 受控 real 模式网络授权**（真实数据来源） | 维持未授权（仅离线/合成数据） | 排序/摘要的数据来源真实性 |
| 6 | 文件导出的目录/保留期/是否入库（方案 C 专属） | 默认 `reports/`（不入库、保留 30 天） | 运维约定与磁盘占用 |
| 7 | `GET /api/daily` 的鉴权策略（方案 B 专属） | 首版沿用现状（无鉴权），并登记为待办 | 安全边界 |

## 7. 未实现 / 未联网 / 未执行

- 本文**仅为提案**：未修改任何代码/路由/契约/迁移/台账/业务库；**未联网、未跑测试、未新增依赖**。
- 三方案**均未实现**：无 `include_matching` 参数、无 `/api/daily` 端点、无导出脚本、无鉴权设计、无缓存。
- 未覆盖：真实运行证据、界面、每日定时触发与提醒、`insufficient/excluded` 明细、契约修订文本。
- **声明**：不宣称任何方案已批准/可用，不宣称 S4/S5 完成；执行任一方案均须用户对 §6 逐项确认后另立实现批（含契约修订与验收矩阵）。
