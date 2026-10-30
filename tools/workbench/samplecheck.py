"""B16：本地文件样品自检（只读；绝不执行文件中的宏或脚本）。

限制：路径 resolve() 后必须位于工作区内 `docs/` 或 `tools/` 下；扩展名白名单
`.xlsx/.pptx/.md/.csv/.pdf`；大小 ≤ 20MB；拒绝 `..` 逃逸与绝对路径逃逸。
"""

from __future__ import annotations

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
ALLOWED_ROOTS = ("docs", "tools")
ALLOWED_EXTS = {".xlsx", ".pptx", ".md", ".csv", ".pdf"}
MAX_BYTES = 20 * 1024 * 1024


def _resolve(path_text: str) -> pathlib.Path:
    raw = str(path_text or "").strip()
    if not raw:
        raise ValueError("路径为空")
    if "\x00" in raw:
        raise ValueError("路径包含非法字符")
    candidate = pathlib.Path(raw)
    if not candidate.is_absolute():
        candidate = ROOT / raw
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"路径无法解析：{exc}") from exc
    try:
        rel = resolved.relative_to(ROOT)
    except ValueError:
        raise ValueError("路径必须位于工作区内")
    if rel.parts and rel.parts[0] not in ALLOWED_ROOTS:
        raise ValueError("只允许 docs/ 或 tools/ 下的文件")
    return resolved


