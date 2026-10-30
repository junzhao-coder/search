"""重建 source_manifest.json：自动扫描 raw/ 全部原始件（UTF-8 严格解码校验 + sha256 + UTC 时间），
并给出关键 URL→文件映射。仅写本 scope。"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time

ROOT = pathlib.Path(r"D:\桌面\two\docs\validation\v9\research-collection")
RAW = ROOT / "raw"

# 关键 URL → 文件（未列出者为 GitHub API/raw 的其它抓取件，文件内自带可核对信息）
URL_MAP = {
    "gh_search_q_mediacrawler.json": "https://api.github.com/search/repositories?q=MediaCrawler&sort=stars&order=desc&per_page=10",
    "gh_search_q_multi_cn.json": "https://api.github.com/search/repositories?q=多平台 采集 评论 爬虫&sort=stars&order=desc&per_page=10",
    "gh_search_q_xhs_comment.json": "https://api.github.com/search/repositories?q=xhs 评论 爬虫&sort=stars&order=desc&per_page=10",
    "gh_search_q_xianyu.json": "https://api.github.com/search/repositories?q=闲鱼 爬虫 商品 采集&sort=stars&order=desc&per_page=8",
    "gh_search_q_bili_comment.json": "https://api.github.com/search/repositories?q=bilibili 评论 爬虫&sort=stars&order=desc&per_page=8",
    "gh_search_catbus.json": "https://api.github.com/search/repositories?q=catbus&sort=stars&order=desc&per_page=6",
    "gh_search_小红书_抖音_B站_微博_贴吧_采集_CLI.json": "https://api.github.com/search/repositories?q=小红书 抖音 B站 微博 贴吧 采集 CLI（total=0）",
    "gh_repo_NanmiCoder__MediaCrawler.json": "https://api.github.com/repos/NanmiCoder/MediaCrawler",
    "gh_repo_cv-cat__catbus.json": "https://api.github.com/repos/cv-cat/catbus（该件为 PowerShell .Content 解码，中文描述可能失真；数值字段已核对）",
    "gh_repo_Cialle__RedCrack.json": "https://api.github.com/repos/Cialle/RedCrack",
    "gh_repo_dataabc__weibo-crawler.json": "https://api.github.com/repos/dataabc/weibo-crawler",
    "gh_repo_Nemo2011__bilibili-api.json": "https://api.github.com/repos/Nemo2011/bilibili-api",
    "gh_commit_NanmiCoder__MediaCrawler.json": "https://api.github.com/repos/NanmiCoder/MediaCrawler/commits?per_page=1（sha 8f58399…）",
    "gh_commit_cv-cat__catbus.json": "https://api.github.com/repos/cv-cat/catbus/commits?per_page=1（sha 0a6e705…）",
    "gh_commit_Cialle__RedCrack.json": "https://api.github.com/repos/Cialle/RedCrack/commits?per_page=1（sha a557e32…）",
    "gh_commit_Ghauster__BilibiliCommentScraper.json": "https://api.github.com/repos/Ghauster/BilibiliCommentScraper/commits?per_page=1（sha 0b39e06…, 2023-04-25）",
    "commit_locks.json": "4 个候选的 commit sha/时间/链接汇总",
    "gh_tree_catbus.json": "https://api.github.com/repos/cv-cat/catbus/git/trees/0a6e705…?recursive=1",
    "gh_tree_RedCrack.json": "https://api.github.com/repos/Cialle/RedCrack/git/trees/a557e32…?recursive=1",
    "gh_contents_cv-cat__catbus.json": "https://api.github.com/repos/cv-cat/catbus/contents/?ref=master",
    "gh_contents_Cialle__RedCrack.json": "https://api.github.com/repos/Cialle/RedCrack/contents/?ref=master",
    "gh_contents_dataabc__weibo-crawler.json": "https://api.github.com/repos/dataabc/weibo-crawler/contents/?ref=master（无 LICENSE）",
    "gh_contents_Nemo2011__bilibili-api.json": "https://api.github.com/repos/Nemo2011/bilibili-api/contents/?ref=main（无 LICENSE）",
    "license_MediaCrawler.txt": "https://raw.githubusercontent.com/NanmiCoder/MediaCrawler/main/LICENSE（NON-COMMERCIAL LEARNING LICENSE 1.1）",
    "readme_MediaCrawler.md": "https://raw.githubusercontent.com/NanmiCoder/MediaCrawler/main/README.md",
    "pyproject_MediaCrawler.toml": "https://raw.githubusercontent.com/NanmiCoder/MediaCrawler/main/pyproject.toml",
    "src_MediaCrawler_bilibili_core.py": "https://raw.githubusercontent.com/NanmiCoder/MediaCrawler/8f583999006d5b692272c608440e193ca282e73b/media_platform/bilibili/core.py",
    "src_MediaCrawler_bilibili_field.py": "https://raw.githubusercontent.com/NanmiCoder/MediaCrawler/8f583999006d5b692272c608440e193ca282e73b/media_platform/bilibili/field.py",
    "src_MediaCrawler_base_config.py": "https://raw.githubusercontent.com/NanmiCoder/MediaCrawler/8f583999006d5b692272c608440e193ca282e73b/config/base_config.py",
    "license_catbus.txt": "https://raw.githubusercontent.com/cv-cat/catbus/0a6e705f95d991ac3cdc896b774570479a23c0ad/LICENSE（MIT）",
    "readme_catbus.md": "https://raw.githubusercontent.com/cv-cat/catbus/0a6e705f95d991ac3cdc896b774570479a23c0ad/README.md",
    "src_catbus_SKILL.md": "https://raw.githubusercontent.com/cv-cat/catbus/0a6e705f95d991ac3cdc896b774570479a23c0ad/.claude/skills/catbus/SKILL.md",
    "src_catbus_capabilities.md": "https://raw.githubusercontent.com/cv-cat/catbus/0a6e705f95d991ac3cdc896b774570479a23c0ad/docs/capabilities.md",
    "src_catbus_errors.md": "https://raw.githubusercontent.com/cv-cat/catbus/0a6e705f95d991ac3cdc896b774570479a23c0ad/.claude/skills/catbus/workflows/errors.md",
    "src_catbus_confirm.ts": "https://raw.githubusercontent.com/cv-cat/catbus/0a6e705f95d991ac3cdc896b774570479a23c0ad/src/cli/confirm.ts",
    "src_catbus_auth_handlers.ts": "https://raw.githubusercontent.com/cv-cat/catbus/0a6e705f95d991ac3cdc896b774570479a23c0ad/src/core/auth-handlers.ts",
    "license_RedCrack.txt": "https://raw.githubusercontent.com/Cialle/RedCrack/a557e328b6e723f63dcd75f1c52640794f2c84b5/LICENSE（MIT）",
    "readme_RedCrack.md": "https://raw.githubusercontent.com/Cialle/RedCrack/a557e328b6e723f63dcd75f1c52640794f2c84b5/README.md",
    "src_RedCrack_comments.py": "https://raw.githubusercontent.com/Cialle/RedCrack/a557e328b6e723f63dcd75f1c52640794f2c84b5/request/web/apis/comments.py",
    "license_BilibiliCommentScraper.txt": "https://raw.githubusercontent.com/Ghauster/BilibiliCommentScraper/0b39e0659c78fe695d2c675edc1f9c0042935ee4/LICENSE（MIT）",
    "readme_BilibiliCommentScraper.md": "https://raw.githubusercontent.com/Ghauster/BilibiliCommentScraper/0b39e0659c78fe695d2c675edc1f9c0042935ee4/README.md",
    "readme_weibo-crawler.md": "https://raw.githubusercontent.com/dataabc/weibo-crawler/master/README.md",
    "readme_ECommerceCrawlers.md": "https://raw.githubusercontent.com/DropsDevopsOrg/ECommerceCrawlers/master/README.md",
}

TOOLING = {
    "skill_tool": "absent — 本会话函数表无 skill 工具，未“加载技能”",
    "agent_reach_cli": "absent — PATH 上 agent-reach/reach/agentreach/areach 均 not found",
    "stealth_browser_mcp": "absent — 本会话无可调用 mcp__stealth__* 工具",
    "github_api": "ok — 60/hr；本次共 21 次（rate_limit 1 + 检索 7 + repo 5 + contents 4 + commits 4）",
    "raw_githubusercontent": "ok — 统一「下载字节→UTF-8 严格解码→LF」；44 件全部严格解码通过",
    "web_search_site_x_com": "站点限定检索未命中（2 组查询，0 条 X 原帖）；唯一线索为第三方 V2EX 帖→cv-cat/catbus",
    "x_collect_cli": "ok（只读）— --help exit=0；doctor exit=0，handle=@Johnsmathjyjp utc=2026-10-25T05:23:40Z；未运行 search（输出落工具目录，超出本 scope）",
    "npx_catbus": "未安装、未运行（npx 可能触发下载与执行，不称“无执行干跑”）",
}

CORRECTIONS = [
    "BiliScraper 末次 commit 2023-04-25；距观测日 2026-10-25＝42 个月（repo pushed_at 2024-02-21＝32 个月）——删除“停更约 1.5 年”",
    "readme_BilibiliCommentScraper.md 与 readme_BilibiliCommentScraper_master.md 的 sha256 相同（重复件、内容一致），上一版“不同版本”有误",
    "44 个原始件全部通过 UTF-8 严格解码（bad=0）；上一版“字段乱码”是控制台按 ANSI 显示所致，文件未损坏",
    "issue 数一律写 open_issues_count 计数，标注“不等于已核对的已知故障”",
    "catbus 降级为“待验证候选”，不作为全局依赖；未运行 npx/--help",
    "首批范围改为 P1/P2/P3 三条与“≥3 平台且含交易源”相容的路径（提案，非裁定）",
]


def main() -> int:
    files, bad = [], []
    for p in sorted(RAW.iterdir()):
        if not p.is_file():
            continue
        b = p.read_bytes()
        try:
            b.decode("utf-8")
            utf8 = "ok"
        except UnicodeDecodeError as exc:
            utf8 = f"BAD: {exc.reason}@{exc.start}"
            bad.append(p.name)
        files.append({
            "file": f"raw/{p.name}",
            "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest(),
            "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(p.stat().st_mtime)),
            "utf8_strict": utf8,
            "source_url": URL_MAP.get(p.name, "（GitHub API/raw 抓取件；未逐件登记 URL）"),
        })
    dup = {}
    for f in files:
        dup.setdefault(f["sha256"], []).append(f["file"])
    dupes = [v for v in dup.values() if len(v) > 1]

    payload = {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scope": "docs/validation/v9/research-collection",
        "method": "GitHub REST API + raw.githubusercontent（按 commit sha 取件）＋ 本项目 x-collect CLI 只读 --help/doctor；文本统一「字节→UTF-8 严格解码→LF」；未运行任何候选程序",
        "tooling": TOOLING,
        "corrections_in_this_revision": CORRECTIONS,
        "file_count": len(files),
        "utf8_bad_files": bad,
        "identical_sha_groups": dupes,
        "files": files,
        "external_probe": {
            "log": "x_collect_probe.log",
            "note": "本项目自有 X 工具：--help exit=0；doctor exit=0，LOGGED_IN handle=@Johnsmathjyjp；未读 cookie 值、未登录、未发布",
        },
    }
    out = ROOT / "source_manifest.json"
    out.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"wrote source_manifest.json files={len(files)} utf8_bad={bad} dupes={dupes}")
    for name in ("RESEARCH.md", "source_manifest.json", "x_collect_probe.log"):
        b = (ROOT / name).read_bytes()
        print(f"{name}: {len(b)}B bom={b.startswith(b'\xef\xbb\xbf')} crlf={b'\r\n' in b}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
