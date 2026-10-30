# B3：上架准备检查 + 人工上架包导出（交付报告）

- 执行者：C；范围：`tools/workbench/`、`docs/validation/product-workflow/b3/`
- 入口：**http://127.0.0.1:5015/worksheet**（部署 PID **104568**，仅绑 127.0.0.1）
- 结论：**就绪检查与导出结构已实现并阻断到位**；B2 结论（公开货源多为禁止/不明）未改变，**没有把任何真实商品标成就绪**；生产库当前无工作单（`runtime/workflow.sqlite3` 不存在）。

## 1. 就绪检查（服务端推导，7 项）

| key | 检查项 | 通过条件 | 缺项提示示例 |
| --- | --- | --- | --- |
| `specs` | 产品规格完整 | `name/use_case/deliverable/target_platform` 非空 | 缺少：拟交付物 |
| `supply` | 已选货源 | `selected_supply_id` 非空 | 未选货源（selected_supply_id 为空） |
| `license` | 许可三档均允许 | `supply_license_{commercial,redistribute,resell}` 均为 `yes` | 未通过：可商用=unknown、可再分发=no… |
| `sample` | 样品/交付入口已核验 | `sample_status=verified` | 未核验样品/交付入口 |
| `cost` | 成本已知 | `cost_minor>0` 或 `cost_known=yes` | 成本未知 |
| `platform` | 目标平台条件有证据 | `platform_evidence` 非空 | 缺少目标平台条件证据 |
| `copy` | 文案定稿 | `copy_status=final` 且 `copy_version` 非空 | 文案未定稿 |

- `readiness(record)` 是**纯函数**，`overall_ready = all(checks.ok)`；页面不提供任何“标记完成/就绪”的入口。
- 证据通过 `POST /worksheet/<id>/evidence` 录入（CSRF + revision 乐观锁 + 同事务审计），**证据通道拒绝 `status`、`gate_*`、`ready/verified`、`snapshot` 等字段（403）**，与 B1 的越级防护一致。

## 2. 库结构（只 ALTER，不动既有数据）

`init_schema` 内以 `PRAGMA table_info` 守卫追加 16 列（`supply_license_*`、`supply_version`、`sample_status/ref`、`cost_minor/cost_known`、`platform_evidence`、`copy_status/copy_version`、`selling_points`、`price_minor`、`delivery_note`、`aftersales_note`、`faq_json`），并新增 `workorder_export`（`revision/copy_version/supply_id/supply_version/stamp_hash/content_sha256/created_utc`）。**不改 B1 既有列、不清空数据**（隔离库测试已验证可重复初始化）。

## 3. 导出

- `GET /worksheet/<id>/export?format=md|json`
  - 未就绪 → **409** + 逐条阻断项（HTML，含“未选货源/许可三档/样品/成本未知/平台/文案未定稿”等原因）。
  - 就绪 → 生成文件并记录导出：`Content-Disposition: attachment; filename="wo-…-rN.md|json"`，响应头带 `X-WB-Revision / X-WB-Stamp / X-WB-Copy-Version / X-WB-Supply`。
- **买家可见白名单**：`title`、`selling_points`、`contents{includes,excludes}`、`format{fmt,language,version}`、`price{amount_minor,currency,note}`、`delivery`、`aftersales`、`faq`；结构自带 `buyer_visible_fields`。
- **导出前自检**：若内容出现 `cost/profit/margin/score/internal/raw_ref/snapshot/成本/利润/打分/毛利` 等内部标记 → 直接拒绝导出（`export_internal_leak`），防止越界。
- **版本戳**：`revision`、`copy_version`、`supply_id`、`supply_version`、`generated_utc`、`contents[]` 与 `stamp_hash`；每次导出写 `workorder_export`。详情页比对最新戳：任一维度变化 → 旧导出标 **已失效** 并提示需重检重导。

## 4. 测试（真实 subprocess + manifest）

`run_suites.py` 用 `subprocess.run(capture_output=True)` 执行并写 **`execution_manifest.json`**（argv/cwd/start_utc/end_utc/returncode/summary_lines + 原始 stdout/stderr 文件）：

| suite | returncode | summary |
| --- | --- | --- |
| `b3_export` | **0** | `Ran 9 tests — OK` |
| `b1_workflow` | **0** | `Ran 27 tests — OK` |
| `workbench_all` | **0** | `Ran 98 tests — OK` |
| `project_full` | **0** | `Ran 334 tests — OK`（48.1s） |

**B3 九例覆盖**：全缺态（7 项中 6 项阻断 + 导出 409 且列出原因）、详情页检查表与禁用按钮、部分缺逐项翻绿、**伪造就绪**（`ready/status/gate_*` → 403 且状态不变）、齐全后 MD/JSON 导出（白名单、无内部字段）、未就绪→就绪的导出切换、**版本戳变化后旧导出失效**（改 `copy_version` → 旧戳失效、重导后恢复有效）、证据通道 revision 校验与回滚、详情页 GET 零写。

## 5. 截图（隔离库/临时目录）

| 文件 | 尺寸 | bytes | sha256 前 16 |
| --- | --- | --- | --- |
| `shots/desktop_detail_not_ready.jpg` | 1440×900 | 80,500 | `0f825aab6e74e34f…` |
| `shots/desktop_detail_ready.jpg` | 1440×900 | 80,508 | `b0a13c79359faa55…` |
| `shots/mobile_detail_ready.jpg` | 390×844 | 34,718 | `e9ff5c175df580f2…` |

