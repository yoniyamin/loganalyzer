import webview
import threading
import uvicorn
import sys
import os
import logging
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

def start_server():
    """Run uvicorn server."""
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")

def main():
    api = Api()
    
    # Start the server in a separate thread
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # Create the window (maximized on startup)
    window = webview.create_window(
        'Replicate Log Analyzer', 
        f'http://{HOST}:{PORT}',
        width=1200,
        height=800,
        js_api=api,
        maximized=True,
        text_select=True  # Enable text selection and copying
    )
    api.set_window(window)
    
    # Start the GUI
    webview.start(debug=True)

if __name__ == '__main__':
    main()

