# S3 真实链路前置设计稿 · 独立评审（非作者评审）

> 评审对象：[docs/design/S3_REAL_LINK_SPEC.md](<../design/S3_REAL_LINK_SPEC.md>)（121 行，sha256 `4052e6ff8ab6933ddcedce9619023a1988a0733822c12db203439733e6573b7c`，15651 bytes）
> 评审者：独立执行者 A（作者为原 B），任务 `task-4f144c3f9bee2a4f11b84ef96e1e491e`。评审时点：2026-10-20 12:47 +08:00。
> 性质：**纯只读评审**。未修改被评审文件与任何源码/测试/台账；**未联网、未启动应用、未运行任何测试**；只读复算了被评审文件与依据文件的 sha256（见 §0.2）。
> 技能：本会话函数清单中**没有 `skill` 工具**（无法调用，如实标注未加载任何技能）；本评审为文档/代码静态核对，未引入依赖与费用。
> 结论：**需修订**（不建议直接进入受控 real 模式实现批）。阻断/需修订项见 §6、最小修订见 §7。

## 0. 方法与输入

### 0.1 评审方法

1. 逐行读被评审稿，按 g1 七项与 g2 拆解其主张；
2. 对每条引用打开原文核对（行号以被评审稿 `L…` 标注，代码以 `文件:行` 标注）；
3. 只读复算哈希，确认被评审稿引用的冻结值与当前 live 一致；
4. 以"现有 fixtures + 既有断言能否执行"检验 §9 的 R-01…R-10；
5. 不把静态阅读写成实测证据；不能核实的引用明确标注"未核实/无法核实"。

### 0.2 只读复算的哈希（live 当前值，评审时点）

| 文件 | sha256 | 被评审稿引用 |
| --- | --- | --- |
| `docs/design/S3_REAL_LINK_SPEC.md`（121 行） | `4052e6ff…73b7c` | 被评审对象 |
| `app/sources/bilibili_view.py`（334 行） | `b0dc0ced1bc3be3eca85116559d5acae52f7753dca1dcbbac259e573cc73f98e` | L5 描述行数；与 OFFLINE 验收所列一致 |
| `app/sources/wiring.py`（166 行） | `bafcf3974cbfb3ed4da99936e5d65d10d6f02c663b6325008255b4eaecc0da05` | L5 冻结值 ✓ 一致 |
| `app/core/importer.py`（991 行） | `a11eaf4d39541ac11459eb1cebb8586f4922838b96714d7f7f3d2e253cff51a1` | L5 冻结值 ✓ 一致 |
| `app/core/identity.py`（84 行） | `358e3c27ec06522679cd7ace61ea29d8182807533a7bd123bfef481c65b67d9b` | 未引用（本评审补充依据） |
| `app/storage/migrations/0001_init.sql` | `9b0493731305c2e3de3c89a1a16dcc8a53ca5882d014f63333b34e7c872e62bb` | 未引用（本评审补充依据） |
| `tests/fixtures/sources/bilibili_view_ok_BV1us8MzPEmn.json` | `d7915ce4…a1f3` | L91 引用 ✓ |
| `tests/fixtures/sources/bilibili_view_failures.json` | `5b666278…2213` | L91 引用 ✓ |
| `docs/design/CONTRACT.md` | `826c24cc…fb4f9` | L5 引用 |
| `DEVELOPMENT_PLAN.md` | `0a50d317…63c6` | L5 引用 |
| `docs/design/S3_WIRING_SPEC.md`（231 行） | `d1e58c32…089a` | L5 引用 ✓ 行数一致 |
| `docs/validation/S3_OFFLINE_WIRING_ACCEPTANCE.md` | `d0b08009…c185` | L5 引用 |
| `docs/validation/S3_PUBLIC_PATH_COMPATIBILITY.md` | `ef6d0d7e…40cc` | L4 引用 |
| `tests/sources/test_wiring_offline.py` | `c66d72ee36f7697c105a87934784a0abb552ae4bdf8c5c60ad7179c4c264da4f` | L5 冻结值 ✓ 一致 |
| `tests/sources/test_bilibili_view.py` | `7b1367e1…15b8` | 未引用（本评审补充依据） |

