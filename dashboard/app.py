"""FastAPI application serving the GOLIDE trading control panel."""
from pathlib import Path
import hmac
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dashboard.state import overview, set_control
from config import Settings

STATIC = Path(__file__).with_name("static")
app = FastAPI(title="GOLIDE Trading Control", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}


@app.get("/api/overview")
def api_overview() -> dict: return overview()


@app.post("/api/control/{action}")
def api_control(action: str, authorization: str = Header(default="")) -> dict:
    token = Settings.from_env().dashboard_token
    supplied = authorization.removeprefix("Bearer ")
    if not token or not hmac.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Control authentication required")
    try: return {"ok": True, "control": set_control(action)}
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse: return FileResponse(STATIC / "index.html")
