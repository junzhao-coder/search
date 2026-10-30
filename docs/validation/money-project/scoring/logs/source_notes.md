# 采集来源备注

- **X**：`tools/collect_search.py`（复制自 topic-crawler wrapper，f=top；`x_collect.py` 未改）30 条，exit=0，127.5s。
- **Bilibili**：首次 `curl` 未带 `Accept: application/json` 时返回 HTML 风控页；补上 `Accept` + UA/Referer 后成功，20 条，exit=0，约 1.2s。
- **GitHub**：直连 `api.github.com` 返回 `API rate limit exceeded for 221.2.164.52`（共享 IP 配额耗尽）；改用进程级本地代理 `127.0.0.1:10808` 重试，1 次 search 请求成功，10 仓库，exit=0，约 1.1s；未使用 token，未扩大请求量。