> 备注：`test_import_api.py` 的 `251fff5f…` 与上述 4 个冻结值在**本会话此前批次**（`run_20261019_224713_compat3/evidence/30_frozen_live.json`，5/5 PASS）已复算一致；本轮未重复计算该文件。

## 1. g1 逐项结论（覆盖 / 缺失 / 歧义）

判据：g1 七项 = 本任务"重点审查"1)–7)。行号均指被评审稿。

| # | g1 项 | 被评审行号 | 结论 | 依据（代码/契约行） | 说明 |
| --- | --- | --- | --- | --- | --- |
| g1-1 | 未授权时拒绝运行 / 绕过口 / URL 走私 | L14–L31（A1–A9）、L30 | **歧义（过程覆盖、强制缺失）** | adapter 无授权校验（`bilibili_view.py:297-322` 只要求注入 transport）；`wiring.py:134-166` 无授权参数；`request_url` 只由 bvid 构造（`:321`）；`resolve_target` 拒绝非信任域/短链/带 userinfo/非默认端口（`:33-63`）；适配器测试 `test_invalid_or_untrusted_targets_never_reach_transport`（`test_bilibili_view.py:356`） | **URL 走私口不存在**（构造与校验两条都硬）。但 A1–A9 是**人工确认清单**，"执行层必须拒绝启动"（L30）没有定义强制产物；绕过口＝直接 `BilibiliViewReader(transport=真实)` 或 `complete_known_object(reader=…)`（两者代码内都无授权校验）。设计把强制留给实现批（L76/L83），但未写"哪些 A 项由代码强制、哪些仅人工确认"，也未列"未授权批次 transport 调用 0 次"的测试要求 |
| g1-2 | 预算/限流/停止 vs 适配器缓存与失败分类；重试矩阵 | L33–L39 | **覆盖设计、含不可执行项与自相矛盾** | 缓存：`bilibili_view.py:307-333`（进程内 dict、24h TTL、只缓存内容、失败不缓存 `:324-329`）；失败分类：`:66-87`；无预算/限流/停止代码（稿 L110 自认未实现） | ① L35 `budget_exhausted` **不是合法状态**：`run_record.status` CHECK 只有 `running/ok/partial/failed/interrupted/skipped_duplicate`（`0001_init.sql:259`），且 §1 声明不新增表/迁移 → 只能写 notes/error_summary 文本，稿未写落点。② L37 `robots_disallowed` **适配器不产出**（只产出 timeout/rate_limited/blocked_login/failed，见 `:66-87`、`:208-268`），且 `search_coverage` 表按迁移注释**根本不建**（`0001_init.sql:2`），适配器注释里的"frozen search_coverage.outcome 枚举"无库内依据。③ L37"退避 2s → 4s"与"最多重试 1 次"不自洽（1 次重试只会用到 2s）。④ L36"同对象最小间隔 ≥5 秒 / 并发度 1"没有任何可执行落点说明（属实现批，可接受，但应标"实现批"） |
| g1-3 | 技术默认 0 与失败审计 vs importer / record_failure 实际语义 | L41–L55 | **大部分覆盖；1 处与代码相反；缺 1 行** | `wiring.py:106-131`（单事务失败 run；省略三计数列；note 技术零文本 `:117-118`）；`0001_init.sql:262-264`（三项 `NOT NULL DEFAULT 0`）；`wiring.py:141-147`（适配器失败→失败 run）、`:160-164`（异常/422→失败 run）；`importer.py:932-944`（ok/partial 与三项计数）、`:967-977`（atomic 失败保留批次与行结果） | ① L54"技术默认 0 ≠ 已观测零需求"**准确**：schema 默认 + note 原文一致。② L53 计数口径**准确**（`items_found=len(parsed_rows)`、`items_new=counts.created`、`items_dup=counts.duplicate_skipped`，`importer.py:944`）。③ **L51 与代码相反**："SQL 异常…异常冒泡，不吞不伪成功"——实际 `complete_known_object` 捕获 `(sqlite3.Error, AppError)` 后**写失败 run 并返回**（`wiring.py:160-161`），只有"失败审计写入本身失败"才冒泡（`:128-131`）。④ 表缺 `WiringReject` 行（标题>300/缺 bvid/哈希不符/记录非 ok → 失败 run，`wiring.py:146-147`），§9 也无对应 case。⑤ transport **抛异常**路径无审计：`reader.complete`（`:140`）与 `self._transport(request_url)`（`bilibili_view.py:327`）均无 try/except，异常会穿透，不写失败 run，与 L49"失败必有审计"冲突（见 F-08） |
| g1-4 | 观察时间保真（回退与 wiring §11.5 引用） | L57–L63 | **机制覆盖、引用错误 + 语义混淆** | 合法校验：`bilibili_view.py:114-123`；`source`/`import_time` 判定与回退戳：`:126-132`；时间来源列：`wiring.py:91-92`；内部注入与落库：`importer.py:763-800`、`:839-840`、`:545-547`；适配器测试 `test_observed_at_defaults_to_import_time_and_is_not_pubdate`（`test_bilibili_view.py:102`） | ① L60"见 S3_WIRING_SPEC §11.5"**引用错误**：观察时间内部注入的设计与断言在 **§4.5**；§11.5 是 stray 告警返工（其 L228 只说明"观察时间/hint 未动"）。② L62"源时间…由适配器换算为 UTC+8 ISO"**混淆字段**：适配器把 `pubdate` 换算成 `published_at`（`:261`、`:108-111`），**不换算 `observed_at`**；`observed_at` 由调用方传入，缺省/非法时用**调用时刻**回退并标 import_time（`:126-132`、`:289-291`）。真实批次的"源时间"规则（由 runner 从 pubdate/ctime 换算后显式传入）设计未写 |
| g1-5 | 强键与 ABA 表述、旧证据边界、是否夸大 | L65–L71 | **覆盖、需限定边界** | `identity.py:34-45`（`_sha16`=前 16 字节/32 hex；`content_hash`）、`:73-77`（`n:<source>:<native>`）；`0001_init.sql:97`（`ux_demand_strong`）、`:122`（`evidence UNIQUE(demand_signal_id)` 部分唯一）；CONTRACT §4.5（`CONTRACT.md:499-529`，含 L527 real/synthetic 两条）；既有实测：本仓 [S3_PUBLIC_PATH_COMPATIBILITY.md](S3_PUBLIC_PATH_COMPATIBILITY.md) §7.7（C6：失效后 step3→4 全部 evidence 行逐值相等、v1 仅 `last_seen_at`、v2 整行不变、`gate_review` 无新增） | 主表述与实测一致，**但**：① L70"旧证据 `invalidated_at`/`invalid_reason` **一律**不动"应限定"**导入路径**"——失效 API 会按其语义修改这两列（非导入行为）。② L70"不追加证据"只对**旧版本重放**成立；`version_added` 会为新 `demand_signal` 行建证据（`evidence UNIQUE(demand_signal_id)`，每行至多 1 条）。③ L68"同 bvid 不同 `data_origin` ⇒ 两条独立记录"契约正确（`CONTRACT.md:527`），但当前 `build_row` 只许 synthetic（`wiring.py:58-59`），**本项无法离线验证**，§9 也没有对应 case |
| g1-6 | 复用边界与 code 一致性；是否错误声称可运行 real | L73–L78 | **覆盖、准确（1 处歧义、1 处通道缺口）** | `wiring.py:29-34`（23 键 ✓ 实际 23）、`:52-103`（`build_row`；标题>300 拒绝 `:73-74`；示例域 URL `:87`）、`:58-59`（synthetic-only）、`:106-131`、`:134-166`；`importer.py:763-800`、`:803-809`、`:939-944` | ① 复用清单与代码逐项成立；synthetic-only 未被本稿修改（L76）✓；request_url 偏差（L77）与 `S3_WIRING_SPEC.md:230` 一致 ✓。② "示例域 URL **两阶段**"（L75）表述歧义：`build_row` 只有一步（`:87` 直接写示例域）；"两阶段"是 adapter canonical URL → wiring 示例域 URL 的整体链路（wiring spec §3），建议注明。③ **通道缺口**：L16/L77/L102（R-08）都要求把 S3AUTH/请求 URL 写进 `run_record.notes/error_summary`，但现状成功路径 notes 固定为 `batch=<id>`（`importer.py:944`）、失败路径 notes 固定文本+bvid（`wiring.py:117-125`）——**没有任何注入口**，与"不新造落库通道"（L78）存在张力 |
| g1-7 | §9 R-01…R-10 可执行性、期望可核验、遗漏 case | L89–L106 | **部分覆盖：8 项现状可验、2 项不可执行、缺 5 类 case** | fixtures：ok `real_excerpt`+`is_complete_raw_response=false`；failures 合成 5+ 例（`rate_limited_412`/`login_redirect_200`/`timeout`/`html_shell`/`missing_62002`，另 `server_error_500`）；既有断言：`test_wiring_offline.py:107-460`（s3w01…s3w21）、`test_bilibili_view.py:70-538` | 逐项见 §4 表。要点：R-01…R-06、R-09、R-10 可映射既有断言/fixture；**R-07（预算/停止）与 R-08（成功路径 URL 审计）依赖尚未实现的 runner 与 notes 通道**（稿 L110 自认未实现），故 L91"验证真实链路会用到的一切机制"属夸大。缺：缓存命中/TTL 过期/失败不缓存（适配器测试已覆盖但稿未引用）、并发度与最小间隔（属实现批）、"重试计入预算"（L35 说含重试却无 case）、`real`/`synthetic` 共存（不可离线验）、`WiringReject` 失败审计 |
| g2 | 设计稿/未接通区分、越界承诺 | L1–L6、L10–L12、L76、L108–L113 | **覆盖良好（1 处内部夸大）** | 真实证据边界声明 L4 与 compat 报告 §4.2/§6.6/§7.6 一致；§10 未实现/未联网/未执行/未覆盖四段完整；§8 前置清单含"实现批已验收" | 未发现"已接通/可运行 real"的错误陈述；未发现新增网络权限/依赖/表/端点/CLI/定时器或修改契约、source 种子的越界承诺（L3、L11、L31 与迁移/种子一致）。**唯一内部矛盾**：§9 标题与 L91 的"一切机制"与 R-07/R-08 的不可执行性冲突（属表述夸大，非越界） |