def check_path(path_text: str) -> dict:
    """返回 {ok, path, ext, size, summary, checks[], error}；不修改任何状态。"""
    try:
        path = _resolve(path_text)
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "checks": []}
    if path.suffix.lower() not in ALLOWED_EXTS:
        return {"ok": False, "path": str(path), "error": f"扩展名不在白名单：{path.suffix}", "checks": []}
    if not path.exists() or not path.is_file():
        return {"ok": False, "path": str(path), "error": "文件不存在", "checks": []}
    size = path.stat().st_size
    if size > MAX_BYTES:
        return {"ok": False, "path": str(path), "error": f"文件超过 20MB（{size} B）", "checks": []}
    checks: list[dict] = [{"item": "存在与大小", "ok": True, "detail": f"{size} B"}]
    ext = path.suffix.lower()
    try:
        if ext == ".xlsx":
            _check_xlsx(path, checks)
        elif ext == ".pptx":
            _check_pptx(path, checks)
        elif ext in (".md", ".csv"):
            _check_text(path, checks)
        else:
            _check_pdf(path, checks)
    except Exception as exc:  # noqa: BLE001
        checks.append({"item": "解析", "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
    ok = all(c["ok"] for c in checks)
    summary = "; ".join(f'{c["item"]}:{c["detail"]}' for c in checks)
    return {"ok": ok, "path": str(path.relative_to(ROOT)), "ext": ext, "size": size,
            "checks": checks, "summary": summary}


def _check_xlsx(path: pathlib.Path, checks: list[dict]) -> None:
    try:
        import openpyxl
    except ImportError:
        _check_xlsx_stdlib(path, checks)
        return
    wb = openpyxl.load_workbook(path, read_only=True, data_only=False)
    try:
        sheets = wb.sheetnames
        formulas = nonempty = 0
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    nonempty += 1
                    if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("=")):
                        formulas += 1
        checks.append({"item": "sheets", "ok": len(sheets) >= 1, "detail": f"{len(sheets)} 张（{', '.join(sheets[:5])}）"})
        checks.append({"item": "非空单元格", "ok": nonempty > 0, "detail": str(nonempty)})
        checks.append({"item": "公式", "ok": True, "detail": str(formulas)})
        ext_links = getattr(wb, "_external_links", []) or []
        checks.append({"item": "外部链接", "ok": len(ext_links) == 0, "detail": f"{len(ext_links)} 个"})
    finally:
        wb.close()
    with zipfile.ZipFile(path) as zf:
        vba = [n for n in zf.namelist() if n.lower().endswith("vbaproject.bin")]
    checks.append({"item": "宏(vbaProject)", "ok": len(vba) == 0, "detail": "无" if not vba else f"{len(vba)} 个"})


def _check_xlsx_stdlib(path: pathlib.Path, checks: list[dict]) -> None:
    """openpyxl 不可用时的只读兜底：直接解析 xlsx 的 zip/XML（仍不执行任何内容）。"""
    import re as _re
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        sheet_files = [n for n in names if _re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
        formulas = nonempty = 0
        for name in sheet_files:
            xml = zf.read(name).decode("utf-8", "replace")
            formulas += xml.count("<f>") + xml.count("<f ")
            nonempty += len(_re.findall(r'<c [^>]*>.*?</c>', xml))
        external = [n for n in names if n.startswith("xl/externalLinks/")]
        vba = [n for n in names if n.lower().endswith("vbaproject.bin")]
        checks.append({"item": "sheets", "ok": len(sheet_files) >= 1,
                       "detail": f"{len(sheet_files)} 张（stdlib 解析）"})
        checks.append({"item": "非空单元格", "ok": nonempty > 0, "detail": str(nonempty)})
        checks.append({"item": "公式", "ok": True, "detail": str(formulas)})
        checks.append({"item": "外部链接", "ok": len(external) == 0, "detail": f"{len(external)} 个"})
        checks.append({"item": "宏(vbaProject)", "ok": len(vba) == 0, "detail": "无" if not vba else f"{len(vba)} 个"})
        checks.append({"item": "解析器", "ok": True, "detail": "openpyxl 不可用，已回退 stdlib（只读）"})


def _check_pptx(path: pathlib.Path, checks: list[dict]) -> None:
    try:
        from pptx import Presentation
    except ImportError:
        with zipfile.ZipFile(path) as zf:
            slides = len([n for n in zf.namelist() if n.startswith("ppt/slides/slide")])
            vba = [n for n in zf.namelist() if n.lower().endswith("vbaproject.bin")]
        checks.append({"item": "slides", "ok": slides >= 1, "detail": f"{slides}（stdlib 解析）"})
        checks.append({"item": "宏(vbaProject)", "ok": len(vba) == 0,
                       "detail": "无" if not vba else f"{len(vba)} 个"})
        checks.append({"item": "解析器", "ok": True, "detail": "python-pptx 不可用，已回退 stdlib（只读）"})
        return
    prs = Presentation(str(path))
    slides = len(prs.slides)
    checks.append({"item": "slides", "ok": slides >= 1, "detail": str(slides)})
    with zipfile.ZipFile(path) as zf:
        vba = [n for n in zf.namelist() if n.lower().endswith("vbaproject.bin")]
    checks.append({"item": "宏(vbaProject)", "ok": len(vba) == 0, "detail": "无" if not vba else f"{len(vba)} 个"})


def _check_text(path: pathlib.Path, checks: list[dict]) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.count("\n") + (1 if text else 0)
    checks.append({"item": "UTF-8 可读", "ok": True, "detail": "ok"})
    checks.append({"item": "行数", "ok": lines > 0, "detail": str(lines)})


def _check_pdf(path: pathlib.Path, checks: list[dict]) -> None:
    head = path.read_bytes()[:8]
    checks.append({"item": "PDF 头部", "ok": head.startswith(b"%PDF-"), "detail": head.decode("latin-1", "replace")[:8]})


def check_and_apply(conn, workorder_id: str, *, path_text: str, revision) -> dict:
    """通过 → sample_status=verified + sample_ref；失败 → 状态不变，返回原因。"""
    import readiness as rd
    import workflow as wf
    wf.init_schema(conn)
    record = wf.get(conn, workorder_id)
    if record is None:
        raise wf.Reject("not_found", "工作单不存在", 404)
    raw = str(revision).strip() if revision is not None else ""
    if not raw.isdigit():
        raise wf.Reject("revision_invalid", f"revision 必须是 ASCII 正整数（收到 {revision!r}）")
    rev = int(raw)
    if rev != int(record["revision"]):
        raise wf.Reject("revision_conflict", f"版本冲突：当前 revision={record['revision']}，提交 {rev}", 409)
    result = check_path(path_text)
    if not result["ok"]:
        return {"applied": False, "result": result}
    note = f'{result["path"]}（{result["size"]} B）：{result["summary"]}'
    now = __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime())
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("UPDATE workorder SET sample_status='verified', sample_ref=?, revision=revision+1, "
                           "updated_at=? WHERE workorder_id=? AND revision=?",
                           (note[:900], now, workorder_id, rev))
        if cur.rowcount != 1:
            conn.rollback()
            raise wf.Reject("revision_conflict", "版本冲突：UPDATE 命中 0 行，本次未写入", 409)
        conn.execute("INSERT INTO workorder_event (workorder_id, action, detail, at) VALUES (?,?,?,?)",
                     (workorder_id, "sample_check", f'ok {result["path"]}', now))
        conn.commit()
    except wf.Reject:
        raise
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        raise wf.Reject("update_failed", f"写回失败已回滚：{type(exc).__name__}", 409)
    return {"applied": True, "result": result, "record": wf.get(conn, workorder_id)}
