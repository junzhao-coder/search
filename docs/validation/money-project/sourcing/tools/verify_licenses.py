#!/usr/bin/env python
"""Verify licenses for the 10 GitHub repos from the accepted scoring sample.

Rules:
- Prefer API license.spdx_id (already in raw/github_search.json).
- If spdx_id is null/NOASSERTION, fetch /repos/{full_name}/license and read the
  first 40 decoded lines; never infer from repo name.
"""

from __future__ import annotations

import base64
import datetime
import json
import pathlib
import re
import urllib.error
import urllib.request

BASE = pathlib.Path(__file__).resolve().parents[1]
SCORING = BASE.parent / "scoring"
RAW = BASE / "raw"
LICENSES = RAW / "licenses"
LOGS = BASE / "logs"
PROXY = "http://127.0.0.1:10808"
UA = "Mozilla/5.0 (compatible; DSH-sourcing-check/1.0)"


def utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify(spdx: str | None, text: str) -> tuple[str, str]:
    """Return (verdict, reason)."""
    value = f"{spdx or ''}\n{text}".upper()
    if "CREATIVE COMMONS ATTRIBUTION" in value:
        if "NONCOMMERCIAL" in value:
            return "禁止或不明", "CC BY-NC: non-commercial restriction; not usable commercially"
        return "需授权", "CC BY: commercial use allowed only with attribution (署名)"
    if re.search(r"\bMIT\b|\bAPACHE\b|\bBSD-3\b|\bBSD 3\b", value) and "NOASSERTION" not in value:
        return "可商用", "permissive license (MIT/Apache/BSD)"
    if re.search(r"\bGPL\b|\bAGPL\b|\bMPL\b|\bLGPL\b", value):
        return "需授权", "copyleft/share-alike license requires obligations"
    if not text.strip():
        return "禁止或不明", "no LICENSE file / no license text"
    return "禁止或不明", "license text is custom/unclear; cannot confirm commercial use"


def fetch_license(full_name: str) -> dict:
    url = f"https://api.github.com/repos/{full_name}/license"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    last_error = None
    last_status = 0
    for proxy in (PROXY, None):
        handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
        opener = urllib.request.build_opener(*handlers)
        try:
            with opener.open(req, timeout=30) as response:
                status = response.status
                body = response.read().decode("utf-8")
            data = json.loads(body)
            content = base64.b64decode(data.get("content") or "").decode("utf-8", errors="replace")
            first = [line.strip() for line in content.splitlines() if line.strip()][:40]
            return {"status": status, "api": data, "text": "\n".join(first),
                    "license_url": data.get("html_url") or url, "error": None}
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
    return {"status": last_status, "api": None, "text": "", "license_url": url,
            "error": last_error}


def main() -> int:
    LICENSES.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    source = json.loads((SCORING / "raw" / "github_search.json").read_text(encoding="utf-8"))["items"]
    extra_path = BASE / "raw" / "github_extra_selected.json"
    if extra_path.exists():
        source += json.loads(extra_path.read_text(encoding="utf-8"))["items"]
    checked_at = utc()
    results = []
    for index, item in enumerate(source, 1):
        full = item["full_name"]
        api_lic = item.get("license") or {}
        spdx = api_lic.get("spdx_id")
        row = {
            "source_index": index,
            "full_name": full,
            "html_url": item.get("html_url"),
            "stars": item.get("stargazers_count"),
            "forks": item.get("forks_count"),
            "pushed_at": item.get("pushed_at"),
            "language": item.get("language"),
            "api_spdx": spdx,
            "api_license_name": api_lic.get("name"),
            "checked_at": checked_at,
        }
        if spdx and str(spdx).upper() != "NOASSERTION":
            row.update({"license_source": "api_license", "license_spdx": spdx,
                        "license_text_first40": (api_lic.get("name") or ""),
                        "license_url": row["html_url"] + "/blob/HEAD/LICENSE",
                        "http_status": None, "error": None})
        else:
            fetched = fetch_license(full)
            filename = LICENSES / (full.replace("/", "__") + ".json")
            filename.write_text(json.dumps(fetched, ensure_ascii=False, indent=1),
                                encoding="utf-8", newline="\n")
            row.update({"license_source": "license_file", "license_spdx": spdx,
                        "license_text_first40": fetched["text"],
                        "license_url": fetched["license_url"],
                        "http_status": fetched["status"], "error": fetched["error"]})
        verdict, reason = classify(row["license_spdx"], row["license_text_first40"])
        row["license_verdict"] = verdict
        row["license_reason"] = reason
        results.append(row)
        print(f"{index:02d} {full:<55} spdx={spdx!s:<14} source={row['license_source']:<13} "
              f"http={row['http_status']} verdict={verdict}")

    out = BASE / "raw" / "license_checks.json"
    out.write_text(json.dumps({"checked_at": checked_at, "count": len(results), "results": results},
                              ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (LOGS / "license_check.log").write_text(
        json.dumps({"checked_at": checked_at, "count": len(results),
                    "verdicts": {v: sum(1 for r in results if r["license_verdict"] == v)
                                 for v in ("可商用", "需授权", "禁止或不明")}},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