## 2. 引用逐条核对（真伪与行号）

| # | 被评审稿引用（行） | 核对结果 | 依据 |
| --- | --- | --- | --- |
| 1 | L5 `S3_WIRING_SPEC.md` 231 行、§11.5 返工 | **真** | 文件 231 行；§11.5 见 `S3_WIRING_SPEC.md:225-231` |
| 2 | L5 `wiring.py` 166 行、冻结 `bafcf397…` | **真** | 166 行；sha 一致（§0.2） |
| 3 | L5 `importer.py` 内部参数段、冻结 `a11eaf4d…` | **真** | `importer.py:763-800`（单行/白名单/时间戳/同事务）、`:803-809`（`run_source_id` FK 预校验）；sha 一致 |
| 4 | L5 `bilibili_view.py` 334 行：注入式 transport / 失败分类 / 回退戳 | **真** | `:297-322`/`:66-87`/`:126-132`/`:334` 行数 |
| 5 | L5 CONTRACT §0.5/§0.7/§1.10–§1.12/§2.2/§3.3/§4/§4.5 | **段落均存在**；§0.5/§4/§4.5 已抽查一致，其余未逐字核对 | `CONTRACT.md:53,64,241,248,252,291,340,400,499` |
| 6 | L5 PLAN §7（S3-A1/A2/A3） | **真** | `DEVELOPMENT_PLAN.md` §7 |
| 7 | L4 compat 报告 §4「`tc-*` 是 HTTP 处理栈模拟」 | **真（位置可更精确）** | 实际在 §4.2（`S3_PUBLIC_PATH_COMPATIBILITY.md:59`），§6.6/§7.6 复述 |
| 8 | L67 身份 `n:bilibili:<bvid>`、来源名命名空间 | **真** | `identity.py:73-77`；CONTRACT §4.5 L510（用登记来源名） |
| 9 | L68 强键 `UNIQUE(data_origin, source_id, identity_key, content_hash)`；`content_hash` 前 16 字节 | **真** | `0001_init.sql:97`；`identity.py:34-45`；CONTRACT L505/L514 |
| 10 | L69 旧版本重见只刷新 `last_seen_at`、不改链、不复活旧证据 | **真（对导入路径）** | 本仓 compat §7.7 实测 C6；`CONTRACT.md:520-527` |
| 11 | L70 导入不改 `invalidated_*`、不追加证据、不重建 `gate_review` | **真（限导入路径；`version_added` 例外）** | compat §7.7；`0001_init.sql:122` |
| 12 | L71 `stat` 只进 engagement、不参与指纹/门槛/排序 | **真** | `bilibili_view.py:263`；`identity.py:43-45` |
| 13 | L75 23 键白名单、标题≤300 拒绝、示例域 URL | **真（"两阶段"歧义）** | `wiring.py:29-34,73-74,87` |
| 14 | L76 不改 `build_row` 的 synthetic-only；real 须另批 | **真** | `wiring.py:58-59`；稿 L83/L110 |
| 15 | L77 `request_url` 成功路径不落任何字段（无列） | **真**；但"必须记录"缺通道 | `S3_WIRING_SPEC.md:230`；`importer.py:944`（notes 固定） |
| 16 | L54 技术默认 0（schema 省略取默认）+ note 文案 | **真** | `0001_init.sql:262-264`；`wiring.py:117-118` |
| 17 | L45–L48 `run_record(status='ok')`、计数口径 | **真** | `importer.py:932-944`、`:909` |
| 18 | L49 适配器失败→零业务行+失败 run | **真** | `wiring.py:141-147` |
| 19 | L50 映射/校验 422→批次+行结果+失败 run | **真** | `wiring.py:162-164`；`importer.py:967-977` |
| 20 | L31 四行种子仍 `manual_import`/`yes` | **真** | `0001_init.sql:283-294`（`s_manual`/`s_xianyu`/`s_xhs`/`s_bili`） |
| 21 | L35 达到预算"标 `budget_exhausted`" | **假（作为状态不可执行）** | `0001_init.sql:259` 枚举无此值 |
| 22 | L37 `robots_disallowed` 不重试 | **假（适配器不产出该类）** | `bilibili_view.py:66-87,208-268`；`0001_init.sql:2`（`search_coverage` 未建） |
| 23 | L51 SQL 异常"异常冒泡，不吞不伪成功" | **假（与代码相反）** | `wiring.py:160-161` |
| 24 | L60 观察时间保真"见 S3_WIRING_SPEC §11.5" | **假（章节错）** | 应为 `S3_WIRING_SPEC.md:94-110`（§4.5）；§11.5 是 stray 告警返工 |
| 25 | L62 源时间"由适配器换算为 UTC+8 ISO" | **假（字段混淆）** | `bilibili_view.py:108-111,261`（pubdate→`published_at`）；observed_at 来自调用方 `:126-132,289-291`；测试 `test_bilibili_view.py:102` |
| 26 | L16 确认结果写入"该批次 run_record.notes" | **假（无注入口）** | `importer.py:944` 固定 `batch=<id>`；`wiring.py:117-125` |

