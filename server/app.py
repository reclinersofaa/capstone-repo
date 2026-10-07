"""
Capstone web server: the showcase pages, the phishing quiz, and the quiz response log.

Run from the repo root:
    uvicorn server.app:app --port 8000
Then open http://localhost:8000
"""
import json
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.scorer import extract_cues, score_email, extractor_status

HERE = Path(__file__).resolve().parent
SHOWCASE = HERE.parent / "showcase"
RESPONSES = HERE.parent / "data" / "human_quiz" / "responses.jsonl"

app = FastAPI(title="PES Capstone PW26_SVM_01: showcase and quiz", version="2.0")

MAX_BODY = 4096
ANSWERS = {"phishing", "legitimate"}
DEPARTMENTS = {
    "Finance & Accounts Payable", "IT Service Desk", "Human Resources", "Regional Sales",
    "Operations & Logistics (shift)", "Customer Support (contact centre)", "Other / not listed",
    "not_given",
}


def _answer_key() -> dict:
    """email_id -> is_phishing, from the same file the browser loads. Server-side truth."""
    f = SHOWCASE / "quiz_items.json"
    if not f.exists():
        return {}
    return {int(i["email_id"]): int(i["is_phishing"]) for i in json.loads(f.read_text(encoding="utf-8"))}


KEY = _answer_key()


@app.get("/")
def root():
    return RedirectResponse(url="/showcase/")


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


@app.post("/api/quiz/response")
async def quiz_response(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return JSONResponse(status_code=413, content={"error": "Payload too large."})
    try:
        rec = json.loads(raw)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Body must be JSON."})
    if not isinstance(rec, dict):
        return JSONResponse(status_code=400, content={"error": "Body must be an object."})
    try:
        eid = int(rec["email_id"])
        q = int(rec["question"])
        ms = int(rec["response_ms"])
        answer = str(rec["answer"])
        pid = str(rec["participant_id"])[:64]
        dept = str(rec.get("department", "not_given"))[:80]
    except (KeyError, TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "Missing or malformed quiz fields."})
    if eid not in KEY or answer not in ANSWERS or not (0 <= ms <= 3_600_000) or not (1 <= q <= 100):
        return JSONResponse(status_code=400, content={"error": "Unknown item, answer, or timing."})
    if dept not in DEPARTMENTS:
        dept = "not_given"
    is_phishing = KEY[eid]
    correct = int((answer == "phishing") == bool(is_phishing))   # recomputed here, never trusted
    stored = {
        "participant_id": pid, "consent_at": str(rec.get("consent_at", ""))[:40],
        "question": q, "email_id": eid, "is_phishing": is_phishing, "answer": answer,
        "correct": correct, "response_ms": ms, "long_pause": int(ms > 120_000),
        "department": dept, "received_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    RESPONSES.parent.mkdir(parents=True, exist_ok=True)
    with RESPONSES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(stored, ensure_ascii=False) + "\n")
    return {"ok": True}


app.mount("/showcase", StaticFiles(directory=str(SHOWCASE), html=True), name="showcase")
