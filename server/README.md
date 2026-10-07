# Capstone web server

Serves the showcase pages and the phishing quiz.

```
uvicorn server.app:app --port 8000
```

Then open http://localhost:8000 (redirects to the results summary).

| Route | What it is |
|---|---|
| `/showcase/` | results summary |
| `/showcase/report.html` | full report (notebook 06 output) |
| `/showcase/quiz.html` | human phishing quiz (intro essay, consent, per-item timing) |
| `POST /api/quiz/response` | appends one quiz answer to `data/human_quiz/responses.jsonl` |

The showcase is mounted as static files so the pages' relative links work the same
under the server as they do when opened directly.

`scorer.py` holds the extraction swapper (local Ollama, then hosted keys). It is not
served; `scripts/bootstrap.py` uses it for the end-to-end extraction check.