## 3. 越界检查（③）

| 检查项 | 结论 | 依据 |
| --- | --- | --- |
| 新增网络权限 / 真实 HTTP | **无**（设计明确注入式 transport；adapter 不导入 HTTP 客户端） | `bilibili_view.py:1-6,297-322`；`test_bilibili_view.py:538`（module has no network client）；稿 L3/L10/L12 |
| 新增依赖 | **无** | 稿 L3；既有代码仅标准库 |
| 新增表 / 迁移 | **无**；且设计使用的审计落点都在既有 `run_record` 文本字段 | 稿 L3/L16/L77；`0001_init.sql:252-267` |
| 新增端点 / CLI / 定时器 | **无** | 稿 L3（范围外）、L10-11 |
| 改 `source` 四行种子 / 契约 | **无**；L31 明确保持现状 | `0001_init.sql:283-294`；稿 L11/L31/L121 |
| 错误声称"可运行 real"/"已接通" | **无**；L1–L4、L12、L76、§10 一致声明未实现/未联网 | 稿 L1-L4/L12/L76/L108-L113 |

> 结论：**不存在越界承诺**；设计把未来实现项（真实 transport、预算/停止、授权清单校验、URL 审计）明确列为未实现（L110）与实现批前置（L83），边界陈述总体可信。

