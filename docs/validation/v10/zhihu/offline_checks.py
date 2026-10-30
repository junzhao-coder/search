"""Offline check driver: the two test modules plus CLI smoke checks.

Writes stdout/stderr/exit logs under docs/validation/v10/zhihu/logs/.
No network, no browser, no Zhihu host: transports are refused or fixtures, and
the login flow is exercised through the unit tests' fake browser only.

State dirs are per-scenario-family, so a 15s inter-call interval or an existing
lock cannot mask a later scenario: `_state` for the main CLI flow, `_state_risk`
for the risk lock, and separate fresh dirs for the detail success path, the
comments success path and the login-wall lock. All are created fresh on every run.

Run from the repo root:
    <python> docs/validation/v10/zhihu/offline_checks.py
Exit 0 only when every scenario produced its expected exit code.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[4]
LOGS = REPO / "docs" / "validation" / "v10" / "zhihu" / "logs"
FIXTURES = REPO / "docs" / "validation" / "v10" / "zhihu" / "fixtures"
STATE_MAIN = LOGS / "_state"
STATE_RISK = LOGS / "_state_risk"
STATE_DETAIL = LOGS / "_state_detail"
STATE_COMMENTS = LOGS / "_state_comments"
STATE_LOGIN_WALL = LOGS / "_state_login_wall"
PY = sys.executable
ANSWER = "https://www.zhihu.com/question/900/answer/111"


def run(name: str, argv: list[str], *, expect: int = 0) -> dict:
    started = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(REPO)}
    proc = subprocess.run(argv, cwd=str(REPO), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=300)
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / f"{name}.stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (LOGS / f"{name}.stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    record = {"name": name, "argv": argv, "cwd": str(REPO), "started_utc": started,
              "finished_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "expect": expect, "exit": proc.returncode,
              "match": proc.returncode == expect,
              "stdout_chars": len(proc.stdout or ""), "stderr_chars": len(proc.stderr or "")}
    print(json.dumps(record, ensure_ascii=False))
    return record


def main() -> int:
    for directory in (STATE_MAIN, STATE_RISK, STATE_DETAIL, STATE_COMMENTS,
                      STATE_LOGIN_WALL):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)

    base = [PY, "-m", "tools.selection.access.zhihu"]
    main_state = [*base, "--state-dir", str(STATE_MAIN)]
    risk_state = [*base, "--state-dir", str(STATE_RISK)]
    detail_state = [*base, "--state-dir", str(STATE_DETAIL)]
    comments_state = [*base, "--state-dir", str(STATE_COMMENTS)]
    login_wall_state = [*base, "--state-dir", str(STATE_LOGIN_WALL)]

    results = [
        run("unittest", [PY, "-m", "unittest", "-v",
                         "tests.test_access_budget", "tests.test_access_zhihu"]),
        run("cli_help", [*base, "--help"]),
        run("cli_login_help", [*base, "login", "--help"]),
        run("cli_doctor", [*main_state, "doctor"]),
        run("cli_search_offline", [*main_state, "search", "周计划模板",
                                   "--input", str(FIXTURES / "search_v3.json")]),
        run("cli_budget", [*main_state, "budget", "--ledger", "6"]),
        # second call in the same budget, immediately: interval guard, exit 6
        run("cli_search_second_offline", [*main_state, "search", "第二个词",
                                          "--input", str(FIXTURES / "search_v3.json")],
            expect=6),
        # relabel with a fresh-looking id must not reset anything (still exit 6)
        run("cli_relabel_no_reset", [*main_state, "--batch-id", "brand-new-looking-id",
                                     "search", "第三个词",
                                     "--input", str(FIXTURES / "search_v3.json")],
            expect=6),
        run("cli_budget_after_relabel", [*main_state, "budget", "--ledger", "8"]),
        # fresh state dirs: the 15s interval from the search calls above cannot
        # block the detail/comments success paths
        run("cli_detail_offline", [*detail_state, "--batch-id", "detail-label",
                                   "detail", ANSWER,
                                   "--input", str(FIXTURES / "detail.html")]),
        run("cli_comments_offline", [*comments_state, "--batch-id", "comments-label",
                                     "comments", ANSWER,
                                     "--input", str(FIXTURES / "comments_v5.json")]),
        run("cli_export", [*main_state, "export",
                           "--input", str(FIXTURES / "records.jsonl"),
                           "--output", str(LOGS / "export_out.jsonl")]),
        run("cli_export_secrets", [*main_state, "export",
                                   "--input", str(FIXTURES / "records_secrets.jsonl"),
                                   "--output", str(LOGS / "export_secrets_out.jsonl")]),
        run("cli_export_missing", [*main_state, "export",
                                   "--input", str(FIXTURES / "does_not_exist.jsonl")],
            expect=9),
        # missing --input file on a network command: exit 8, no call charged
        run("cli_input_missing", [*main_state, "--batch-id", "input-check",
                                  "search", "任意词",
                                  "--input", str(FIXTURES / "does_not_exist.json")],
            expect=8),
        run("cli_import_smoke", [PY, "-c",
                                 "import tools.selection.access.zhihu as z;"
                                 "import tools.selection.access.browser as b;"
                                 "print(z.EXIT_OK, b.SIGNED_IN_JS[:10])"]),
    ]

    # --- risk / lock scenario: default path, exactly what a user would run ---
    results.append(run("risk_first_call", [*risk_state, "detail", ANSWER,
                                           "--input", str(FIXTURES / "risk.html")],
                       expect=5))
    results.append(run("risk_restart_refused", [*risk_state, "search", "任意词",
                                                "--input", str(FIXTURES / "search_v3.json")],
                       expect=6))
    results.append(run("risk_relabel_refused", [*risk_state, "--batch-id",
                                                "totally-new-batch",
                                                "search", "任意词",
                                                "--input", str(FIXTURES / "search_v3.json")],
                       expect=6))
    results.append(run("risk_budget_inspect", [*risk_state, "budget", "--ledger", "6"]))
    results.append(run("risk_login_refused", [*risk_state, "login", "--timeout", "1"],
                       expect=6))
    # a second, differently-caused lock (login wall) on its own fresh state dir,
    # so it is not pre-locked by risk_first_call and actually exercises the
    # login-wall detection path
    results.append(run("login_wall_first_call", [*login_wall_state, "--batch-id",
                                                 "offline-login-wall", "detail", ANSWER,
                                                 "--input", str(FIXTURES / "login_wall.html")],
                       expect=5))
    results.append(run("login_wall_restart_refused", [*login_wall_state, "search", "任意词",
                                                      "--input", str(FIXTURES / "search_v3.json")],
                       expect=6))

    summary = {"generated_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "python": PY, "cwd": str(REPO), "runs": results,
               "all_match": all(r["match"] for r in results)}
    (LOGS / "offline_checks.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_match": summary["all_match"],
                      "mismatched": [r["name"] for r in results if not r["match"]]},
                     ensure_ascii=False))
    return 0 if summary["all_match"] else 1


if __name__ == "__main__":
    sys.exit(main())
