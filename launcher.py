import socket
import threading
import webbrowser

import uvicorn

from settings_store import apply_runtime_settings


def find_open_port(preferred=8000):
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free localhost port was available for the app.")


def open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")


def main():
    apply_runtime_settings()
    port = find_open_port(8000)
    timer = threading.Timer(1.5, open_browser, args=(port,))
    timer.daemon = True
    timer.start()
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
