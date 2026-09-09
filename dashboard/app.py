"""FastAPI application serving the GOLIDE trading control panel."""
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dashboard.state import overview, set_control

STATIC = Path(__file__).with_name("static")
app = FastAPI(title="GOLIDE Trading Control", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}


@app.get("/api/overview")
def api_overview() -> dict: return overview()


@app.post("/api/control/{action}")
def api_control(action: str) -> dict:
    try: return {"ok": True, "control": set_control(action)}
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse: return FileResponse(STATIC / "index.html")

