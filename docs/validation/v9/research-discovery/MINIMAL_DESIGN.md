# 最小设计：需求证据 → 方向卡 → 品类台账 → 工作单 + 可暂停轮次

> 仅设计/离线 synthetic 验证，**不是已实现系统**；不新增依赖、不接业务库。目标是让本地单用户能解释“为什么合并/不合并、为什么续跑、失败后怎么办”，而不是先上向量库/任务队列。

## 1. 数据关系（最小表）

```text
evidence ──< direction_evidence >── direction_card
   │                                      │
   └──< discovery_event >── category ─────┘
                              │
                              ├── category_alias
                              ├── category_event (merge/split/exclude/include/undo)
                              └── workorder (仅引用确认后的 direction/category)

round ──< round_item
```

| 表 | 最小字段 | 说明 |
| --- | --- | --- |
| `evidence` | `id, source_kind(demand/supply/dev_ref), platform, url, quote, locale, market(domestic/global), captured_at, content_hash, raw_ref` | 原文引用 + 来源；不把摘要当原文 |
| `direction_card` | `id, job_statement, buyer, task, deliverable, format, locale, status(draft/confirmed/rejected), evidence_ids, notes` | 一个方向可引用多条证据；平台不是身份 |
| `category` | `id, canonical_label, identity_key, audience, task, deliverable_family, locale, status(active/merged/excluded), merged_into, created_at` | **平台/标题/格式/载体不进 identity_key** |
| `category_alias` | `category_id, alias_norm, source_evidence_id, created_at` | 同义改写/历史别名；可撤销 |
| `discovery_event` | `id, category_id, kind(new/update/ambiguous/merge/split/exclude/include), evidence_id, before_json, after_json, actor, at, undo_of` | 只追加；用于审计/撤销 |
| `review_queue` | `id, candidate_a, candidate_b, reason, evidence_ids, status(pending/accepted/rejected)` | 不确定项进人工，不丢弃 |
| `workorder` | `id, direction_id, category_id, stage, status, revision` | 只从 confirmed 方向建；不复制平台身份 |
| `round` | `id, status, budget_json, cursor_json, idempotency_key, started_at, ended_at, error_count` | 一轮有界任务 |
| `round_item` | `round_id, item_key, state(pending/processing/done/failed), attempts, last_error, updated_at` + `UNIQUE(round_id,item_key)` | 断点/重放的最小粒度 |

- 现有 `workorder/readiness` 只作为下游引用；本设计的 research 表建议放**独立** `runtime/research.sqlite3`，不写 `instance/app.db`、不改既有迁移。
- 不建全文/向量索引；证据先按 `content_hash` 与 `(platform,url)` 去重。

## 2. 身份与匹配（不做未经验证的分数公式）

### 2.1 身份键

```text
identity_key = sha256(canonical_json({
  audience, task, deliverable_family, locale
}))
```

- `audience`：学生/备考/自由职业者/小商家等**人群**；
- `task`：考试倒计时/周计划/客户跟进/会议纪要等**任务**；
- `deliverable_family`：Excel 模板/Notion 模板/提示词包/素材包等**交付族**；
- `locale`：中文/英文等**语言市场**。
- **不包含**：platform、标题、封面、文件名、文件格式细分（xlsx/csv 可同族）、来源作者、价格。
- 只改标题/格式/载体 → 不改 identity_key → 不算新品。

### 2.2 匹配顺序

1. **exact identity_key** → 同一 category；
2. **exact alias**（人工确认过的同义写法）→ 同一 category；
3. 字段有实质差异（audience/task/deliverable_family 任一不同）→ **不同 category**；
4. 只有字符串相似、但字段不能证明同一 → `review_queue`，**不自动合并**；
5. 新证据找不到匹配 → `discovery_event(new)`，进人工确认，不直接建工作单。

> 不使用“组均分 × log/AND 阈值”作为分类/合并依据；分类是身份/证据问题，不是排序分数。需要排序时只用 `evidence_count`、`last_seen` 做**复核优先级**，不作为事实判定。

### 2.3 四种反例

| 反例 | 处理 |
| --- | --- |
| **同需求跨平台**：X 帖“need Notion study planner” + 闲鱼“Notion 学习计划模板” | 同 audience/task/deliverable_family/locale → 同一 category；两条 evidence 的 platform 不同；不因平台不同新建 |
| **同义改写**：`Notion study planner` / `学习计划 Notion 模板` / `study timetable template` | 人工确认后写 `category_alias`；后续 exact alias 命中；不改 canonical 身份；没有确认就进 review |
| **同大类不同任务**：`学生考试倒计时` vs `自由职业者客户 CRM` | 都是 Notion/Excel 模板，但 audience/task 不同 → **不同 category**；不能按“模板”大类合并 |
| **旧品类新证据**：旧闲鱼 listing + 新 X 需求原话 | 同 identity_key → `discovery_event(update)` 追加 evidence、更新 last_seen；**不新建**；旧证据保留 |

补充：
- **只改标题/格式/载体**（如 xlsx→csv、改封面/文件名）→ same deliverable_family，`update`，不新建。
- **排除可恢复**：`status=excluded` + reason，不删除 evidence/alias；`include` 事件恢复。
- **合并/拆分可撤销**：
  - merge：from→to，写 `category_event(merge, before/after)`，from 保留 `merged_into`，evidence/alias 仍可追溯；
  - split：新建 category，按 evidence 子集重分配，写 `category_event(split)`；旧 category 保留；
  - undo：按 event `before_json` 反向操作，**不硬删历史**；冲突进 review。

## 3. 发现/工作单的最小流转

