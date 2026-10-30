# 货源库与机会-货源联动（Notion/数字商品）

> 数据来源：已验收 scoring 的 60 条机会样本 + GitHub 公开仓库许可证核验 + 已采集的闲鱼 20 条真实商品（只读）。**不构成法律意见；不用于下单/互动。**

## 1. 方法与口径

### 许可证
- 优先 GitHub API `license.spdx_id`；若为 `null` 或 `NOASSERTION`，实际读取 `/repos/{owner}/{repo}/license` 并解码 LICENSE 前 40 行，不凭仓库名猜测。
- 三档：**可商用**（MIT/Apache/BSD 等宽松许可）、**需授权（署名/有条件）**（CC BY 需署名；GPL/AGPL/MPL 等带义务）、**禁止或不明**（无 LICENSE、404 或自定义条款）。
- **CC BY 更正**：gh-01 的 API 标记为 NOASSERTION，但 LICENSE 前 40 行为 CC BY 4.0；CC BY 允许商用、仅需署名，因此归 **需授权**，不是“禁止或不明”。上一版分类错误，本版已更正。
- 无 LICENSE/404 的仓库才是“禁止或不明”；不能仅凭 NOASSERTION 字段判定，必须看 LICENSE 文本。MediaCrawler 若 NOASSERTION 且无可识别许可文本，仍按“不明”处理。

### 价格
- `price` 字段的 **¥1 是引流标价**，不是真实客单价；`effective_price` 合并 raw_text 中的小数后缀（如 `¥1 .88` → ¥1.88）。
- `reference_price` 是 raw_text 中更高的划线/参考价（如 `¥699`、`¥9.9`），不是成交价。
- `wants` 是“N人想要”的兴趣代理，不是订单/付款人数。
- 小红书 20 条已读取，但 `price=null`，未纳入价格信号；仅作内容参考。

### 联动
- 机会来自已验收 `scoring/scores.csv` 的 Top10；货源按品类做**最近可复用模板**匹配，不是同款商品；匹配质量在表中标注“近似匹配”。
- 毛利沿用 scoring 的区间估计（无成本输入），并叠加闲鱼价格信号作为市场参考；不把 ¥1 标价当真实售价。

## 2. 货源表（sources.csv，14 行）

