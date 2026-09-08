from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser


HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def choose_port(preferred: int = DEFAULT_PORT) -> int:
    """Return the first available local port in DataForge's port range."""
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"无法在 {preferred}–{preferred + 19} 范围内找到可用端口。")


def open_browser_when_ready(url: str, timeout: float = 30.0) -> None:
    """Open the app only after its local HTTP server is ready."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                webbrowser.open(url)
                return
        except Exception:
            time.sleep(0.25)


def main() -> None:
    port = choose_port(int(os.environ.get("DATAFORGE_PORT", DEFAULT_PORT)))
    os.environ["DATAFORGE_PORT"] = str(port)

    if "--check" in sys.argv:
        import nicegui
        import ultralytics

        print(f"DataForge 启动环境正常：Python {sys.version.split()[0]}")
        print(f"NiceGUI {nicegui.__version__}，Ultralytics {ultralytics.__version__}")
        print(f"可用地址：http://{HOST}:{port}")
        return

    url = f"http://{HOST}:{port}"
    print(f"正在启动炼数 DataForge：{url}")
    print("请保持此窗口打开；关闭窗口将停止 DataForge。")
    threading.Thread(target=open_browser_when_ready, args=(url,), daemon=True).start()

    import app as dataforge_app

    dataforge_app.main()


if __name__ == "__main__":
    main()