```text
evidence (raw quote)
  → direction_card (draft → confirmed by user)
  → category match:
       exact/alias → attach
       field mismatch → new category (pending review)
       similarity only → review_queue
  → discovery_event(new/update/ambiguous)
  → workorder (only confirmed direction+category; existing readiness gates separate)
```

- **方向卡**必须有 1 条以上原文 evidence；生成文案/标题不覆盖原话；用户确认后才可用于工作单。
- **新发现/旧更新/待判重**：
  - new：无 exact/alias；
  - update：同 identity_key + 新 evidence；
  - ambiguous：相似但字段冲突/别名冲突；
  - 三者都保留 evidence，不丢弃。
- **工作单**只引用确认后的 IDs；后续 revision 变化按既有 workorder 语义；本设计不替代基线 readiness 判定。

## 4. 主动开轮/暂停续跑

### 4.1 状态机

```text
draft → running → (complete | partial | paused | failed)
paused → running (resume)
partial → running (retry failed/pending)
running → paused (user/预算/时间)
```

- `round`：`budget_json = {max_items,max_pages,max_seconds,max_errors}`；
- `cursor_json`：当前页/偏移/最后 item_key；只保存**已提交**位置；
- `idempotency_key`：同一用户请求/同一轮的唯一键；重复 start 返回既有 round；
- `round_item`：每个 item 的状态/attempts/last_error，唯一键防重复。

### 4.2 单条处理事务（伪代码）

```python
for item in source.page(cursor):
    if paused or budget_exhausted(): break
    try:
        with db.transaction():
            evidence_id = upsert_evidence(item)      # content_hash/platform+url
            upsert_round_item(round_id, item.key, "done")
            advance_cursor(item.key)                 # 只提交成功/确定跳过
    except Exception as exc:
        record_round_item_failed(item.key, exc)
        error_count += 1
        if error_count > max_errors: status = "partial"; break
```

- **重放**：`upsert_evidence` 按 `content_hash`/`(platform,url)` 幂等；`round_item` 唯一键决定是否已处理；同一 item 不重复计数/重复写证据。
- **部分失败**：失败 item 记 `failed`，不伪装成功；继续/停止由 `max_errors` 决定；最终 `partial`，不是 `complete`。
- **中断恢复**：`running/paused/partial` 重新读取 cursor；已 done items 跳过；failed/pending 可重试；budget 重新按剩余额度计算（不重置已用计数）。
- **暂停**：在 item 边界检查 `status=paused`，不再取下一页；不依赖强杀进程；清理连接后退出。
- **边界**：`max_pages`/`max_items`/`max_seconds` 硬停；不会无限采集；错误率超限转 `partial/failed`。
- **语义取舍**：至少一次处理 + 幂等 upsert；不承诺跨进程 exactly-once；以 `round_item/evidence` 唯一键消除重复副作用。

### 4.3 复用与新建

| 复用 | 新建（后续，不在本任务实现） |
| --- | --- |
| Flask 应用工厂、现有 SQLite、标准库 `sqlite3`/`hashlib`/`json` | `tools/research/` 下的小模块：`rounds.py`（状态机）、`identity.py`（normalize/alias）、`discovery.py`（事件/撤销） |
| 现有 workorder/readiness 只作为下游引用 | 独立 `runtime/research.sqlite3`；不迁移/不改 `instance/app.db` |
| 现有测试风格 unittest | 新增 pure-function 测试 + 临时 SQLite 测试；不引入 Celery/Redis/向量库 |

## 5. 被否决的替代方案

| 方案 | 否决原因 |
| --- | --- |
| 直接引入 Scrapy | Twisted/lxml/parsel 等重依赖；JOBDIR 是单 job 的框架语义，嵌入小工具体系成本高；只借鉴概念 |
| 默认引入 RapidFuzz | C++ 扩展/平台轮子；相似度只给候选，不能证明同一品类；60 条规模无需 |
| 向量库/embedding 自动聚类 | 不可解释、阈值敏感、误合并难撤销；无原文/证据审计；新增依赖与运维 |
| Redis/Celery/RQ/APScheduler | 本地单用户不需要 broker/daemon；持久化/部署复杂；与 Flask+SQLite 基线不一致 |
| 自动按相似度阈值合并 | 同大类不同任务会误并；无法区分“同义改写”和“不同人群/任务”；不可逆风险 |
| “组均分×log/AND 阈值” | 本任务没有验证过该公式；会把身份问题伪装成分数；不采用 |

## 6. 最小推荐与验证顺序

1. **先做**：evidence + direction_card + category/category_alias + discovery_event + review_queue + workorder 引用；**不建**向量/任务队列。
2. **再做**：`round/round_item` 状态机；单进程 CLI/Flask 手动触发，预算硬停。
3. **验证**：
   - 用 `synthetic_examples.py` 跑四反例（跨平台/同义/不同任务/旧证据）；
   - 标注 20–30 条真实证据，人工检查合并/拆分/排除/撤销；
   - 两轮人为在 item 3 中断，恢复后核对 evidence 行数、round_item done、无重复；
   - 检查 research 库与业务库隔离；失败项保持 failed/partial。
4. **不在本阶段做**：自动发布、自动采购、平台登录、真实用户抓取、重型框架。

## 7. 未验证/待实验

- 中文同义词/缩写是否需要分词（本设计先用 exact/alias + 人工，不引入分词库）。
- 旧品类新证据的 `last_seen` 是否驱动列表排序（只影响复核顺序，不影响身份）。
- 合并/拆分 event 的并发控制（SQLite `BEGIN IMMEDIATE` + revision 待实验）。
- 轮次预算与 timeout 的具体数值需在真实采集前由用户确认。
