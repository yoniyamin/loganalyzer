from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from backend.api.endpoints import router as api_router
from backend.llm.endpoints import router as llm_router
from backend.database import init_db, SessionLocal, UserSettings
from backend.paths import static_dir
import json
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Log Analyzer Backend")

# Initialize DB
logger.info("Initializing database...")
init_db()

# Mount API routers
app.include_router(api_router, prefix="/api")
app.include_router(llm_router, prefix="/api")

# Mount Static
STATIC_DIR = static_dir()
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def _get_ui_theme_from_db() -> str:
    db = SessionLocal()
    try:
        setting = db.query(UserSettings).filter(UserSettings.key == "ui_theme").first()
        if setting and setting.value:
            data = json.loads(setting.value)
            theme = data.get("theme") if isinstance(data, dict) else None
            if theme in ("light", "dark"):
                return theme
    except Exception:
        pass
    finally:
        db.close()
    return "dark"

@app.get("/")
async def read_index():
    logger.info("Serving index.html")
    html_path = os.path.join(STATIC_DIR, "index.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    theme = _get_ui_theme_from_db()
    html = html.replace("__SERVER_UI_THEME__", theme)
    return HTMLResponse(html)

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Log Analyzer server on http://127.0.0.1:8000")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)


