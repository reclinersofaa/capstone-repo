# Orientation for any agent (or human) opening this repo cold

Read this first. It tells you what this project is, whether it currently works, and
how to prove that in under a minute — before touching any other file.

## What this is

An agent-based simulation of phishing susceptibility (PES University capstone
PW26_SVM_01). Synthetic employees with cognitive traits (fatigue, motivation,
vigilance) "read" a 1,595-email corpus and click or report each one. Headline finding:
persuasion-guided AI phishing reaches parity with the best human-authored spear-phishing
in evading detection, without requiring an attacker's own expertise — not superiority
over all real phishing (an earlier version of this claim overstated that; see
`notebooks/07_vtriad_validity_fix.ipynb`). Full narrative: [`README.md`](README.md). Deep
technical reference: [`SYSTEM.md`](SYSTEM.md).

## Step 1 — always run this first

```bash
python scripts/bootstrap.py
```

Framework-free, stdlib-only, safe to run with nothing installed — it tells you what's
missing rather than crashing. It checks: Python + deps, the corpus, the committed cue
cache, the notebook, the server files, whether local Ollama is reachable, whether a
hosted API key in `.env` works, and — critically — makes ONE REAL test call through the
extraction swapper so "a key is present" and "extraction actually works" are never
conflated. Add `--serve` to launch the demo server once checks pass, `--open` to also
open a browser tab.

Do not assume the project works from reading code. Run the check.

## Two independent things live here — know which one you're touching

| | Needs a model? | What it is |
|---|---|---|
| **The simulation** (`src/agent_v2.py`, `notebooks/06_agent_simulation_v2.ipynb`) | No — reads the committed cue cache | The actual research: 239,250 decisions, all the headline numbers |
| **Live extraction** (`server/scorer.py: extract_cues()`) | Yes, but auto-swaps | The ONLY part of the whole project that calls a model live |

The swapper (`extract_cues` in `server/scorer.py`) tries local Ollama (`gemma4:12b`)
first; if unavailable, it falls to the hosted chain in `src/llm_providers.py`
(Groq → Cerebras, keys from `.env`, server-side only, never sent to the browser). If
you're on a machine with no GPU, this is expected and fine — the hosted path is real,
not a stub. If BOTH fail, bootstrap.py will show it as a FAIL, not a silent empty
result — extraction never returns `[]` on failure (see the truncation-bug note below).

## Known traps — read before you "fix" something that isn't broken

- **`python` in a bare shell may not be your `.venv`.** This has caused real
  divergence (a 1,595 vs 1,395-email corpus from the same code). If deps seem
  missing, check `python -c "import sys; print(sys.executable)"` before reinstalling
  anything. On this machine the real interpreter is `.venv/Scripts/python.exe`.
- **Free-tier hosted models get deprecated without notice.** `src/llm_providers.py`'s
  Groq model has already had to change once (`llama-4-scout-17b` was retired from the
  API entirely). If the hosted path fails, run `python -m src.llm_providers` to see
  live provider status, and check `/v1/models` on the failing provider before assuming
  the code is wrong.
- **A reasoning model silently eating its own output looks identical to "no cues
  found."** Several free models (`gpt-oss`, `zai-glm`, `qwen3.6`) wrap output in a
  `<think>` block and return nothing else within a small token budget. Any extractor
  change must be tested with a real call and an inspected raw response, not just "no
  exception was raised."
- **A truncated JSON array must never silently become `[]`.** `num_predict`/
  `max_tokens` too small + a parser that gives up on a missing `]` = an obviously
  cue-rich phishing email silently scores as "no cues," inverting the whole result.
  Already happened once and was fixed in `src/ollama_extractor.py` — if you touch
  extraction, re-verify with a deliberately cue-rich test email, not just a normal one.
- **The cue cache is scoped per extraction model** (`data/cue_cache_v2/<model>/`,
  content-hash keyed, not positional). Never point a run at the bare `cue_cache_v2/`
  root or mix caches from different models — cue counts are only comparable within one
  extractor.

## Where things are

```
src/                  the model: agent_v2.py, decision_loop.py, dataset_v2.py,
                       groq_client.py, ollama_extractor.py, llm_providers.py
notebooks/06_*.ipynb  THE analysis — run top-to-bottom, no model needed (cached)
showcase/index.html   static results page — no model, no keys, host it anywhere
server/               live scorer web app — the ONLY model-dependent frontend piece
scripts/bootstrap.py  run this first, always
data/cue_cache_v2/gemma4-12b/   the committed, published cue cache (1,595 files)
README.md, SYSTEM.md, ARCHITECTURE.md, DATA_PROVENANCE.md   docs, in that order of depth
```

## If you're about to demo this

Run `python scripts/bootstrap.py` on the actual demo machine, in advance, not for the
first time in front of an audience. If it reports any FAIL, the showcase
(`showcase/index.html`) still works with zero dependencies — it's pre-baked, static,
and cannot fail live. Treat it as the fallback of last resort.
