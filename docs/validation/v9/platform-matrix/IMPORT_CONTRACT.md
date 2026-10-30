# 导入契约：闲鱼 20 条 → 统一信号（imported）

> 样本：`tools/platform-login/data/xianyu_items.jsonl`（**只读**，20 行；文件 sha `c70f1580…`）。
> 本文件不复制原始标题/正文到业务库，也不写 `instance/app.db`、`workbench.sqlite3` 或既有 CSV；仅定义 imported 映射与缺口。

## 1. 实读事实（20 行，按实际字段）

| 实际字段 | 覆盖 | 说明 |
| --- | --- | --- |
| `href` | 20/20 | 形如 `https://www.goofish.com/item?id=<id>&categoryId=...`；`id` 可解析 20/20，且 20 个唯一 |
| `title` | 20/20 | 平台展示标题（可能截断）；不是正文全文 |
| `price` | 20/20 | 均为 `¥ 1` 展示价；**引流价**，不是成交价 |
| `raw_text` | 20/20 | 卡片文本（截断到约 200 字）；含 `N人想要`、地区/发货文案等 |
| `platform` | 20/20 | `xianyu` |
| `item_id` | **0/20 独立列** | 无该列；从 `href` 的 `id` 派生（20/20），不能假装源字段 |
| `wants` | 16/20 | 从 `raw_text` 的 `N人想要` 派生；合计 **8093**，不是成交/订单 |
| `effective_price` | 20/20 派生 | 有效价 **1.00/1.09/1.10/1.88**；由 `¥1` + 小数后缀派生 |
| `reference_price` | 3/20 派生 | 9.9 / 9.89 / 699，来自 `raw_text` 的第二个 `¥` 数；不是成交价 |
| `lang` | 20/20 启发式 | 文本含 CJK → `zh`；**源文件无 lang 字段**，标记 `lang_source=heuristic` |
| `collected_at` | **0/20 行级** | 源文件无每条时间；只有批次时间 `2026-10-22T08:46:35Z`（`e2e/data/xianyu_summary.json`），标 `collected_at_scope=batch` |
| 评论/正文/楼中楼 | 0/20 | 无评论、无评论者、无楼中楼字段 |
| 作者/发布时间/销量/成交/类目/卖家 | 0/20 | 源文件无；不得推断 |
| `raw_sha256` | 20/20 | 每行原始 JSON 字节的 sha256（见 `import_sample_stats.json`），用于审计，不用于去重身份 |

- 文件级 sha256：`c70f15801db70d9c0a170024c24ddd18ab9cedf056f21c708207066915c851e0`。
- 样本文件是当时采集产物，**不是平台实时状态**；不重新采集、不探测。

## 2. 统一信号字段与映射

```text
signal = {
  platform: "xianyu",
  native_id: "1052243348747",       # 从 href 的 id 派生
  parent_native_id: null,            # 列表没有父评论；缺失
  url: "https://www.goofish.com/item?id=...",
  quote/text: raw_text,              # 原文卡片文本（截断）；不改成摘要
  title: title,                      # 可选展示字段
  lang: "zh",                        # heuristic，不是源字段
  collected_at: "2026-10-22T08:46:35Z", # 批次时间，row-level unknown
  listed_price: 1.0,                 # CNY
  effective_price: 1.0,              # 1.00/1.09/1.10/1.88
  wants: 2519,                       # 可空；兴趣代理，不是成交
  origin_kind: "imported",           # 不是 real/synthetic
  raw_sha256: "...",                 # 原始行字节哈希
  content_hash: "..."               , # 规范化内容哈希（见 §4）
  batch_id: "xianyu-20261022T084635Z"
}
```

| 目标字段 | 来源/派生 | 可映射 | 缺失/不可得 |
| --- | --- | --- | --- |
| `platform` | `platform` | 是 | — |
| `native_id` | `href` 的 `id` | 是（20/20） | 无独立列；解析失败应拒绝 |
| `parent_native_id` | — | 否 | 列表无父评论；`null` |
| `url` | `href` | 是 | `categoryId` 非身份；可保留或规范化 |
| `quote/text` | `raw_text` | 是 | 被采集脚本截断（约 200 字），不是详情全文 |
| `lang` | CJK 启发式 | 部分 | 不是平台字段；`lang_source=heuristic` |
| `collected_at` | 批次 summary | 部分 | 无行级时间；`collected_at_scope=batch` |
| `listed_price` | `price` | 是（1.0） | 引流价，不是成交价 |
| `effective_price` | raw 的小数后缀 | 是（1.0–1.88） | 仍是展示价，不是成交价 |
| `wants` | `raw_text` | 16/20 | 4 条缺失；不是订单/付款 |
| `origin_kind` | 固定 `imported` | 是 | 业务 `data_origin` 不支持 imported（见 §3） |
| `raw_sha256` | 原始行 | 是（20/20） | 换行/格式变化会改变；仅审计 |
| `content_hash` | 规范化字段 | 是 | 见 §4；不是平台 ID |

