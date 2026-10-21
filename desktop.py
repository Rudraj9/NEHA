"""
desktop.py
----------
Desktop GUI launcher for NEHA: Personal AI Assistant.
Milestone 4: Native Desktop Window powered by pywebview (EdgeChromium/WebView2)
with HTML, CSS, and JavaScript interface.

Usage:
    python desktop.py             # Launches native desktop window via pywebview
    python desktop.py --browser   # Fallback: opens interface in local browser
"""

import os
import sys
import argparse
import webbrowser
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading

from dotenv import load_dotenv

# 1. Load environment variables
load_dotenv()

from assistant.brain import validate_credentials
from desktop_app.bridge import DesktopBridge


def get_ui_dir() -> Path:
    """Returns the absolute path to the bundled UI assets directory."""
    return Path(__file__).parent.resolve() / "ui"


def launch_browser_fallback(port: int = 8765) -> None:
    """
    Fallback server when pywebview native desktop wrapper is unavailable or bypassed.
    Serves static UI files over local HTTP and opens default system web browser.
    """
    ui_dir = get_ui_dir()
    os.chdir(str(ui_dir))

    handler = SimpleHTTPRequestHandler
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/index.html"

    print(f"\n[NEHA Desktop Fallback]: Local server started at {url}")
    print("  Opening system browser...")
    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[NEHA]: Local server stopped.")
    finally:
        server.server_close()


def launch_native_window() -> None:
    """
    Primary desktop launcher using pywebview and EdgeChromium (WebView2).
    """
    try:
        import webview
    except ImportError:
        print("[Blocker]: pywebview package is not installed in the active environment.")
        print("  Installing pywebview: .\\.venv\\Scripts\\python.exe -m pip install pywebview")
        print("  Falling back to browser mode...")
        launch_browser_fallback()
        return

    ui_dir = get_ui_dir()
    index_file = ui_dir / "index.html"
    if not index_file.exists():
        print(f"[Error]: UI entry file not found at {index_file}")
        sys.exit(1)

    # 1. Instantiate the Desktop Bridge
    bridge = DesktopBridge()

    # 2. Configure PyWebView Window
    url = index_file.resolve().as_uri()

    window = webview.create_window(
        title="NEHA — Your Personal AI Companion",
        url=url,
        js_api=bridge,
        width=1280,
        height=800,
        min_size=(800, 600),
        background_color="#050811",
        text_select=True,
    )

    bridge.set_window(window)

    def on_closed():
        bridge.shutdown()

    window.events.closed += on_closed

    # 3. Start PyWebView Application Loop
    print("\n[NEHA Desktop]: Launching native desktop window (WebView2)...")
    try:
        # gui='edgechromium' / default WinForms backend on Windows
        webview.start(debug=False)
    except Exception as err:
        print(f"[Notice]: pywebview window could not open ({err}).")
        print("  Launching local browser fallback...")
        launch_browser_fallback()


def main():
    parser = argparse.ArgumentParser(description="NEHA Personal AI Companion Desktop Launcher")
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Run UI through a local server and open in default system browser",
    )
    args = parser.parse_args()

    # Credential Warning Check
    is_valid, cred_msg = validate_credentials()
    if not is_valid:
        print("=" * 65)
        print("[Notice - Setup Required]:")
        print(cred_msg)
        print("=" * 65)

    if args.browser:
        launch_browser_fallback()
    else:
        launch_native_window()


if __name__ == "__main__":
    main()
