"""历史导入 + 批次授权（**已备好，本轮不执行**）。

⚠ 重要：这一步**不是**"续期已过期的窗口"，也**不是**已获批准的动作。
`authorize_batch` 只是按当前时间新开一个 batch 记录（`started_at=now`）；
它**不计费**（只有 `charge()` 计费），但它把"同一批已同意的 1 次搜索"落在一个**新的
batch_id** 上。窗口过期后能否这样重新签发，属计划 P5 尚未裁定的约束，必须由策划者/用户
明确，不能由本脚本默认执行。

这一步会**写平台账本** `tools/selection/access/runtime/platform_weibo.sqlite3`：
1. `import_snapshot(HISTORY_SOURCES)` —— 把 9 个历史源（3 次探路预扣、2 次未计费登录导航、
   4 个离线自检）作为审计快照导入；导入是幂等的（payload 指纹相同 → unchanged）。
2. `authorize_batch("weibo-live-1", authorized_calls=3, window_seconds=300, seed_from=两登录导航)`
   —— 用户已同意的「新批次 3 次」；其中 2 次被两次登录导航占用（seed_used=2），**剩 1 次**。

为什么 authorized_calls 必须写 3 而不是 1：
- `authorize_batch` 要求 `0 <= seed_used < authorized_calls`，而生产批次**必须**绑定
  `HISTORY_SOURCES` 里两条 `uncharged_navigation`（`_audited_uncharged_keys`），
  否则抛 `seed_association_incomplete`；
- `charge()` 的已用量 = 窗口内事件数 + `seed_used`，所以 3 − 2 = **1 次可用**。

执行前必须确认：平台账本不存在（或该批次尚未授权）；执行后必须在 **300s 窗口内**跑那 1 次搜索，
窗口一关就 `batch_window_closed`（不重开，需新 batch_id + 新授权）。

用法（**需策划者先裁定"窗口过期后重新签发"是否算原授权**；本任务不执行）：
    python -X utf8 docs/validation/v10/weibo-live-prep/authorize_batch.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(r"D:\桌面\two")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.selection.access import platform_budget as pb  # noqa: E402

OUT = ROOT / "docs" / "validation" / "v10" / "weibo-live-prep"
BATCH = "weibo-live-1"
SEED_FROM = ("login-window-1", "login-window-2")   # 两次已发生但未计费的登录导航
AUTHORIZED_CALLS = 3                                # 用户同意的新批次 3 次
WINDOW_SECONDS = pb.MAX_SECONDS                     # 300s，授权后必须立刻跑
RECORDS_CAP = pb.MAX_RECORDS                        # 5


def main() -> int:
    ledger = pb.open_default()          # 固定路径：tools/selection/access/runtime/platform_weibo.sqlite3
    try:
        imported = ledger.import_snapshot(
            pb.HISTORY_SOURCES,
            note="weibo-live-prep: 9 个历史源（3 预扣 + 2 未计费登录导航 + 4 离线自检）")
        print(json.dumps({"import": imported,
                          "history": ledger.history_summary()},
                         ensure_ascii=False, indent=1)[:2000])
        batch = ledger.authorize_batch(
            BATCH,
            authorized_calls=AUTHORIZED_CALLS,
            window_seconds=WINDOW_SECONDS,
            source="user:consent:new-batch-3+login+1-search",
            note=("3 次批次；2 次已被两次登录窗导航占用（seed_from），"
                  "剩 1 次用于登录后搜索"),
            records_cap=RECORDS_CAP,
            seed_from=SEED_FROM,
        )
        print(json.dumps({"batch": batch, "summary": ledger.summary(BATCH)},
                         ensure_ascii=False, indent=1))
    finally:
        ledger.close()
    print(json.dumps({"next": "在 300s 窗口内执行 REPORT.md §4 的 search 命令（恰好 1 次）"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