- 不映射：`author`、`published_at`、`sales`、`real_transaction`、`comments`、`parent_comment`、`category`、`seller`、`inventory`。源中没有就是没有，不能用标题猜。
- `listed_price` 与 `effective_price` 都是 CNY；`reference_price` 单独保留，**不**作为售价/毛利输入。

## 3. origin 与业务库边界（关键）

- 业务核心 `app/core/importer.py:51` 的 `DATA_ORIGINS={"real","synthetic"}`；`0001` 迁移的 `data_origin` CHECK 也只允许这两个值（`BASELINE.md:103-108`）。
- **imported 不是 real，也不是 synthetic**：本契约的 `origin_kind=imported` 只能落在 V9 独立信号库；不得静默写成 `real` 或 `synthetic` 混入四门/导入器。
- 如果未来桥接到业务核心，必须**显式迁移/批准** origin 三态（影响 7 表 CHECK/导入器/测试）；本轮不改 schema。**导入 ≠ 自动采集**，也不代表平台实时或授权。
- 20 条样本不写入 `instance/app.db`、`tools/workbench/runtime/workflow.sqlite3`、既有 CSV；本目录 `import_sample_stats.json` 只含哈希/计数，不含全文标题。

## 4. 去重键建议

| 键 | 用途 | 规则 |
| --- | --- | --- |
| **主身份** `(platform, native_id)` | 同一商品/信号 | 稳定；同一 native_id 的标题/价格变化是 update，不是新行 |
| **内容版本** `content_hash` | 判断内容是否更新 | `sha256(canonical({platform,native_id,text,listed_price,effective_price,wants}))`；变化只更新版本/证据，不改身份 |
| **URL 辅助** `(platform, canonical_url)` | 无 native_id 的源 | URL 先移除 tracking/`categoryId` 等非身份 query；本样本全部有 native_id，URL 仅辅助 |
| `raw_sha256` | 审计原始行 | 不用于去重：同一内容重新格式化会变 |

- 标题改写、价格变化、want 变化 → **update/version**，不是新商品；平台不同不作为身份拆分（平台是来源，不是品类）。
- 同一 URL 换 native id / 无法解析 id → 进人工复核，不能自动合并。

## 5. 下一阶段最小适配器（3 平台，评论源 1 + 交易源 1）

| 平台 | 角色 | 最小动作 | 需用户配合 | 风险/门槛 |
| --- | --- | --- | --- | --- |
| **B站** | 评论源（1） | 单公开视频 `view` + 评论第 1 页 `sort=2` + 一个子回复入口；低量、只读 | 无需登录/扫码（公开样本）；提供视频 URL | 第 2 页空、翻页未成立；楼中楼只 1 条；高频/并发/长跑未测；不能承诺全量评论 |
| **闲鱼** | 交易源（1） | **用户导出** 20+ 条 JSONL/CSV → imported 映射/去重/缺口报告；不自动采集 | 导出脱敏样例；确认可商用/隐私范围 | 导入非实时；无成交/评论；¥1 引流价；`wants` 非订单；平台条款/风控未核 |
| **小红书** | 内容/价格补充（第 3） | 用户导出笔记/商品样例或后续授权浏览器只读；先导入，不自动 | 登录/扫码或导出；确认字段范围 | 风控强、登录/扫码不稳定；价格/评论字段未验证；不能把 README 当实测 |

- **推荐顺序**：B站 1 页评论（已 A 实测）→ 闲鱼导入（本契约）→ 小红书导入（未验证，失败则维持 B站+闲鱼 2 源）。
- **微博**作为备选：A 实测当前访客墙，登录后能力未验证；不作为首批自动源；用户若提供登录态也只能先跑 1 页并立即停。
- 不采用 catbus/MediaCrawler 作为依赖；不自动处理验证码；遇到登录/风控立即停。
- 每源先设预算：1 页/20 条/单次/间隔 ≥3s；记录请求、sha、exit；不无限翻页。

## 6. 导入验收检查

1. 20 条均能解析 native_id；重复 native id = 0。
2. 20 条有 raw_sha256；content_hash 20 个；`origin_kind=imported`。
3. 4 条无 wants 不填 0/不猜测；3 条 reference 单独保留。
4. 标题/正文不写入业务库；`data_origin` 不伪造。
5. 同 native id 重导 → 更新版本，不新增；同 content 重导 → 不新增。
6. 运行后 `instance/app.db`/workbench/CSV 哈希不变（只读）。
