import logging
import socket
import sys
import threading
import webbrowser

import uvicorn

from settings_store import apply_runtime_settings, user_data_dir


def find_open_port(preferred=8000):
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free localhost port was available for the app.")


def open_browser(port):
    webbrowser.open(f"http://127.0.0.1:{port}")


def configure_logging():
    log_dir = user_data_dir()
    log_file = log_dir / "app-launcher.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        filename=str(log_file),
        filemode="a",
    )
    return log_file


def install_exception_hook():
    def handle_exception(exc_type, exc_value, exc_traceback):
        logging.getLogger("launcher").exception(
            "Unhandled exception in packaged app",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = handle_exception


def main():
    apply_runtime_settings()
    log_file = configure_logging()
    install_exception_hook()
    logging.getLogger("launcher").info("Starting Video Translation Studio")
    from app import app as fastapi_app

    port = find_open_port(8000)
    timer = threading.Timer(1.5, open_browser, args=(port,))
    timer.daemon = True
    timer.start()
    logging.getLogger("launcher").info("Opening local server on port %s", port)
    try:
        uvicorn.run(
            fastapi_app,
            host="127.0.0.1",
            port=port,
            reload=False,
            log_level="info",
            log_config=None,
            access_log=True,
        )
    except Exception:
        logging.getLogger("launcher").exception("Launcher failed. Check %s", log_file)
        raise


if __name__ == "__main__":
    main()