`shots_manifest.json` 自校验 **3/3 一致**；三个视口 `overflowX=false`（1440/390）。截图来自端口 5018 的隔离实例（测试库与密钥在系统临时目录，跑完删密钥）。

## 6. 部署与守卫

- 只停本工具 5015 进程后同端口重启：**PID 104568**；`/worksheet` 200、导航含「商品工作单」；`/healthz` 仍含 `app_id=workbench-opportunity/1`；5018 已停。
- 生产库 `tools/workbench/runtime/workflow.sqlite3` **不存在**（0 条工作单）——未替用户创建任何候选或证据。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scoring/scores.csv ab0c3546…`、`sourcing/sources.csv 13679b60…`；未改评分/货源原始 CSV、未新增依赖。

## 7. 限制与未覆盖

1. **没有真实货源可用于验证**（B2：公开货源多为禁止/不明；StudySphere 覆盖范围待确认）。因此本批只用隔离 fixture 造证据，**没有把任何真实商品标成就绪**；证据值（许可三档/样品/成本/平台条件）是**人工填写并留痕**，不代表平台已核验。
2. 导出中的价格是**建议售价**（页面与文件均注明“最终以卖家填写为准”），不是成交价，也不含利润测算。
3. 不包含：自动抓取平台条款、样品自动验货、上架动作、平台 API 对接（均为后续阶段）。
4. 版本戳失效判定基于 `revision/copy_version/supply_id/supply_version` 四项；**内容字段（卖点/FAQ 等）改动也会通过 revision 体现**，但若直接改库绕过应用则不在保护范围。
5. 生产库为 0 条，页面在你首次「选为候选商品」后才会出现检查表与导出按钮。

---

# rev5 窄修（截图覆盖检查区块 / 内部标记 409 / 点名证据）

## 1. 截图改为「检查区块裁剪」，两态 × 桌面/手机（共 4 张，取代旧的首屏图）

做法：`section[aria-labelledby="h-ready"]` 的 `getBoundingClientRect()` 换成**页面坐标**，用 CDP `Page.captureScreenshot(clip=Viewport(...), capture_beyond_viewport=True)` 裁剪该区块（PNG）。manifest 记录 `selector / clip{x,y,width,height,scale} / scroll_y / method / 区块标题 / hasChecks / hasBlockers / hasDisabled / hasExportLink`，并自校验：**图片尺寸 == clip 尺寸**、sha256 与磁盘一致、**同视口两态 sha 不同**。

| 文件 | 尺寸 | bytes | sha256 前 12 | 关键标记 |
| --- | --- | --- | --- | --- |
| `shots/desktop_checks_not_ready.png` | 1160×749 | 83,205 | `0c518cb90a07` | 检查表 + 阻断列表 + **禁用按钮**，无 export 链接 |
| `shots/desktop_checks_ready.png` | 1160×629 | — | `352645c87064` | 检查表 + **可点导出链接** |
| `shots/mobile_checks_ready.png` | 362×746 | — | `dc34cbe1d991` | 390×844 视口下裁剪，**可导出** |
| `shots/mobile_checks_not_ready.png` | 362×1307 | 80,331 | `a0ff18b477c2` | 390×844 视口下裁剪，**禁用按钮 + 阻断项** |

`shots_manifest.json`：`verification.checked=4 / failed=0 / ok=true`；`state_distinct` 两对均为 `true`（证明未就绪/就绪是两张不同图）。两态用**两个不同工作单**（`submit_key` 不同，避免幂等命中同一条）。

## 2. 导出内部标记自检：500 → 409 业务拒绝

`readiness.build_export()` 命中内部标记时抛 `Reject("export_internal_leak", …, 409)`；`GET /worksheet/<id>/export?format=json` 实测返回 **409**（页面含 `export_internal_leak`），不再 500。

## 3. 点名证据（用例名 → 真实状态码）

| 用例 | 场景 | 结果 |
| --- | --- | --- |
| `test_evidence_revision_and_validation` | `revision=999` / `cost_minor=abc` | **409** / **400**，库内 revision 未变 |
| `test_forged_ready_rejected_and_state_unchanged` | `ready=1`、`status=ready`、`gate_cost=verified` | **403**，状态与 `selected_supply_id` 未变 |
| `test_csrf_required_and_origin_checked`（B1 套件） | 缺失/错误 CSRF、跨站 Origin | **403** |
| `test_unicode_and_bad_csrf_are_403_not_500`（B1 套件） | Unicode/超长/含 `\u0000` token | **403**（非 TypeError） |
| `test_export_internal_marker_rejected`（新增） | 卖点含「毛利」 | **409 `export_internal_leak`**（HTTP 亦 409） |

## 4. 复跑与部署

- 仅跑 B3 专项（真实 subprocess + `execution_manifest_b3_only.json`）：`b3_export` **rc=0，`Ran 10 tests — OK`**（原 9 例 + 新增内部标记用例）。
- 只停本工具 5015 进程后同端口重启：**PID 85744**；`/worksheet` 200、`/healthz` 含 `app_id=workbench-opportunity/1`；5018 已停。
- 守卫未变：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…`、`sources.csv 13679b60…`。
