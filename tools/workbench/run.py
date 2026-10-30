"""启动本地机会工作台（仅 127.0.0.1；零业务库写入；不依赖 DSH）。

用法：
  python tools/workbench/run.py                # 默认 5015，自动打开浏览器
  python tools/workbench/run.py --no-browser   # 供测试/无头环境
  python tools/workbench/run.py --port 5016
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser

DEFAULT_PORT = 5015
HOST = "127.0.0.1"


def port_in_use(host: str, port: int) -> bool:
    """Windows 上不能用 SO_REUSEADDR 探测（会误判已被监听的端口为空闲）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return True
    return False


def _is_workbench(port: int) -> bool:
    """端口上跑的是不是本工作台：只认 /healthz 的本工作台 JSON（不杀任何进程）。"""
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://{host_url(port)}/healthz", timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return isinstance(data, dict) and data.get("status") == "ok" and "counts" in data
    except Exception:
        return False


def host_url(port: int) -> str:
    return f"{HOST}:{port}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地机会工作台（只读）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)

    if port_in_use(HOST, args.port):
        if _is_workbench(args.port):
            url = f"http://{HOST}:{args.port}/"
            print("本地机会工作台已在运行：")
            print(f"  地址：{url}（PID 请用任务管理器或 netstat 查看）")
            print("  无需重复启动；如需重启，请在原窗口按 Ctrl+C 后再运行。")
            if not args.no_browser:
                webbrowser.open(url)
            return 0
        print(f"[错误] 端口 {args.port} 已被占用。请换一个端口：", file=sys.stderr)
        print(f"       python tools/workbench/run.py --port {args.port + 1}", file=sys.stderr)
        print("       本程序不会结束其它进程。", file=sys.stderr)
        return 3

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    from app import create_app  # noqa: PLC0415  (延迟导入，确保端口检查先行)

    application = create_app()
    url = f"http://{HOST}:{args.port}/"
    print("本地机会工作台已启动（只读）")
    print(f"  地址：{url}")
    print(f"  进程 PID：{os.getpid()}   绑定：{HOST}（仅本机）")
    print("  停止：在本窗口按 Ctrl+C；关闭窗口亦可")
    print("  说明：不写入业务库；数据每次请求时从本地产物重新读取")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        application.run(host=HOST, port=args.port, debug=False, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n已停止。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
