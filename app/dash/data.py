"""Read-only dashboard data loaders (stdlib only)."""

from __future__ import annotations

import csv
import datetime
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: All paths are relative to the project root (or DASH_DATA_ROOT in tests).
SOURCES = [
    ("scores", "docs/validation/money-project/scoring/scores.csv", "csv"),
    ("scoring_report", "docs/validation/money-project/scoring/report.md", "text"),
    ("sources", "docs/validation/money-project/sourcing/sources.csv", "csv"),
    ("prices", "docs/validation/money-project/sourcing/price_signals.csv", "csv"),
    ("join", "docs/validation/money-project/sourcing/opportunity_sourcing_top10.csv", "csv"),
    ("xianyu", "tools/platform-login/data/xianyu_items.jsonl", "jsonl"),
    ("xiaohongshu", "tools/platform-login/data/xiaohongshu_items.jsonl", "jsonl"),
    ("topic_top20", "docs/validation/x-collect/topic-crawler/top20.md", "text"),
    ("topic_summary", "docs/validation/x-collect/topic-crawler/filtered/summary.csv", "csv"),
]

FALLBACKS = {
    "xianyu": ["login/data/xianyu_items.jsonl"],
    "xiaohongshu": ["login/data/xiaohongshu_items.jsonl"],
}


def utc_from_ts(ts: float | None) -> str:
    if not ts:
        return "暂无数据"
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_csv(path: pathlib.Path) -> tuple[list[dict], str | None]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh)), None
    except FileNotFoundError:
        return [], "文件缺失"
    except Exception as exc:  # noqa: BLE001
        return [], f"读取失败：{type(exc).__name__}"


def read_jsonl(path: pathlib.Path) -> tuple[list[dict], int, str | None]:
    rows, bad = [], 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    except FileNotFoundError:
        return [], 0, "文件缺失"
    except Exception as exc:  # noqa: BLE001
        return [], bad, f"读取失败：{type(exc).__name__}"
    return rows, bad, None


def read_text(path: pathlib.Path) -> tuple[str, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return "", "文件缺失"
    except Exception as exc:  # noqa: BLE001
        return "", f"读取失败：{type(exc).__name__}"


def _resolve(root: pathlib.Path, key: str, rel: str) -> pathlib.Path:
    path = root / rel
    if path.exists():
        return path
    for alt in FALLBACKS.get(key, []):
        alt_path = root / alt
        if alt_path.exists():
            return alt_path
    return path


def _num(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def load_dashboard_data(root: str | pathlib.Path | None = None) -> dict:
    """Load all files; never raises for missing/corrupt files."""
    base = pathlib.Path(root) if root else ROOT
    datasets: dict[str, dict] = {}
    warnings: list[str] = []
    content: dict[str, object] = {}

    for key, rel, kind in SOURCES:
        path = _resolve(base, key, rel)
        entry = {"key": key, "path": str(path.relative_to(base)) if path.is_relative_to(base) else str(path),
                 "exists": path.exists(), "kind": kind, "count": 0, "bad_lines": 0,
                 "mtime": utc_from_ts(path.stat().st_mtime if path.exists() else None),
                 "error": None, "size": path.stat().st_size if path.exists() else 0}
        if kind == "csv":
            rows, err = read_csv(path)
            content[key] = rows
            entry["count"] = len(rows)
        elif kind == "jsonl":
            rows, bad, err = read_jsonl(path)
            content[key] = rows
            entry["count"] = len(rows)
            entry["bad_lines"] = bad
        else:
            text, err = read_text(path)
            content[key] = text
            entry["count"] = len(text.splitlines()) if text else 0
        entry["error"] = err
        if err:
            warnings.append(f"{rel}：{err}")
        elif entry["bad_lines"]:
            warnings.append(f"{rel}：跳过 {entry['bad_lines']} 条坏 JSONL")
        datasets[key] = entry

    scores = content.get("scores", [])
    scores = sorted(scores, key=lambda r: _num(r, "total_score"), reverse=True)
    sources = content.get("sources", [])
    prices = content.get("prices", [])
    join = content.get("join", [])
    xianyu = content.get("xianyu", [])
    xhs = content.get("xiaohongshu", [])

    verdicts = {}
    for row in sources:
        verdict = row.get("license_verdict") or "未知"
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    effective = []
    for row in prices:
        try:
            effective.append(float(row.get("effective_price")))
        except (TypeError, ValueError):
            continue
    wants = []
    for row in prices:
        try:
            wants.append(int(float(row.get("wants"))))
        except (TypeError, ValueError):
            continue

    top20_text = content.get("topic_top20", "")
    top20 = []
    for line in top20_text.splitlines():
        if line[:2].strip().rstrip(".").isdigit() and "|" in line:
            top20.append(line.strip())
    topic_summary = content.get("topic_summary", [])

    latest = max((entry["mtime"] for entry in datasets.values() if entry["mtime"] != "暂无数据"),
                 default="暂无数据")
    counts = {key: entry["count"] for key, entry in datasets.items()}
    return {
        "root": str(base),
        "datasets": datasets,
        "warnings": warnings,
        "generated_at": latest,
        "scores": scores,
        "sources": sources,
        "prices": prices,
        "join": join,
        "xianyu": xianyu,
        "xiaohongshu": xhs,
        "top20": top20,
        "topic_summary": topic_summary,
        "counts": counts,
        "license_verdicts": verdicts,
        "price_stats": {"count": len(prices), "effective_min": min(effective) if effective else None,
                        "effective_max": max(effective) if effective else None,
                        "wants_count": len(wants), "wants_sum": sum(wants) if wants else 0},
    }


__all__ = ["load_dashboard_data", "ROOT"]
