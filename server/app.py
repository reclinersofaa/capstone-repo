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
    except RuntimeError as e:
        # extract_cues() only raises this for the one expected, already-friendly case:
        # neither extractor is configured. Safe to show verbatim.
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        # Anything else (network error, malformed provider response, ...) is an
        # unexpected failure -- log the real cause server-side, never leak a raw
        # exception string onto the live results panel.
        print(f"[api/score] unexpected extractor failure: {e!r}")
        return JSONResponse(status_code=503, content={
            "error": "The extractor hit an unexpected error. Try again, or switch to a "
                     "preloaded example while it's investigated."
        })
    result = score_email(ext["cues"], n_agents=max(5, min(int(inp.n_agents), 100)))
    result["engine"] = ext["engine"]
    result["mode"] = ext["mode"]
    return result


app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(str(HERE / "static" / "index.html"))


@app.get("/report")
def report_alias():
    """Old bookmark-friendly alias -> the report now lives under /showcase/."""
    return FileResponse(str(HERE.parent / "showcase" / "report.html"))


# Mounted (not FileResponse'd) so the showcase pages' own relative links
# (index.html / report.html / mock_landing_page.html / report_assets/...) resolve
# correctly under the server exactly as they do when the file is opened directly or
# hosted elsewhere with no server at all -- see CLAUDE.md's "host it anywhere" note.
# html=True serves index.html for a bare /showcase/ request.
app.mount("/showcase", StaticFiles(directory=str(HERE.parent / "showcase"), html=True), name="showcase")
