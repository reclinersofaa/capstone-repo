# Live phishing scorer

Paste an email → extract its 9 detectable cues → run it through 30 correlated agents
across the workday → get a simulated click rate. A live, interactive companion to the
static [`showcase/`](../showcase/index.html).

## The GPU / hosted swapper

Cue extraction (the only model-dependent step) auto-detects where to run:

1. **Local GPU** — if Ollama is reachable with the model, extraction runs on
   `gemma4:12b` locally. Reproducible, free, no keys. *(This is the published path.)*
2. **Hosted fallback** — otherwise it uses the `src/llm_providers` chain
   (Groq → Cerebras → …) with keys read from `.env`, **server-side only**. Keys are
   never sent to the browser.
3. **Neither** — the API returns a clear 503 telling you to start Ollama or add a key.

The health badge in the UI shows which path is active. Scoring itself (the agent
simulation) uses no model — it is deterministic Python/numpy.

Override the local model with `SCORER_OLLAMA_MODEL` (default `gemma4:12b`).

## Run it

From the **repo root**, in your project `.venv`:

```bash
pip install -r server/requirements.txt
uvicorn server.app:app --reload --port 8000
```

Then open <http://localhost:8000>.

To show it on another device on the same network, bind all interfaces:

```bash
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

## Endpoints

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | the scorer UI |
| `/api/health` | GET | which extractor the swapper will use right now |
| `/api/score` | POST | `{subject, sender, body}` → cues + per-hour click rate |

## Files

```
server/
  scorer.py        core: extract_cues() swapper + score_email() simulation (framework-free, unit-testable)
  app.py           FastAPI wrapper + static hosting
  static/index.html  the UI
  requirements.txt web-layer deps (fastapi, uvicorn)
```

`python server/scorer.py` runs a no-web smoke test of the scoring core.

## Note on the numbers

The score is a **relative, within-model** susceptibility measure, not a field click
rate. Fewer detectable cues → higher click rate by construction, and a zero-cue email
can never be reported. Compare emails against each other, not against the real world.
