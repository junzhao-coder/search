# B13：文案版本历史/回滚 + 导出记录去重 + 发布回填与变更提示（交付报告）

- 范围：`tools/workbench/`、`docs/validation/product-workflow/b13/`；未改业务库/CONTRACT/评分与货源 CSV
- 结论：三项缺口已补齐——文案有**不可变版本历史 + 回滚生成新版本**；导出记录按版本戳**幂等去重**；发布信息可回填且**变更后提示重核/重导**；隔离库闭环走查通过；六套测试全绿；已部署 5015（PID 128992）。

## 1. 数据模型（只新增表/增量列，不改既有列）

| 对象 | 说明 |
| --- | --- |
| 新表 `workorder_copy_version` | `id / workorder_id / version_no / snapshot_json / content_hash / created_at / created_by`，`UNIQUE(workorder_id, version_no)` |
| 新表 `workorder_publish` | `workorder_id(PK) / status / published_url / published_at / platform_note / sold_count / publish_version / updated_at` |
| `workorder_export` 增量列 | `dedupe_key`（`revision|copy_version|supply_id|supply_version`）、`publish_version`（记录导出时的发布版本），`CREATE INDEX IF NOT EXISTS` |

文案快照字段：`name / selling_points / includes / excludes / fmt / language / version / price_minor / delivery_note / aftersales_note / faq_json`；`content_hash` 判定「同内容不新增」。

## 2. 功能实现

| 功能 | 行为 |
| --- | --- |
| 版本生成 | 每次保存文案（证据 POST）后，若快照 hash 与最新版不同 → 插入 `version_no = max+1`（`created_by='ui'`），**同事务**提交；同内容重复保存**不新增** |
| 版本列表 | 详情页「文案版本历史」显示版本号/时间/来源/摘要+hash 前 10 位/「回滚到此版本」按钮 |
| 回滚 | `POST /worksheet/<id>/copy/rollback`（CSRF + revision 乐观锁）：内容取旧快照写回，**生成新版本**（`created_by='rollback:vN'`），历史不删除；revision 冲突 409、版本不存在 404、无 CSRF 403 |
| 导出去重 | `record_export` 先查同 `dedupe_key` 记录：命中 → 返回既有记录、`deduplicated=True`、**不新增行**；未命中 → 插入并记 `publish_version`；响应头 `X-WB-Deduplicated: true/false` |
| 发布回填 | `POST /worksheet/<id>/publish`（CSRF+同源）：状态仅 `未发布/已发布/已下架`；URL 仅 `http/https` 且含域名（≤500）；`sold_count` 非负整数；备注 ≤500；每次保存 `publish_version+1` |
| 变更提示 | 导出记录保存当时的 `publish_version`；详情页比较 `publish.publish_version > export.publish_version` → 显示「发布信息已变更，建议重核就绪并重新导出」 |

## 3. 隔离库闭环走查（真实 HTTP，`walkthrough.json`）

| 步骤 | 响应 | 关键结果 |
| --- | --- | --- |
| POST 新建自制单 | 200 | `wo:20261023-fc432ace`（格式合规） |
| POST 七项证据（含 demo 平台） | 200 | 详情 **7 通过 / 0 未通过** |
| GET export（预览） | 200 | 零写（不产生导出记录） |
| POST export/record 首次 | 200 | `X-WB-Deduplicated: false` |
| **POST export/record 重复** | 200 | **`X-WB-Deduplicated: true`，行数不变** |
| POST publish（已发布 + URL） | 200 | `publish_version=1` |
| POST 改文案（copy_version → v2） | 200 | 生成**版本 v2** |
| GET 详情 | 200 | **“上次导出：已失效 … 需重新检查并导出：工作单版本”**，版本历史 3 条可回滚 |
| POST export/record（新戳） | 200 | `deduplicated=false`，导出行 1→2 |
| POST 回滚 v1 | 200 | 生成 **v3**（`rollback:v1`），历史保留 |

最终计数：`workorder_export=2`、`workorder_copy_version=3`（版本序列 1,2,3）、`workorder_publish=1`。

截图：`shots/desktop_copy_history.png`（1160×309，版本历史+回滚按钮）、`shots/desktop_publish.png`（1160×200，发布回填）。

## 4. 测试（真实 subprocess，`execution_manifest.json`）

| suite | rc | summary |
| --- | --- | --- |
| `b13_copy_publish` | **0** | `Ran 8 tests — OK` |
| `b12_selfmade` | **0** | `Ran 10 tests — OK` |
| `b1_workflow` | **0** | `Ran 27 tests — OK` |
| `b3_export` | **0** | `Ran 24 tests — OK` |
| `workbench_all` | **0** | `Ran 131 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（48.4s） |

B13 八例：版本生成与同内容去重、回滚生成新版本且历史保留、回滚校验（409/404/403）、导出记录幂等（重复不增行 + 改文案后新增）、发布回填非法值 400（状态/URL 协议/非法 URL/负销量/非数字）、发布保存与变更提示（含页面横幅）、页面两区块存在、详情 GET 零写。B3 原「重复记录新增行」用例已按新语义更新为「同戳幂等 + 改版本新增」。

## 5. 部署与守卫

- 只停本工具 5015 进程后同端口重启：**PID 128992**；生产单 `wo:20261023-88ef9a66` 详情 200，**页面已含「文案版本历史」「发布回填」**；`/healthz` 仍 `app_id=workbench-opportunity/1`；5021 已停。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`；未改评分/货源 CSV、无新依赖。

## 6. 限制

1. 版本历史只快照**文案相关字段**（不含成本/门槛/证据类字段）；证据类改动仍以 `workorder_event` 记录，不生成文案版本。
2. 回滚只回写文案字段，不改货源/许可/成本/平台证据；回滚后可再点「记录本次导出」生成新戳。
3. 去重键是 `(revision, copy_version, supply_id, supply_version)`；若只改成本/证据（revision 会变）也会被视为新戳，属预期。
4. 发布状态仅三档枚举，不支持自定义状态；`published_at` 为自由文本（未做时区/格式强校验）。
5. 生产单当前 `platform_evidence` 仍为空 → 导出依旧 409；本次功能不改变就绪判定。