## 4. §8 前置清单与 §9 R-01…R-10 可执行性（④）

### 4.1 §8 前置清单（L80–L87）

- 六项均具体、可勾选；"隔离运行目录/独立 DB/业务库前后哈希"与既有批次做法一致（可执行）。
- 缺口：(a) "网络证据（时间、URL、状态码、原因）可留痕"**未给落点/通道**（与 F-06 同源）；(b) 未列"transport 异常处理"前置；(c) 未列"停止后 `run_record.notes` 的确定文案"（因 `budget_exhausted` 不能作状态，需文案化）；(d) 未列"未授权批次拒绝运行"的验证项。

### 4.2 §9 R 表逐项

| R | 现状可执行？ | 可用 fixture / 既有断言 | 期望值可核验性 | 意见 |
| --- | --- | --- | --- | --- |
| R-01 | **可** | ok fixture + `test_wiring_offline.py:107`（s3w01）+ adapter tests | 可（需规定**每 case 新建 reader**，否则缓存命中使 transport 计数为 0） | 建议补"新实例"前置 |
| R-02 | **可** | s3w02（`:132`） | 可 | 与 compat C5 实测口径一致 |
| R-03 | **可** | s3w03（`:143`） | 部分：应写具体数值——`rows_version_added=1`、`counts.created=0`、`items_new=0`（`importer.py:740-750,909,944`） | 期望值需具体化 |
| R-04 | **可** | s3w17（`:352`）+ compat §7.7 C6 | 可（断言不 500 即 status=201；链/证据/`invalidated_*` 不变） | 建议引用 C6 既有证据 |
| R-05 | **可** | s3w05（`:165`）+ adapter `test_invalid_observed_at_falls_back_and_is_recorded`（`test_bilibili_view.py:122`） | 可（固定 clock 注入 `bilibili_view.py:307`） | — |
| R-06 | **可** | failures fixture 5 例 + s3w06/s3w07/s3w20（`:177,190,428`） | 可；但"不重试"**不可判别**——适配器本身零重试（`bilibili_view.py:298` "No retries"、测试 `:449`），断言应改为"transport 调用次数=1、失败不缓存" | 断言口径需改 |
| R-07 | **不可** | 需 batch runner（未实现，稿 L110）；`budget_exhausted` 非合法 status | 不可（除非改断言为 notes 文本） | 移至实现批后验 |
| R-08 | **不可** | 需 notes/error_summary 注入口（现无，见 F-06）；成功路径 notes 固定 | 不可 | 移至实现批后验，并在设计写清通道 |
| R-09 | **可** | s3w20（`:428`）+ `wiring.py:117-118` | 可（断言 notes 含技术零文案、三计数=0） | — |
| R-10 | **可** | s3w14（`:284`）+ adapter `:538`、`:356`（非法目标 0 次 transport） | 可 | — |

