"""
Core of the live email scorer — no web framework, so it can be unit-tested and
smoke-run on its own (`python server/scorer.py`).

Two independent jobs:
  1. extract_cues(...)  — the GPU/hosted SWAPPER. Local Ollama (gemma4:12b) if the
                          machine has it; otherwise the hosted fallback chain
                          (Groq -> Cerebras -> ...) via src/llm_providers, keys read
                          from .env server-side. Never returns silently-empty on a
                          hosted failure — it raises, same policy as the batch pipeline.
  2. score_email(cues)  — runs the UNCHANGED v2 decision loop (build_correlated_agents
                          + simulate_email) over the workday hours and aggregates click
                          rate per hour. This is pure Python/numpy: no GPU, no keys.

The split matters: scoring the current results needs no model at all (see the
showcase). Only turning a brand-new pasted email into a cue list needs the swapper.
"""

import os
import re
import sys
import json
import random
from pathlib import Path

# Make `src` importable whether run as `python server/scorer.py` or `uvicorn server.app:app`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Stdlib-only import (safe even without numpy / groq installed) — gives us the exact
# 9-cue taxonomy and the single-email prompt the published extractor used.
from src.ollama_extractor import OllamaExtractor, VALID_CUES, _PROMPT  # noqa: E402

OLLAMA_MODEL = os.getenv("SCORER_OLLAMA_MODEL", "gemma4:12b")
LIVE_CACHE = str(ROOT / "data" / "cue_cache_live")   # kept separate from the published cache
HOURS = [8.0, 10.0, 12.0, 14.0, 16.0]
HOUR_LABELS = {8: "8am", 10: "10am", 12: "12pm", 14: "2pm", 16: "4pm"}
_URL_RE = re.compile(r"https?://\S+", re.I)

_AGENTS = None  # built once, reused across requests (deterministic, seed=42)


# ---------------------------------------------------------------------------
# The swapper
# ---------------------------------------------------------------------------
def _local_extractor() -> OllamaExtractor:
    return OllamaExtractor(model=OLLAMA_MODEL, cache_dir=LIVE_CACHE)


def _hosted_chain() -> list:
    """Provider names with a real (non-placeholder) key, in fallback order. [] if none."""
    try:
        from src import llm_providers
        return [p["name"] for p in llm_providers.available()]
    except Exception:
        return []


def extractor_status() -> dict:
    """Which path the swapper will take right now — used by the /api/health badge."""
    try:
        if _local_extractor().is_available():
            return {"mode": "local", "engine": OLLAMA_MODEL,
                    "detail": f"local GPU · Ollama · {OLLAMA_MODEL}"}
    except Exception:
        pass
    chain = _hosted_chain()
    if chain:
        return {"mode": "hosted", "engine": chain[0], "chain": chain,
                "detail": "hosted · " + " → ".join(chain)}
    return {"mode": "none", "engine": None,
            "detail": "no local model reachable and no API key configured (.env)"}


def _parse_cue_array(text: str) -> list:
    s, e = text.find("["), text.rfind("]") + 1
    if s == -1 or e <= 0:
        return []
    frag = text[s:e]
    try:
        parsed = json.loads(frag)
        if isinstance(parsed, list):
            return [c for c in parsed if c in VALID_CUES]
    except Exception:
        pass
    return [c for c in re.findall(r'"([^"]+)"', frag) if c in VALID_CUES]


def _hosted_extract(subject, sender, body, urls):
    from src import llm_providers
    prompt = _PROMPT.format(
        subject=subject or "(none)", sender=sender or "(none)",
        body=(body or "")[:2000], urls=", ".join(urls) or "none",
    )
    text, provider = llm_providers.complete(prompt, max_tokens=120, temperature=0.1, verbose=False)
    return _parse_cue_array(text), provider


def extract_cues(subject: str, sender: str, body: str) -> dict:
    """
    Swapper entry point. Returns {cues, engine, mode}. Raises RuntimeError only if
    NEITHER a local model nor a hosted key is usable.
    """
    urls = _URL_RE.findall(f"{subject}\n{body}")
    # 1) local GPU first (reproducible, free, no keys)
    try:
        ext = _local_extractor()
        if ext.is_available():
            cues = ext.extract(0, subject or "", sender or "", body or "", urls)
            return {"cues": cues, "engine": OLLAMA_MODEL, "mode": "local"}
    except Exception:
        pass  # fall through to hosted
    # 2) hosted swap (Groq -> Cerebras -> ...); keys live in .env, server-side only
    if _hosted_chain():
        cues, provider = _hosted_extract(subject, sender, body, urls)
        return {"cues": cues, "engine": provider, "mode": "hosted"}
    raise RuntimeError(
        "No extractor available: local Ollama is not reachable and no hosted key is set. "
        "Start Ollama (`ollama pull gemma4:12b`) or add a GROQ_API_KEY / CEREBRAS_API_KEY to .env."
    )


# ---------------------------------------------------------------------------
# The scorer (no model — pure v2 simulation)
# ---------------------------------------------------------------------------
def _get_agents(n=30, seed=42):
    global _AGENTS
    if _AGENTS is None or len(_AGENTS) != n:
        from src.agent_v2 import build_correlated_agents
        _AGENTS = build_correlated_agents(n, seed=seed)
    return _AGENTS


def score_email(cues, n_agents=30, seed=42, hours=None) -> dict:
    """
    Run `cues` through `n_agents` copula-correlated agents at each workday hour,
    mirroring run_simulation_v2's loop exactly (reset -> advance -> seeded loop rng).
    Returns per-hour click rate + overall + the 8am→4pm delta.
    """
    from src.decision_loop import simulate_email
    hours = hours or HOURS
    agents = _get_agents(n_agents, seed)
    master = random.Random(seed)
    tally = {h: {"clicked": 0, "reported": 0} for h in hours}
    pclick = {h: [] for h in hours}

    for agent in agents:
        agent.reset_workday()
        for h in hours:
            agent.advance_workday(h)
            loop_rng = random.Random(master.randint(0, 1_000_000))
            pclick[h].append(agent.compute_p_click())
            res = simulate_email(agent, list(cues), rng=loop_rng)
            tally[h][res["decision"]] += 1

    rows, total_click, total = [], 0, 0
    for h in hours:
        c, r = tally[h]["clicked"], tally[h]["reported"]
        n = c + r
        rows.append({
            "hour": h, "label": HOUR_LABELS.get(int(h), str(h)),
            "click_rate": round(100.0 * c / n, 1) if n else 0.0,
            "clicked": c, "reported": r,
            "mean_p_click": round(100.0 * sum(pclick[h]) / len(pclick[h]), 1) if pclick[h] else 0.0,
        })
        total_click += c
        total += n

    return {
        "n_agents": n_agents, "n_cues": len(cues), "cues": list(cues),
        "overall_click_rate": round(100.0 * total_click / total, 1) if total else 0.0,
        "per_hour": rows,
        "workday_delta": round(rows[-1]["click_rate"] - rows[0]["click_rate"], 1),
    }


if __name__ == "__main__":
    print("Extractor status:", json.dumps(extractor_status(), indent=2))
    for demo in (["urgency", "suspicious_link"], [], ["urgency", "threats", "generic_greeting", "spelling_grammar", "suspicious_link"]):
        out = score_email(demo)
        print(f"\ncues={demo!r}  ->  overall={out['overall_click_rate']}%  "
              f"8am={out['per_hour'][0]['click_rate']}%  4pm={out['per_hour'][-1]['click_rate']}%  "
              f"delta={out['workday_delta']:+}")
