"""
WebGap: Desktop entry point
Starts the Flask server in a background thread, waits for it to be ready,
then opens a native PyWebView window (uses Edge WebView2 on Windows).
"""
import sys
import os
import threading
import time

# ── Path resolution (dev vs frozen exe) ───────────────────────────────────────
_FROZEN   = getattr(sys, 'frozen', False)
_BASE_DIR = sys._MEIPASS if _FROZEN else os.path.dirname(os.path.abspath(__file__))

# Ensure our bundled modules are importable when frozen
if _FROZEN and _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)


# ── Flask server thread ────────────────────────────────────────────────────────
_PORT = 5001
_HOST = '127.0.0.1'
_URL  = f'http://{_HOST}:{_PORT}'


def _run_server():
    from app import app as flask_app
    flask_app.run(
        host=_HOST,
        port=_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def _wait_for_server(timeout: float = 20.0) -> bool:
    """Poll localhost until Flask answers or timeout expires."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(_URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import webview

    # Start Flask in a daemon thread so it dies when the window closes
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Wait until the server is accepting connections
    if not _wait_for_server():
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "WebGap failed to start the internal server.\n"
            "Make sure no other application is using port 5001.",
            "WebGap: Startup Error",
            0x10,  # MB_ICONERROR
        )
        sys.exit(1)

    # Create the native window
    window = webview.create_window(
        title='WebGap',
        url=_URL,
        width=1280,
        height=920,
        min_size=(1024, 720),
        background_color='#000000',
        text_select=True,
        confirm_close=False,
    )

    webview.start(debug=False, private_mode=False)
