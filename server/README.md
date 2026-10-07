# Capstone web server

Serves the showcase pages, the phishing quiz, and the live scorer.

## Quickstart (demo)

```
cd Capstone
.venv\Scripts\python.exe -m uvicorn server.app:app --port 8000
```

(Or plain `python -m uvicorn server.app:app --port 8000` if your shell's `python`
already points at the venv — check with `python -c "import sys; print(sys.executable)"`
first; see CLAUDE.md's "known traps" if unsure.)

Then open **http://localhost:8000** — it redirects to the results summary. Every page
is reachable from there via the same nav bar (no separate servers, one process, one port):

| Route | What it is |
|---|---|
| `/showcase/` (`index.html`) | results summary — the headline findings |
| `/showcase/report.html` | full report (notebook 06 output) |
| `/showcase/quiz.html` | human phishing quiz (intro essay, consent, per-item timing) |
| `/showcase/emails.html` | real phishing emails with cues highlighted, click-rate-through-the-day, per-department breakdown |
| `/showcase/live.html` | live scorer — preloaded instant examples, or paste your own email for a real extraction |
| `POST /api/quiz/response` | appends one quiz answer to `data/human_quiz/responses.jsonl` |
| `GET /api/health` | which extractor is live right now (local Ollama vs hosted vs none) |
| `POST /api/score` | runs a fresh extraction + scoring pass on a pasted email |

If Ollama isn't running on the demo machine, `/api/health` and the "Paste your own"
box on the live scorer will fall back to the hosted chain (`.env` keys) or report
"no extractor available" — the rest of the site (everything except live-pasted
emails) has **no model or network dependency at all**, it's pre-baked static data,
and cannot fail live. If something looks wrong under time pressure, that's the page
to fall back to.

`scorer.py` holds the extraction swapper (local Ollama, then hosted keys), used by
both `/api/score` and `scripts/bootstrap.py`'s end-to-end extraction check.

The showcase is mounted as static files so the pages' relative links work the same
under the server as they do when the files are opened directly.
