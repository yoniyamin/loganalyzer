from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.api.endpoints import router as api_router
from backend.llm.endpoints import router as llm_router
from backend.database import init_db
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
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def read_index():
    logger.info("Serving index.html")
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Log Analyzer server on http://127.0.0.1:8000")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)


