# 商品分类法（载体 × 用途）+ 内容型分离（rev8）

- 执行者：C；范围：`tools/workbench/`、`docs/validation/money-project/product-taxonomy/`
- 实测地址：**http://127.0.0.1:5015/opportunities**（PID 101752）
- 本轮：新增 3 个**内容型（非商品）**类目并与可售商品分开；内容型五段分析换口径；`Notion模板怎么导入？` 已移出待人工。
- **验收线 `Notion 其它 ≤ 18`：未达成，实际 20（差 2 条）**；已按你的要求给出 **20 条逐条缺词说明**（`categories.json.other_missing`）。**没有为凑数扩词或编造。**

## 1. 三类内容型（非商品）

| 内容型类目 | 关键词 | 条数 |
| --- | --- | --- |
| **Notion 资源推荐清单** | rekomendasi / cara mencari / best / list / 合集 / 推荐 / 盘点 | **8** |
| **Notion 使用教程/导入设置** | import / setup / how to / copy / 导入 / 拷贝 / 设置 / 模板怎么用 / 怎么导入 / 如何导入 | **5** |
| **Notion 教学变现** | create a template / sell it for / monetize / turn into product / 教人做模板 / 变现 | **1** |

合计 **内容型 14 条**，在页面上用「类型」列标记为 `内容·非商品`，且**不计入可售商品计数**。

## 2. 商品型 46 条（守恒 `46 + 14 = 60`）

| 商品类型 | 条数 |
| --- | --- |
| Notion 学习笔记模板 | 14 |
| **Notion 其它（待人工）** | **20** |
| Notion 内容创作选题库 | 5 |
| Notion 赠送引流模板 | 2 |
| Notion 生活计划（预算/健身/旅行） | 2 |
| Notion 求职投递追踪表 | 1 |
| 未归类（待人工） | 2 |

> **副作用需说明**：上一版「Notion 设计作品集模板 3」为本轮 0 —— 这几条标题/简介含 `best`/`list`，被**优先命中「资源推荐清单」**（内容型优先于商品型）。这是规则优先级导致的重分配，不是丢数据（总数守恒）。

## 3. 达标评估

| 目标 | 结果 | 判定 |
| --- | --- | --- |
| `Notion 其它 ≤ 18` | **20** | **未达成（差 2）** |
| ≥4 个 Notion 子类各 ≥2 条 | **6 个**（学习 14 / 内容 5 / 赠送 2 / 生活 2 / 推荐 8 / 教程 5） | 已达成 |
| 商品/内容分离且内容不计入可售 | `product=46, content=14`，`checked=true` | 已达成 |
| 其它条目**每条**都有缺词说明 | `other_missing` 20 条 = 其它 20 条 | 已达成 |

### 剩余 20 条的逐条缺词说明（前 5 条示例，完整 20 条见 `categories.json.other_missing`）

| 平台 | 标题片段 | 缺什么 |
| --- | --- | --- |
| x | `•ଓ.° template notion •ଓ.° — a thread by me` | 缺用途词与内容型词（纯展示贴） |
| x | `notion template <3 some of you asked…` | 缺用途词（只有 `template`，无求职/学习/内容/生活/设计/赠送） |
| github | `InlitX/Obsidian-Dashboard-Gallery` | 描述里只有 dashboard/gallery，无用途词与内容型词 |
| x | `this is my AI psychosis (ft @bot …)` | 与 Notion 商品无关的闲聊贴 |
| … | … | 每条均写明“缺用途词且未命中内容型词（import/setup/推荐/rekomendasi/变现 等）” |

**要补上这 2 条，只有三条路（任选，需你授权）**：① 再扩词表（如 `shop/store/my template/sell my` 等，会影响分类语义）；② 补抓推文详情页/外链落地页正文、GitHub README（现有 `raw_summary` 只到搜索接口层）；③ 人工标注这 20 条。

## 4. 内容型五段分析（口径已换）

是什么 / 谁看 / 需求证据 / 竞争与分发 / **流量价值 · 引流去向 · 相邻可带货商品**：

> 「内容型（非商品），不估算毛利；流量价值：组内 N 条、需求合计 X、最高分位 Y%；引流去向：站内主页 / 合集 / 私信关键词；可带货的相邻商品：同主题 Notion 模板、PPT 模板或资料包（需人工挑选，数据中未标注）」

页面内容组的「可售性均值」「毛利区间」显示 `—（内容型不适用）`，表头计数为 **可售商品 46 条 · 内容型 14 条（不计入可售）**。

## 5. 测试与产物

