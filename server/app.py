"""
FastAPI wrapper for the live phishing scorer.

Run from the repo root:
    pip install -r server/requirements.txt
    uvicorn server.app:app --reload --port 8000
Then open http://localhost:8000

The browser only ever talks to this server; API keys stay in .env, server-side.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.scorer import extract_cues, score_email, extractor_status

HERE = Path(__file__).resolve().parent
app = FastAPI(title="Phishing Susceptibility — Live Scorer", version="1.0")


class EmailIn(BaseModel):
    subject: str = ""
    sender: str = ""
    body: str = ""
    n_agents: int = 30


@app.get("/api/health")
def health():
    """Which extractor the swapper will use right now (local GPU vs hosted vs none)."""
    return extractor_status()


@app.post("/api/score")
def score(inp: EmailIn):
    if not (inp.subject.strip() or inp.body.strip()):
        return JSONResponse(status_code=400, content={"error": "Provide at least a subject or a body."})
    try:
        ext = extract_cues(inp.subject, inp.sender, inp.body)   # <- the swapper
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    result = score_email(ext["cues"], n_agents=max(5, min(int(inp.n_agents), 100)))
    result["engine"] = ext["engine"]
    result["mode"] = ext["mode"]
    return result


app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(str(HERE / "static" / "index.html"))


@app.get("/showcase")
def showcase():
    """Serve the static results showcase from the same server, for convenience."""
    return FileResponse(str(HERE.parent / "showcase" / "index.html"))


@app.get("/report")
def report():
    """Full-notebook report: every section of notebook 06, rendered from its saved outputs."""
    return FileResponse(str(HERE.parent / "showcase" / "report.html"))


app.mount("/report_assets", StaticFiles(directory=str(HERE.parent / "showcase" / "report_assets")),
          name="report_assets")
