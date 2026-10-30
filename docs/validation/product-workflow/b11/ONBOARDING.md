# 新商品接入清单（ONBOARDING）

> 任意新商品接入这套流程时，按下表填字段即可。**标「用户」的必须你本人给**；标「系统」的由程序校验/生成。
> 「缺了会怎样」列即为七项就绪检查的阻断后果——**系统不会因为你点了什么就放行**。

## 1. 规格字段（阶段 1，用户填 → 系统校验）

| 字段 | 谁填 | 示例值 | 判定标准 | 缺失后果 |
| --- | --- | --- | --- | --- |
| `name` | 用户 | 学习计划 Excel 模板｜课程/考试倒计时/周计划/复习进度 | 1–80 字，非空 | `specs` 不通过 |
| `use_case` | 用户 | 学习计划 / 考试倒计时 / 复习进度 | 1–120 字，说清用途 | `specs` 不通过 |
| `target_buyer` | 用户 | 学生 / 备考人群 | ≤80 字 | 不阻断（建议填） |
| `deliverable` | 用户 | Excel .xlsx 单文件（5 表 / 50 公式） | 1–120 字，必须写清交付形态 | `specs` 不通过 |
| `fmt` | 用户 | `xlsx` / `md` / `pdf` / `psd` | ≤40 字 | 不阻断（导出会显示空） |
| `language` | 用户 | 中文 | ≤20 字 | 不阻断 |
| `version` | 用户 | v1 | ≤20 字 | 不阻断 |
| `includes` | 用户 | 5 张表 + 50 个公式 + 下拉/条件格式 + 虚构示例 | ≤600 字 | 不阻断 |
| `excludes` | 用户 | 不含宏/外部链接/三场景规划版/代做 | ≤600 字 | 不阻断 |
| `target_platform` | 用户 | `xianyu` | **仅允许 xianyu** | `specs` 不通过 / 400 |

## 2. 货源与证据字段（阶段 2，用户填 → 系统校验）

| 字段 | 谁填 | 示例值 | 判定标准 | 缺失后果 |
| --- | --- | --- | --- | --- |
| `selected_supply_id` | 用户 | `self:c3-v1`（自制）或外部货源 ID | 非空 | `supply` 不通过 |
| `supply_version` | 用户 | `c3-v1` | 自由文本（用于版本戳） | 影响戳失效判定 |
| `supply_license_commercial` | 用户 | `yes` | **必须 yes** | `license` 不通过 |
| `supply_license_redistribute` | 用户 | `yes` | **必须 yes** | `license` 不通过 |
| `supply_license_resell` | 用户 | `yes` | **必须 yes** | `license` 不通过 |
| `sample_status` | 用户 | `verified` | **必须 verified** | `sample` 不通过 |
| `sample_ref` | 用户 | `b7:selfcheck 17/17（结构自检；非真实 Excel 打开）` | 说明核验方式与范围 | 不阻断（但应写清） |
| `cost_minor` | 用户 | `500`（¥5，**假设**） | 正整数（分）或 `cost_known=yes` | `cost` 不通过 |
| `cost_known` | 用户 | `yes` | 与 `cost_minor` 二选一即可 | 同上 |
| `platform_evidence` | 用户 | 条款 URL / 截图编号（**不得填 synthetic**） | **非空** | `platform` 不通过 → 导出 **409** |

> 自制商品注意：许可三档是**作者对自己作品的权利声明**，不是平台许可；平台类目/虚拟交付仍需单独核验。

## 3. 文案与交付字段（阶段 4，用户填）

| 字段 | 谁填 | 示例值 | 判定标准 | 缺失后果 |
| --- | --- | --- | --- | --- |
| `copy_status` | 用户 | `final` | **必须 final** | `copy` 不通过 |
| `copy_version` | 用户 | `c3-v1-copy` | 非空（进版本戳） | `copy` 不通过 |
| `selling_points` | 用户 | 每行一条，共 5 条 | 每条可被样品/公式证明 | 不阻断（导出会空） |
| `price_minor` | 用户 | `990`（¥9.9，**假设**） | 非负整数（分） | 不阻断（导出显示“未填写”） |
| `delivery_note` | 用户 | 交付 .xlsx + usage.md；不代登录、不算第三方素材 | ≤2000 字 | 不阻断 |
| `aftersales_note` | 用户 | 售后范围/时限未定；不含代做/代填/维护 | ≤2000 字 | 不阻断 |
| `faq_json` | 用户 | `[{"q":"需要什么软件？","a":"Excel 或 WPS"}]` | 合法 JSON 数组 | 不阻断 |

## 4. 最小可跑通路径

**只要 4 个字段**就能建单并看到“还缺什么”（不要求先有货源）：
`name` + `use_case` + `deliverable` + `target_platform` → 详情页显示 **1 通过 / 6 未通过**，每项给出具体缺项。

**要到“导出前一步”**（六项通过、只差平台）需再补：
`selected_supply_id` + 许可三档 `yes` + `sample_status=verified` + `cost_minor`（或 `cost_known=yes`） + `copy_status=final` + `copy_version` → **6/7 通过**，导出会因 `platform_evidence` 为空返回 **409**。

**要到“可导出”**：再把 `platform_evidence` 填成**真实依据**（条款 URL/截图编号）→ **7/7**，此时：
- `GET /export?format=md|json` 只生成内容（**不写库**，头 `X-WB-Recorded: false`）；
- 点「记录本次导出」（`POST /export/record`，需 CSRF）才写 1 行导出记录（头 `true`）；
- 之后任一 `revision / copy_version / supply_id / supply_version` 变化 → 旧导出标**已失效**，需重新记录。

## 5. 接入检查清单（照着打勾即可）

- [ ] 4 个必填规格字段已填（能建单）
- [ ] 货源/许可/样品/成本/文案 5 类证据已填（6/7 通过）
- [ ] `platform_evidence` 填的是**真实依据**，不是 `synthetic-demo://`
- [ ] 卖点每条都能被样品/公式证明，无夸大/绝对化/代做/收益承诺
- [ ] 定价与售后口径已确认（价格是假设，不是成交价）
- [ ] 导出后用「记录本次导出」留档；发布由你手动完成，并回填链接与时间
