# D1 交付摘要

- 目标：用 **synthetic** 单跑通「选品 → 选源 → 验货 → 写介绍 → 就绪 → 导出 → 记录 → 发布回填 → 复盘」，并做守卫实测、界面核对与回归。
- 结论：**链路可跑通**（9/9 步通过、10/10 守卫符合预期、两视口无横向溢出、两套回归全绿）；同时记录 **8 条不顺手项**（未修，按任务要求只记录）。

## 产物

| 文件 | 内容 |
| --- | --- |
| [FLOW-WALKTHROUGH.md](FLOW-WALKTHROUGH.md) | 逐环节表（入口/操作/期望/实际/证据）+ 守卫 10 条 + 界面核对 + **问题清单 8 条** + 回归 |
| `walkthrough.json` | 9 步与 10 守卫的结构化结果（`all_ok=true`）、库计数、`review.py` 输出 |
| `ui.json` | 三栏标签、继续区块链接、6 组视口的 `innerW/scrollW/scrollH/overflowX`、无/无效 wo 探测 |
| `feedback-log.csv` | 一行 synthetic 反馈（中文表头，与 b25 对齐），供 `review.py` 读取 |
| `logs/` | `walkthrough.log`、`workbench_all.log`、`project_full.log` |
| `walkthrough.py` / `ui_metrics.py` | 可复跑脚本（隔离库、跑完删密钥） |

## 关键数字

- 工作单：`wo:20261024-33da03de`（synthetic，名称 `[SYNTHETIC] D1 学习计划模板`）
- 库计数：`workorder=1 / event=11 / export=1 / candidate=1 / copy_version=1 / publish=1`
- 导出：GET md/json **200/200** 且导出表 **0→0**（零写）；POST 记录 **0→1**，重复 `dedup=true` 不增行
- 发布：合法回填 **200**；非法三例 **400**；越权三例 **403** 且库未变
- 传导：改已选许可 → `sample_status/cost_minor=NULL`，导出转 **409**
- 复盘：`review.py` **rc=0**，四指标 `na`（零成交）→ 建议“样本不足，保留观察期”
- 回归：`workbench_all` **213 OK**、`project_full` **334 OK（49.5s）**

## 边界

未登录平台、未发布真实商品、未采购；未改代码与数据；未写生产库/业务库；守卫四哈希未变。详见 [FLOW-WALKTHROUGH.md](FLOW-WALKTHROUGH.md) 第四节问题清单。