**遗漏的关键 case（建议补入 §9 或明确引用既有覆盖）**：24h 缓存命中（adapter `test_cache_hit_within_24h_then_refresh`，`test_bilibili_view.py:438`；`test_cache_shares_content_but_rebuilds_url_per_input` `:414`）；失败不缓存（`:449`）；TTL 过期（`:438` 内含）；并发度/最小间隔（属实现批）；"重试计入预算"（L35 说含重试，R-07 未覆盖）；`real`/`synthetic` 共存（不可离线，标注实现批后验）；`WiringReject` 失败审计（title>300/哈希不符/记录非 ok → 失败 run，`wiring.py:146-147`；既有 s3w08/s3w21 可参考）。

## 5. 缺项 / 歧义 / 风险清单

| 编号 | 严重度 | 问题 | 位置 | 最小修订方向 |
| --- | --- | --- | --- | --- |
| F-01 | **阻断** | 观察时间保真引用章节错误（§11.5 ≠ 观察时间设计） | L60 | 改引 S3_WIRING_SPEC §4.5（`S3_WIRING_SPEC.md:94-110`），§11.5 仅作"未改观察语义"佐证 |
| F-02 | **阻断** | `pubdate→observed_at` 混淆：适配器只换算 `published_at`，`observed_at` 由调用方传入/回退为调用时刻 | L62 | 明确"真实批由 runner 把 pubdate/ctime 换算后作为 `observed_at` 入参；适配器不自行换算、也不把 pubdate 当 observed_at" |
| F-03 | **阻断** | "SQL 异常…异常冒泡"与代码相反（wiring 捕获并写失败 run；仅审计写入失败冒泡） | L51 | 改写该行；并补 `WiringReject` 失败行 |
| F-04 | **阻断** | `budget_exhausted` 不是合法 `run_record.status`（无迁移授权） | L35 | 明确落点为 `run_record.notes`/`error_summary` 文本；或在实现批定义新状态（需改迁移，超出本设计） |
| F-05 | **阻断** | `robots_disallowed` 无适配器产出；`search_coverage` 表未建 | L37 | 删除该项，或明确映射为 `failed` 并在实现批新增分类与停止判定 |
| F-06 | **阻断** | S3AUTH/请求 URL 无写入通道（notes 现为固定文本） | L16、L77、L102 | 指定最小内部通道（类比 `internal_observation` 的内部参数，或 runner 另写 `run_record(status='running')`），并声明不改公共契约；R-08 移实现批 |
| F-07 | **阻断** | R-07/R-08 被列为"离线最小验收"但依赖未实现功能；L91"一切机制"夸大 | L89–L102 | 拆分"现状可验/实现批后验"两段 |
| F-08 | **风险** | transport 抛异常会绕过失败审计（adapter `:327`、wiring `:140` 均无 try） | L49 vs 代码 | 明确 transport 契约"绝不抛异常、以 error 字段返回"，或要求 runner 捕获并写失败 run；补对应 case |
| F-09 | 需修订 | A1–A9 无代码强制点；绕过口=直调 adapter/`complete_known_object`；未标注"人工/强制" | L14–L31 | 标注各 A 项执行方式；实现批须有 runner 级 gate + "未授权=0 次 transport"断言 |
| F-10 | 需修订 | §4 缺 `WiringReject` 行；§9 无对应 case | L43–L51 | 补行 + 补 case（可参考 s3w08/s3w21） |
| F-11 | 需修订 | "旧证据一律不动/不追加证据"未限定路径与 `version_added` 例外 | L70 | 限定"导入重放路径"；注明 `version_added` 为新 `demand_signal` 行建证据 |
| F-12 | 需修订 | `real`/`synthetic` 共存不可离线验证，§9 无 case | L68 | 标注"实现批后验" |
| F-13 | 需修订 | 缺缓存命中/TTL/失败不缓存/并发/重试计数 case（部分已有测试未引用） | L89–L104 | 引用既有适配器测试或新增 R-11…R-15 |
| F-14 | 需修订 | R-03 期望值欠具体（`created=0`/`items_new=0` 未写） | L97 | 写具体数值口径 |
| F-15 | 需修订 | "示例域 URL 两阶段"歧义 | L75 | 注明两阶段在整体链路而非 `build_row` 内部 |
| F-16 | 需修订 | 退避"2s → 4s"与"最多重试 1 次"不自洽 | L37 | 改为 n=1 时单次 +2s，或明确序列含义 |
| F-17 | 需修订 | R-06"不重试"不可判别（适配器零重试） | L100 | 改断言为 transport 调用计数/失败不缓存 |
| F-18 | 建议 | 引用清单中 §0.7/§1.10–§1.12/§2.2/§3.3 未逐字核对（仅存在性） | L5 | 实现批前由作者/策划确认引用段一致 |
| F-19 | 建议 | L4 引用 compat 报告"§4"可精确到 §4.2 | L4 | 精确化 |