| ID | 名称 | 类型 | SPDX | 结论 | 成本 |  effort | 稳定性 | 售后风险 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gh-01 | [enescingoz/awesome-n8n-templates](https://github.com/enescingoz/awesome-n8n-templates) | 提示词/自动化模板 | NOASSERTION | **需授权** | 0（公开仓库） | 低 | 0.95 | 中 |
| gh-02 | [InlitX/Obsidian-Dashboard-Gallery](https://github.com/InlitX/Obsidian-Dashboard-Gallery) | 设计资产/模板 | MIT | **可商用** | 0（公开仓库） | 低 | 0.95 | 低 |
| gh-03 | [vercel-labs/marketing-team-eve-template](https://github.com/vercel-labs/marketing-team-eve-template) | 站点/Notion 模板 | MIT | **可商用** | 0（公开仓库） | 低 | 0.95 | 低 |
| gh-04 | [lakshaybhushan/nextjs-notion-waitlist-template](https://github.com/lakshaybhushan/nextjs-notion-waitlist-template) | 站点/Notion 模板 | NONE | **禁止或不明** | 0（代码公开，许可不明） | 低 | 0.65 | 高 |
| gh-05 | [amjarmed/Awesome-AnyType-Resources](https://github.com/amjarmed/Awesome-AnyType-Resources) | 设计资产/模板 | MIT | **可商用** | 0（公开仓库） | 中 | 0.2 | 低 |
| gh-06 | [wildcatco/notion-blog](https://github.com/wildcatco/notion-blog) | 站点/Notion 模板 | NONE | **禁止或不明** | 0（代码公开，许可不明） | 中 | 0.1 | 高 |
| gh-07 | [makenotion/notion-sdk-typescript-starter](https://github.com/makenotion/notion-sdk-typescript-starter) | Notion 模板/开发资源 | NONE | **禁止或不明** | 0（代码公开，许可不明） | 中 | 0.67 | 高 |
| gh-08 | [timovv/notion-website-template](https://github.com/timovv/notion-website-template) | 站点/Notion 模板 | NONE | **禁止或不明** | 0（代码公开，许可不明） | 低 | 0.1 | 高 |
| gh-09 | [2skydev/Notion-Next.js-blog-starter-kit](https://github.com/2skydev/Notion-Next.js-blog-starter-kit) | 站点/Notion 模板 | NONE | **禁止或不明** | 0（代码公开，许可不明） | 中 | 0.1 | 高 |
| gh-10 | [heyman333/agent-notion-template-docs](https://github.com/heyman333/agent-notion-template-docs) | Notion 模板/开发资源 | MIT | **可商用** | 0（公开仓库） | 低 | 0.95 | 低 |
| gh-11 | [billryan/resume](https://github.com/billryan/resume) | 简历模板 | MIT | **可商用** | 0（公开仓库） | 中 | 0.1 | 低 |
| gh-12 | [cobiwave/simplefolio](https://github.com/cobiwave/simplefolio) | 作品集/站点模板 | MIT | **可商用** | 0（公开仓库） | 中 | 0.63 | 低 |
| gh-13 | [rockbenben/ChatGPT-Shortcut](https://github.com/rockbenben/ChatGPT-Shortcut) | 提示词/自动化模板 | MIT | **可商用** | 0（公开仓库） | 中 | 0.95 | 低 |
| gh-14 | [academicpages/academicpages.github.io](https://github.com/academicpages/academicpages.github.io) | 作品集/站点模板 | MIT | **可商用** | 0（公开仓库） | 中 | 0.95 | 低 |

三档分布：**可商用 8 / 需授权 1 / 禁止或不明 5**（详见 `sources.csv`；`raw/license_checks.json` 与 `raw/licenses/*.json` 保留逐仓库核验证据）。8 个可商用均为 MIT；1 个需授权为 CC BY 4.0（gh-01，需署名）；5 个无 LICENSE/404 为不明。

### CC BY 更正记录

- **gh-01 `enescingoz/awesome-n8n-templates`**：API `license.spdx_id=NOASSERTION`，但实际 LICENSE 前 40 行为 **Creative Commons Attribution 4.0 International**；CC BY 允许商业使用、要求署名，故修正为 **需授权**（非“禁止或不明”）。证据：`raw/licenses/enescingoz__awesome-n8n-templates.json`、`raw/license_checks.json`。
- 其余 5 个无 LICENSE/404 的仓库保持“禁止或不明”：gh-04/06/07/08/09。

## 3. 闲鱼价格信号（price_signals.csv，20 行）

- 标价均为 ¥1；合并小数后缀后的有效价：**¥1.00–¥1.88**（唯一值 ¥1.00, ¥1.09, ¥1.10, ¥1.88）。
- 划线/参考价仅 **3/20** 条：¥9.89, ¥9.90, ¥699.00；其余无参考价，不能据此推客单价。
- 想要人数：**17/20** 条有值，范围 3–2514，合计 9370；是兴趣代理，不是订单。
- 解析状态：`{"fraction_merged": 5, "reference_found": 3, "reference_missing": 17, "wants_missing": 3, "list_price_only": 15}`。

**价格解析失败/部分样例**（完整列表见 `logs/price_parse_summary.json`）：

- item `1052243348747`：`reference_missing|list_price_only`；尾部 `案、做内容、查资料、图片生成、视频生成、运镜分镜、平面设计、绘画都能用，手机电脑都能操作，目录... ¥ 1 2514人想要 江苏 发货极快`
- item `934041348964`：`reference_missing|list_price_only`；尾部 `，非实物，不用快递。秒发货，网盘链结，链结永久有效！ ♦下单请看好，产品自动秒发货，因产品具有... ¥ 1 2335人想要 广东 发货极快`
- item `1065944971904`：`reference_missing|list_price_only`；尾部 `官、脸型、发型、气质高度统一，反复生成同一位人物。 纯电子资料，拍下自助领取。 电子资料可复制保... ¥ 1 436人想要 山东 发货极快`
- item `1083364048246`：`reference_missing|list_price_only`；尾部 `星][五角星][五角星][五角星][五角星][五角星][五角星][五角星][五角星][五角星][五... ¥ 1 22人想要 江苏 发货极快`
- item `1039901404381`：`reference_missing|list_price_only`；尾部 `-- ✔数量:包含541款 大小:35GB ✔格式:157款PSD+16款A1+376款PPT+... ¥ 1 948人想要 上海 发货极快`

> 结论：不能用 ¥1 做毛利分母；有效价仍多为 ¥1.00–¥1.88，划线价只有 3 条（最高 ¥699），因此毛利只能给区间/情景，不给点估计。

join 使用 **5 个不同源码**：`gh-03`、`gh-10`、`gh-11`、`gh-12`、`gh-13`。

## 4. 机会-货源联动 Top10

| # | 机会 | 分数 | 候选货源 | 许可结论 | 闲鱼价格信号 | 毛利区间 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | [•ଓ.° template notion •ଓ.° — a thread by me *̥₊˚‧](https://x.com/booorenjiiy/status/1467843989533442054) | 0.8 | gh-10 heyman333/agent-notion-template-docs | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0） *全量20条代理*；9370 想要 | 0.7–0.95 |
| 2 | [work! adaaa yang butuh template notion buat nged](https://x.com/worksfess/status/1747215882965979516) | 0.77931 | gh-11 billryan/resume | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0）；8231 想要 | 0.7–0.95 |
| 3 | [I just created a Professional Resume Template fo](https://x.com/saviomartin/status/1482243991244615682) | 0.768966 | gh-11 billryan/resume | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0）；8231 想要 | 0.7–0.95 |
| 4 | [Notion模板怎么导入？简单！](https://www.bilibili.com/video/BV19A411f7cH) | 0.76 | gh-03 vercel-labs/marketing-team-eve-template | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0） *全量20条代理*；9370 想要 | 0.45–0.8 |
| 5 | [Stop scrolling if you are a student. I’m giving ](https://x.com/heyeaslo/status/1580068264650022912) | 0.759655 | gh-10 heyman333/agent-notion-template-docs | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0） *全量20条代理*；9370 想要 | 0.7–0.95 |
| 6 | [notion template <3 some of you asked for a notio](https://x.com/opteemisty/status/1674994814016954371) | 0.758621 | gh-10 heyman333/agent-notion-template-docs | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0） *全量20条代理*；9370 想要 | 0.7–0.95 |
| 7 | [˗ˋˏ°• notion template for your class! •°ˎˊ˗ here](https://x.com/aeshoui/status/1824402140070285653) | 0.748276 | gh-10 heyman333/agent-notion-template-docs | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0） *全量20条代理*；9370 想要 | 0.7–0.95 |
| 8 | [【Notion教程】小白友好：如何拷贝模板？如何设置中文版？](https://www.bilibili.com/video/BV1vr421K7EJ) | 0.74421 | gh-12 cobiwave/simplefolio | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0） *全量20条代理*；9370 想要 | 0.45–0.8 |
| 9 | [I created a Search Planner for ChatGPT. This Not](https://x.com/IAmPascio/status/1641088397874802688) | 0.737931 | gh-13 rockbenben/ChatGPT-Shortcut | **可商用** (MIT) | ¥1.0–1.0；1139 想要 | 0.7–0.95 |
| 10 | [177 Notion 教程 No.46 template-1：学习笔记模板（Template S](https://www.bilibili.com/video/BV11i4y147FS) | 0.728421 | gh-10 heyman333/agent-notion-template-docs | **可商用** (MIT) | ¥1.0–1.88（参考 ¥699.0） *全量20条代理*；9370 想要 | 0.45–0.8 |

### Top10 明细（来源/链接/假设）

**1. •ଓ.° template notion •ଓ.° — a thread by me *̥₊˚‧☆ﾐ**
- 机会证据：[https://x.com/booorenjiiy/status/1467843989533442054](https://x.com/booorenjiiy/status/1467843989533442054)；平台 x；分数 0.8。
- 候选货源：`gh-10` [heyman333/agent-notion-template-docs](https://github.com/heyman333/agent-notion-template-docs)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/heyman333/agent-notion-template-docs/blob/HEAD/LICENSE)。
- 匹配质量：同品类：Notion 模板/站点源；匹配理由：**同品类**；替代货源：gh-03:vercel-labs/marketing-team-eve-template(可商用) | gh-02:InlitX/Obsidian-Dashboard-Gallery(可商用)。
- 价格信号：notion / all_20_fallback / 20 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 9370（兴趣代理）。
- 毛利区间：**0.7–0.95**（mid 0.825）；假设：No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated).

**2. work! adaaa yang butuh template notion buat ngedata lamaran kerja yang kita appl**
- 机会证据：[https://x.com/worksfess/status/1747215882965979516](https://x.com/worksfess/status/1747215882965979516)；平台 x；分数 0.77931。
- 候选货源：`gh-11` [billryan/resume](https://github.com/billryan/resume)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/billryan/resume/blob/HEAD/LICENSE)。
- 匹配质量：同品类：简历/求职模板源；匹配理由：**同品类**；替代货源：gh-12:cobiwave/simplefolio(可商用) | gh-14:academicpages/academicpages.github.io(可商用)。
- 价格信号：design / category_filtered / 16 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 8231（兴趣代理）。
- 毛利区间：**0.7–0.95**（mid 0.825）；假设：Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated).

**3. I just created a Professional Resume Template for Notion. Reply with a and I'll **
- 机会证据：[https://x.com/saviomartin/status/1482243991244615682](https://x.com/saviomartin/status/1482243991244615682)；平台 x；分数 0.768966。
- 候选货源：`gh-11` [billryan/resume](https://github.com/billryan/resume)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/billryan/resume/blob/HEAD/LICENSE)。
- 匹配质量：同品类：简历/求职模板源；匹配理由：**同品类**；替代货源：gh-12:cobiwave/simplefolio(可商用) | gh-14:academicpages/academicpages.github.io(可商用)。
- 价格信号：design / category_filtered / 16 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 8231（兴趣代理）。
- 毛利区间：**0.7–0.95**（mid 0.825）；假设：Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated).

**4. Notion模板怎么导入？简单！**
- 机会证据：[https://www.bilibili.com/video/BV19A411f7cH](https://www.bilibili.com/video/BV19A411f7cH)；平台 bilibili；分数 0.76。
- 候选货源：`gh-03` [vercel-labs/marketing-team-eve-template](https://github.com/vercel-labs/marketing-team-eve-template)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/vercel-labs/marketing-team-eve-template/blob/HEAD/LICENSE)。
- 匹配质量：近似匹配：站点/Notion 模板源（内容教程非直接商品）；匹配理由：**近似**；替代货源：gh-10:heyman333/agent-notion-template-docs(可商用) | gh-02:InlitX/Obsidian-Dashboard-Gallery(可商用)。
- 价格信号：notion / all_20_fallback / 20 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 9370（兴趣代理）。
- 毛利区间：**0.45–0.8**（mid 0.625）；假设：No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: template/course upsell: ¥15-99 price, ¥5-30 production/support cost (estimated).

**5. Stop scrolling if you are a student. I’m giving away this FREE Notion template f**
- 机会证据：[https://x.com/heyeaslo/status/1580068264650022912](https://x.com/heyeaslo/status/1580068264650022912)；平台 x；分数 0.759655。
- 候选货源：`gh-10` [heyman333/agent-notion-template-docs](https://github.com/heyman333/agent-notion-template-docs)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/heyman333/agent-notion-template-docs/blob/HEAD/LICENSE)。
- 匹配质量：同品类：Notion 模板/站点源；匹配理由：**同品类**；替代货源：gh-03:vercel-labs/marketing-team-eve-template(可商用) | gh-02:InlitX/Obsidian-Dashboard-Gallery(可商用)。
- 价格信号：notion / all_20_fallback / 20 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 9370（兴趣代理）。
- 毛利区间：**0.7–0.95**（mid 0.825）；假设：No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated).

**6. notion template <3 some of you asked for a notion reveal, so I created this simp**
- 机会证据：[https://x.com/opteemisty/status/1674994814016954371](https://x.com/opteemisty/status/1674994814016954371)；平台 x；分数 0.758621。
- 候选货源：`gh-10` [heyman333/agent-notion-template-docs](https://github.com/heyman333/agent-notion-template-docs)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/heyman333/agent-notion-template-docs/blob/HEAD/LICENSE)。
- 匹配质量：同品类：Notion 模板/站点源；匹配理由：**同品类**；替代货源：gh-03:vercel-labs/marketing-team-eve-template(可商用) | gh-02:InlitX/Obsidian-Dashboard-Gallery(可商用)。
- 价格信号：notion / all_20_fallback / 20 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 9370（兴趣代理）。
- 毛利区间：**0.7–0.95**（mid 0.825）；假设：No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated).

**7. ˗ˋˏ°• notion template for your class! •°ˎˊ˗ here's the notion template as reques**
- 机会证据：[https://x.com/aeshoui/status/1824402140070285653](https://x.com/aeshoui/status/1824402140070285653)；平台 x；分数 0.748276。
- 候选货源：`gh-10` [heyman333/agent-notion-template-docs](https://github.com/heyman333/agent-notion-template-docs)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/heyman333/agent-notion-template-docs/blob/HEAD/LICENSE)。
- 匹配质量：同品类：Notion 模板/站点源；匹配理由：**同品类**；替代货源：gh-03:vercel-labs/marketing-team-eve-template(可商用) | gh-02:InlitX/Obsidian-Dashboard-Gallery(可商用)。
- 价格信号：notion / all_20_fallback / 20 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 9370（兴趣代理）。
- 毛利区间：**0.7–0.95**（mid 0.825）；假设：No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated).

**8. 【Notion教程】小白友好：如何拷贝模板？如何设置中文版？**
- 机会证据：[https://www.bilibili.com/video/BV1vr421K7EJ](https://www.bilibili.com/video/BV1vr421K7EJ)；平台 bilibili；分数 0.74421。
- 候选货源：`gh-12` [cobiwave/simplefolio](https://github.com/cobiwave/simplefolio)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/cobiwave/simplefolio/blob/HEAD/LICENSE)。
- 匹配质量：替代匹配：作品集/站点模板源（教程机会无同款商品）；匹配理由：**替代**；替代货源：gh-14:academicpages/academicpages.github.io(可商用) | gh-03:vercel-labs/marketing-team-eve-template(可商用)。
- 价格信号：notion / all_20_fallback / 20 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 9370（兴趣代理）。
- 毛利区间：**0.45–0.8**（mid 0.625）；假设：No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: template/course upsell: ¥15-99 price, ¥5-30 production/support cost (estimated).

**9. I created a Search Planner for ChatGPT. This Notion template will help you organ**
- 机会证据：[https://x.com/IAmPascio/status/1641088397874802688](https://x.com/IAmPascio/status/1641088397874802688)；平台 x；分数 0.737931。
- 候选货源：`gh-13` [rockbenben/ChatGPT-Shortcut](https://github.com/rockbenben/ChatGPT-Shortcut)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/rockbenben/ChatGPT-Shortcut/blob/HEAD/LICENSE)。
- 匹配质量：同品类：提示词库源；匹配理由：**同品类**；替代货源：gh-10:heyman333/agent-notion-template-docs(可商用) | gh-03:vercel-labs/marketing-team-eve-template(可商用)。
- 价格信号：prompt / category_filtered / 4 条；有效价 ¥1.0–1.0，参考价 无，想要合计 1139（兴趣代理）。
- 毛利区间：**0.7–0.95**（mid 0.825）；假设：Xianyu listed ¥1 is bait; effective range ¥1.00-1.00; no struck reference found; wants is interest proxy. Gross margin from scoring model assumption: digital Notion template: $9-49 price, $0.5-3 payment/hosting cost (estimated).

**10. 177 Notion 教程 No.46 template-1：学习笔记模板（Template Study-Notes）**
- 机会证据：[https://www.bilibili.com/video/BV11i4y147FS](https://www.bilibili.com/video/BV11i4y147FS)；平台 bilibili；分数 0.728421。
- 候选货源：`gh-10` [heyman333/agent-notion-template-docs](https://github.com/heyman333/agent-notion-template-docs)；许可证 **可商用**（MIT）；核验证据 [license](https://github.com/heyman333/agent-notion-template-docs/blob/HEAD/LICENSE)。
- 匹配质量：同品类：Notion 模板/站点源；匹配理由：**同品类**；替代货源：gh-03:vercel-labs/marketing-team-eve-template(可商用) | gh-02:InlitX/Obsidian-Dashboard-Gallery(可商用)。
- 价格信号：notion / all_20_fallback / 20 条；有效价 ¥1.0–1.88，参考价 ¥699.0，想要合计 9370（兴趣代理）。
- 毛利区间：**0.45–0.8**（mid 0.625）；假设：No exact Xianyu Notion category; all 20 digital-goods signals used as basket proxy. Xianyu listed ¥1 is bait; effective range ¥1.00-1.88; struck reference max ¥699.00; wants is interest proxy, not paid orders. Gross margin from scoring model assumption: template/course upsell: ¥15-99 price, ¥5-30 production/support cost (estimated).

## 5. 风险与不可商用清单

- 可商用 **8** 条：`gh-02`、`gh-03`、`gh-05`、`gh-10`、`gh-11`、`gh-12`、`gh-13`、`gh-14`（仍需保留版权声明与第三方素材复核）。
- 需授权（署名/有条件）**1** 条：
  - `gh-01` **enescingoz/awesome-n8n-templates**：CC BY: commercial use allowed only with attribution (署名)；[证据](https://github.com/enescingoz/awesome-n8n-templates/blob/main/LICENSE)。

以下货源**不能仅凭公开仓库直接商用**（无 LICENSE、404 或自定义条款）：

- `gh-04` **lakshaybhushan/nextjs-notion-waitlist-template**：禁止或不明；SPDX=NONE；原因：no LICENSE file / no license text；[证据](https://api.github.com/repos/lakshaybhushan/nextjs-notion-waitlist-template/license)。
- `gh-06` **wildcatco/notion-blog**：禁止或不明；SPDX=NONE；原因：no LICENSE file / no license text；[证据](https://api.github.com/repos/wildcatco/notion-blog/license)。
- `gh-07` **makenotion/notion-sdk-typescript-starter**：禁止或不明；SPDX=NONE；原因：no LICENSE file / no license text；[证据](https://api.github.com/repos/makenotion/notion-sdk-typescript-starter/license)。
- `gh-08` **timovv/notion-website-template**：禁止或不明；SPDX=NONE；原因：no LICENSE file / no license text；[证据](https://api.github.com/repos/timovv/notion-website-template/license)。
- `gh-09` **2skydev/Notion-Next.js-blog-starter-kit**：禁止或不明；SPDX=NONE；原因：no LICENSE file / no license text；[证据](https://api.github.com/repos/2skydev/Notion-Next.js-blog-starter-kit/license)。

其他风险：
- 货源匹配是“最近可复用模板”，不是同款/授权内容；不能把 GitHub 模板等同于闲鱼商品的权利。
- 闲鱼 ¥1 为引流价；有效价与划线价都不是成交价；想要人数不是订单；无法据此算真实转化/利润。
- 8 个 MIT 源可复用代码/模板，但仍需保留版权声明、检查第三方字体/图片/商标与 Notion 模板内容权利。
- 样本没有“囤货/重售后”品类；本库只覆盖数字商品/模板/工具，实体货源覆盖不足。
- GitHub API 曾遇共享 IP rate limit，本次仅读取公开 API/LICENSE；未使用 token，未扩大请求。

## 6. 假设与限制

- **价格**：有效价来自 raw_text 小数后缀合并；17/20 无参考价，3/20 有参考价；不把 ¥1 当 ASP。
- **毛利**：沿用 scoring 的无成本区间估计（如数字模板 0.70–0.95），叠加闲鱼价格信号；不是实际利润，不含退款/支付/客服/流量成本。
- **许可证**：无 LICENSE/404 或无法识别条款按“禁止或不明”；CC BY 等有条件许可归“需授权（署名/有条件）”；本报告不是法律意见。
- **来源匹配**：Top10 里 8 条 Notion 类机会因闲鱼无同品类价格，回退使用全量 20 条数字商品价格带（表中标 `all_20_fallback`），不能视为 Notion 专属价格。
- **样本**：闲鱼 20、GitHub 14（原 10 + 补充 resume/portfolio/prompt 4）；非概率抽样，不能代表全市场；未下单/互动。

