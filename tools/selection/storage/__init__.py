"""V18 单帖采集的隔离存储（独立于既有业务库、账本与历史导出）。

    from tools.selection.storage import Storage, Item, export_compat

    with Storage("D:/data/v18.sqlite3") as box:
        run = box.begin_run("tieba", target_native_id="11066015202")
        box.save([Item(platform="tieba", kind="post", native_id="11066015202",
                       text="正文", likes=None, published_at_raw="10-31 12:34")],
                 run_id=run)
        box.finish_run(run, stop_reason="cancelled")
        export_compat(box, "tieba.csv", platform="tieba")

命令行入口：``python -m tools.selection.storage --help``。
"""

from .compat import (DEFAULT_NOT_APPLICABLE, export_compat, export_items,
                     item_from_record, items_from_records, record_from_row)
from .store import (APPLICATION_ID, COMMENT, KINDS, POST, PRECISIONS,
                    SCHEMA_VERSION, STOP_BATCH, STOP_CANCELLED, STOP_END,
                    STOP_ERROR, STOP_NO_MORE, STOP_PAUSED, STOP_PENDING,
                    STOP_REASONS, STOP_RECORDS, STOP_RISK, Item, Storage, utc_now)

__all__ = [
    "APPLICATION_ID", "SCHEMA_VERSION", "COMMENT", "POST", "KINDS", "PRECISIONS",
    "STOP_BATCH", "STOP_CANCELLED", "STOP_END", "STOP_ERROR", "STOP_NO_MORE",
    "STOP_PAUSED", "STOP_PENDING", "STOP_REASONS", "STOP_RECORDS", "STOP_RISK",
    "Item", "Storage", "utc_now", "DEFAULT_NOT_APPLICABLE", "export_compat",
    "export_items", "item_from_record", "items_from_records", "record_from_row",
]