## 6. 结论

**需修订**：本设计稿的边界意识、复用边界、技术零与失败审计口径总体扎实，多数引用经核对为真（§2 表 1–20 行）；但存在 **7 项阻断级问题**（F-01…F-07）与 1 项风险（F-08），集中在：

1. 观察时间一节**两处引用/语义错误**（F-01/F-02）——若按现稿实现，real 批的"源时间"链路会与适配器实际行为不符；
2. 失败审计一节**与代码相反**的表述（F-03）与缺失的 `WiringReject` 行（F-10）；
3. 预算/停止的**不可执行状态值**（F-04）与**不存在的失败类**（F-05）；
4. S3AUTH/URL 审计**无写入通道**（F-06），导致 §2/§7/§8/R-08 不可实施；
5. §9 把**未实现功能**（R-07/R-08）列为离线最小验收并称"一切机制"（F-07）；
6. transport **抛异常**时的审计缺口（F-08）。

在上述最小修订完成前，**不建议进入受控 real 模式实现批**（即便进入，也须把 R-07/R-08 与 notes 通道作为实现批内交付项，不得以本稿 §9 作为已可执行的验收依据）。

## 7. 最小修订项（建议按序并入设计稿新 revision）

| 编号 | 修订项 | 对应发现 |
| --- | --- | --- |
| M-01 | §5 L60 引用改为 `S3_WIRING_SPEC §4.5`，§11.5 仅作"返工未改观察语义"佐证 | F-01 |
| M-02 | §5 L62 明确：适配器只把 `pubdate` 换算成 `published_at`；`observed_at` 必须由 runner 显式传入（可由 pubdate/ctime 换算），缺省时适配器用调用时刻 `import_time`；删除"适配器换算 observed_at"表述 | F-02 |
| M-03 | §4 L51 改为：wiring 捕获 `sqlite3.Error/AppError` → 另写失败 run；仅失败审计自身写入失败会冒泡；补 `WiringReject` 行为行 | F-03/F-10 |
| M-04 | §3 L35 明确 `budget_exhausted` 只写 notes/error_summary 文本，不作 status；L37 删除或改写 `robots_disallowed`，并明确其归属实现批 | F-04/F-05 |
| M-05 | §2 L16 / §7 L77 指定 notes 审计通道（内部参数或 runner 前置 run），声明不改公共契约与表；R-08 改标"实现批后验" | F-06 |
| M-06 | §9 拆为"现状可验（R-01…R-06、R-09、R-10）+ 实现批后验（R-07、R-08、缓存/TTL/失败不缓存/重试计数/并发/real-synthetic 共存）"，删除"一切机制"表述 | F-07/F-12/F-13 |
| M-07 | 明确 transport 契约（不抛异常/以 error 返回）与异常兜底审计；补对应 case（可新增 R-15） | F-08 |
| M-08 | 细化 R-03 期望数值；改写 R-06 重试断言口径；修正退避文案；§5 L60/L62 之外核对 §9 与 §4 的一致性 | F-14/F-16/F-17 |
| M-09 | 标注 A1–A9 每项的"人工确认/代码强制"归属，并写入实现批的授权闸门验收项；§7 L75"两阶段"注明所指链路 | F-09/F-15 |

## 8. 声明与限制

- **未修改**被评审文件（S3_REAL_LINK_SPEC.md 哈希评审前后未变，见 §0.2）与任何源码、测试、迁移、契约、根台账、业务库。
- **未联网、未启动应用、未运行任何测试**（无 `unittest`/`pytest`/Flask/HTTP 调用）；本评审不是实测证据。
- 只读复算了 §0.2 表中的文件哈希（`Get-FileHash`），未做其它写入。
- 被评审稿为 121 行，评审行号即该文件行号；代码行号以当前 live 文件为准（哈希见 §0.2）。若被评审稿或代码发生修订，本评审需按新哈希重核。
- 本会话**无 `skill` 工具**，未加载任何技能；评审结论仅基于只读阅读与哈希复算。
- 未核实的引用已在 §2 标注（如 CONTRACT §0.7/§1.10–§1.12/§2.2/§3.3 仅核验存在性，未逐字比对内容）。