| 项 | 结果 |
| --- | --- |
| 工作台单测 | **`Ran 42 tests — OK`，exit=0**（新增：三类内容型各命中、内容型不计入可售、`other_missing` 条数=其它条数且每条非空、守恒 `product+content=60`） |
| 原完整套件 | **`Ran 334 tests — OK`，exit=0**，51.4s |
| `categories.json` | 含 `kind`、`conservation{product,content}`、`other_missing[20]`、`coverage`、`targets`、`hit_words.text_source` |
| 聚合页截图 | 1440×900 / 141,757 B / `e0490061c799f726…` |
| 展开五段态 | 1440×900 / 158,315 B / `15f32a23bb7b2ef0…` |
| 手机 | 390×844 / 55,782 B / `546b51bfce655e0c…` |

manifest 自校验 **checked=9 / mismatches=0 / ok=true**，副本与清单逐字节一致；无横向溢出。守卫：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…` 未变。

## 6. 限制（如实）

1. **其它 20 > 18**：差 2 条；20 条逐条缺词已列出，未扩词凑数。
2. **设计作品集类被内容型吸收**（设计 3 → 0）：`best/list` 触发「资源推荐清单」优先，属规则副作用，需你确认是否调整优先级。
3. 内容型判定**仅对 Notion 载体**生效（避免把 PPT 教程等误并）；其它载体暂不区分内容/商品。
4. 内容型的“流量价值”只有需求分位与条数，**没有真实播放/点击/转化数据**；引流去向为规则文案，非实测。
5. 词表仍为启发式，中英印尼混合标题可能误判；五段分析为组级。

---

# rev11 优先级修复（强用途词 > 泛词）

只改判定优先级一处，其余保留。**未改阈值、未编造用途。**

## 1. 新判定顺序

```
载体（标题优先） → 强用途词（portfolio/design/ui kit/moodboard/作品集/设计 → 设计作品集模板，商品型）
                → 内容型（教程 / 泛推荐 / 变现教学）
                → 商品用途（求职/学习/内容/生活/设计/赠送）
```

- **强用途词优先**：命中 `portfolio/design/ui kit/moodboard/作品集/设计` 即判 **Notion 设计作品集模板**，即使同时含 `best/list/合集/推荐/盘点/rekomendasi/cara mencari`。
- **泛词只在无强用途词时生效**（`best/list/合集/推荐/盘点/rekomendasi/cara mencari` → 资源推荐清单）。
- **`secondary_tags`**：设计条目若同时命中推荐/教程/变现词，记为次要标签；写入 `hit_words[item_id].secondary_tags` 与组级 `secondary_top`，页面组行显示「兼：Notion 资源推荐清单」，成员行「用途判定依据」也带 `｜ 兼：…`。

## 2. 回归结果（真实）

| 指标 | rev8 | rev11 |
| --- | --- | --- |
| Notion 设计作品集模板 | 0 | **2** ✅（≥2 达成） |
| Notion 资源推荐清单 | 8 | **7** ✅（>0，未被吞掉） |
| Notion 学习笔记模板 | 14 | 14 |
| Notion 内容创作选题库 | 5 | 4 |
| Notion 赠送引流模板 | 2 | 2 |
| Notion 生活计划 | 2 | 2 |
| Notion 求职投递追踪表 | 1 | 1 |
| **Notion 其它（待人工）** | 20 | **20**（不追求 ≤18） |
| 未归类（待人工） | 2 | 2 |
| **商品 / 内容** | 46 / 14 | **47 / 13**（合计 60 ✅） |
| `notion29` 守恒 | ✅ | **✅（15+6+2+1+1+4 = 29，checked=true）** |

页面头部按你的要求显示：**「剩余 20 条需补采集/人工判断」**（由 `other_missing` 动态渲染），逐条缺词仍保留在 `categories.json.other_missing`（20 条）。

## 3. 测试（真实 exit）

| 套件 | 结果 |
| --- | --- |
| 工作台 | **`Ran 45 tests — OK`，exit=0**（新增：含 `best` 的 portfolio 仍判设计且 `secondary_tags` 含推荐清单；纯 `list` 判推荐；`secondary_tags`/`secondary_top` 记录正确） |
| 原完整套件 | **`Ran 334 tests — OK`，exit=0**，49.5s |

> 过程中我自己引入过一个语法错误（`app.py` 拼接字符串时用 `+ (...)` 后又接 f-string），已修复；两次失败日志保留在提交历史中。

## 4. 截图与清单

| 文件 | 尺寸 | bytes | sha256 前 16 |
| --- | --- | --- | --- |
| `desktop_opportunities.jpg` | 1440×900 | 147,207 | `dead2261382ef1a4…` |
| `desktop_opportunities_expanded.jpg` | 1440×900 | 162,602 | `4fc958aaea6c8019…` |
| `mobile_opportunities.jpg` | 390×844 | 58,080 | `86d3de93b0df7454…` |

manifest 自校验 **checked=9 / mismatches=0 / ok=true**，副本与清单逐字节一致；页面含「兼：」与「需补采集/人工判断」标记（HTTP 实测 `SECONDARY=True NOTE=True`）。守卫：`instance/app.db e073f828…`、`CONTRACT.md 826c24cc…`、`scores.csv ab0c3546…` 未变。