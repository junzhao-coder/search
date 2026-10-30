#!/usr/bin/env python
"""Offline synthetic examples for V9 discovery design (stdlib only).

These examples validate *ideas* (platform-agnostic identity, reversible merge,
bounded resumable round); they are not a product implementation, not real user
data, and do not touch any database or network.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


def canon(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity_key(audience: str, task: str, deliverable_family: str, locale: str) -> str:
    return hashlib.sha256(canon({
        "audience": audience.strip().lower(),
        "task": task.strip().lower(),
        "deliverable_family": deliverable_family.strip().lower(),
        "locale": locale.strip().lower(),
    }).encode()).hexdigest()[:16]


@dataclass
class Category:
    id: str
    audience: str
    task: str
    family: str
    locale: str
    status: str = "active"
    merged_into: str | None = None
    aliases: set[str] = field(default_factory=set)
    evidence: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return identity_key(self.audience, self.task, self.family, self.locale)


def match(categories: list[Category], audience, task, family, locale, title: str):
    key = identity_key(audience, task, family, locale)
    for c in categories:
        if c.status == "active" and c.key == key:
            return c, "identity_key"
    norm = title.strip().lower()
    for c in categories:
        if c.status == "active" and norm in c.aliases:
            return c, "alias"
    return None, "review"


def merge(categories: dict[str, Category], source: str, target: str) -> dict:
    a, b = categories[source], categories[target]
    a.status, a.merged_into = "merged", target
    ev = {"op": "merge", "from": source, "to": target,
          "before": {"status": "active"}, "after": {"status": "merged", "merged_into": target}}
    a.events.append(ev)
    b.events.append({**ev, "op": "merge_in"})
    return ev


def unmerge(categories: dict[str, Category], source: str) -> dict:
    a = categories[source]
    if a.status != "merged":
        raise ValueError("not merged")
    a.status, a.merged_into = "active", None
    ev = {"op": "unmerge", "from": source, "before": {"status": "merged"}, "after": {"status": "active"}}
    a.events.append(ev)
    return ev


def run_round(items: list[str], budget: int, pause_after: int | None = None,
              initial_done: set[str] | None = None):
    """At-least-once + unique item key; cursor advances only after committed item."""
    done: list[str] = []
    seen: set[str] = set(initial_done or set())
    state = "running"
    cursor = 0
    for i, item in enumerate(items):
        if len(done) >= budget:
            state = "paused"
            break
        if pause_after is not None and len(done) >= pause_after:
            state = "paused"
            break
        if item in seen:
            cursor = i + 1
            continue
        seen.add(item)
        done.append(item)
        cursor = i + 1
    if len(seen) >= len(items):
        state = "complete"
    return {"state": state, "cursor": cursor, "done": done, "seen": sorted(seen)}


def main() -> int:
    cats = {
        "cat-study": Category("cat-study", "学生/备考", "考试倒计时", "Notion模板", "zh",
                              aliases={"学习计划模板", "study planner"}),
        "cat-crm": Category("cat-crm", "自由职业者", "客户跟进", "Notion模板", "zh"),
    }
    # 1 same demand cross-platform (platform not in key)
    same, why1 = match(list(cats.values()), "学生/备考", "考试倒计时", "Notion模板", "zh",
                       "Notion study planner")
    # 2 synonym rewrite via alias
    syn, why2 = match(list(cats.values()), "学生/备考", "考试倒计时", "Notion模板", "zh",
                      "学习计划模板")
    # 3 same broad family but different audience/task (compare against study, not CRM)
    diff, why3 = match([cats["cat-study"]], "自由职业者", "客户跟进", "Notion模板", "zh",
                       "Notion 模板")
    # 4 old category + new evidence: update, not new
    old_update = {"event": "update", "category": "cat-study", "evidence": "xianyu:old", "new_evidence": "x:new"}
    # 5 merge + undo
    ev = merge(cats, "cat-crm", "cat-study")
    undo = unmerge(cats, "cat-crm")
    # 6 bounded round pause/resume
    first = run_round(["e1", "e2", "e3", "e4"], budget=2, pause_after=2)
    second = run_round(["e1", "e2", "e3", "e4"], budget=2,
                       initial_done=set(first["done"]))
    out = {
        "synthetic": True,
        "not_implementation": True,
        "not_real_user_data": True,
        "identity": {
            "same_cross_platform": {"matched": bool(same), "why": why1, "key": same.key if same else None},
            "synonym": {"matched": bool(syn), "why": why2, "key": syn.key if syn else None},
            "different_task": {"matched": bool(diff), "why": why3},
            "old_evidence_is_update": old_update,
        },
        "merge_undo": {"merge": ev, "undo": undo, "status_after": cats["cat-crm"].status},
        "round": {"first": first, "second": second, "resumed_from_cursor": first["cursor"],
                  "note": "first pauses after budget; second resumes with initial_done=first.done; keys deduped"},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
