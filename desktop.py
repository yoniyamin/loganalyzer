import webview
import threading
import uvicorn
import sys
import os
import base64
import time
import logging
import urllib.request
import subprocess
import platform
from backend.main import app

# Configure logging to avoid clutter in the console
logging.getLogger("uvicorn").setLevel(logging.WARNING)

PORT = 8000
HOST = "127.0.0.1"

class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def pick_file(self):
        """Open a native file dialog and return the path."""
        file_types = ('Log Files (*.log;*.txt)', 'All files (*.*)')
        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN, 
            allow_multiple=False, 
            file_types=file_types
        )
        if result:
            return result[0]
        return None

    def save_file(self, suggested_name, content):
        """Open a native save file dialog and save the content."""
        file_types = ('Markdown Files (*.md)', 'Text Files (*.txt)', 'All files (*.*)')
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=suggested_name,
            file_types=file_types
        )
        if result:
            save_path = result if isinstance(result, str) else result[0]
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True
            except Exception as e:
                print(f"Error saving file: {e}")
                return False
        return False

    def save_binary_file(self, suggested_name, content_b64):
        """Open a native save dialog and write binary content (base64 from JS)."""
        file_types = ('Word Documents (*.docx)', 'All files (*.*)')
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=suggested_name,
            file_types=file_types
        )
        if result:
            save_path = result if isinstance(result, str) else result[0]
            try:
                raw = base64.b64decode(content_b64)
                with open(save_path, 'wb') as f:
                    f.write(raw)
                return True
            except Exception as e:
                print(f"Error saving binary file: {e}")
                return False
        return False

    def open_log_folder(self, file_path):
        """Open the folder containing the log in the system file manager (desktop app only)."""
        if not file_path or not isinstance(file_path, str):
            return False
        raw = file_path.strip().strip('"').strip("'")
        path = os.path.normpath(raw)
        if not path or not os.path.exists(path):
            return False

        try:
            system = platform.system()
            if system == "Windows":
                if os.path.isfile(path):
                    subprocess.Popen(["explorer", "/select,", path])
                else:
                    subprocess.Popen(["explorer", path])
            elif system == "Darwin":
                if os.path.isfile(path):
                    subprocess.Popen(["open", "-R", path])
                else:
                    subprocess.Popen(["open", path])
            else:
                folder = os.path.dirname(path) if os.path.isfile(path) else path
                subprocess.Popen(["xdg-open", folder])
            return True
        except Exception as e:
            print(f"open_log_folder: {e}")
            return False

def start_server():
    """Run uvicorn server."""
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")

def wait_for_server(timeout=15):
    """Block until the FastAPI server is accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f'http://{HOST}:{PORT}/api/files').read()
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main():
    api = Api()

    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    wait_for_server()

    window = webview.create_window(
        'Replicate Log Analyzer',
        f'http://{HOST}:{PORT}',
        width=1200,
        height=800,
        js_api=api,
        maximized=True,
        text_select=True,
        background_color='#0f172a'
    )
    api.set_window(window)

    webview.start()

if __name__ == '__main__':
    main()

