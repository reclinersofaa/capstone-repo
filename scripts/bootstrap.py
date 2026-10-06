#!/usr/bin/env python3
"""
Self-check + self-boot for the capstone project. Designed so ANY agent or person —
with zero prior context on this repo — can run one command and get an honest report
of what works, then optionally launch the demo server.

    python scripts/bootstrap.py            # check only, print a status report
    python scripts/bootstrap.py --serve    # check, then launch the server if healthy
    python scripts/bootstrap.py --open     # also open a browser tab

Deliberately dependency-light: only stdlib + whatever's already importable, so it can
run BEFORE you know whether requirements are installed, and tells you what's missing
instead of crashing on an ImportError.
"""
import importlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = "OK", "WARN", "FAIL"
_results = []


def check(label, fn):
    try:
        status, detail = fn()
    except Exception as e:
        status, detail = FAIL, f"{type(e).__name__}: {e}"
    _results.append((label, status, detail))
    tag = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
    print(f"{tag} {label:<32} {detail}")
    return status


# ---------------------------------------------------------------------------
def check_python():
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return (OK if ok else WARN), f"{sys.executable}  (Python {v.major}.{v.minor}.{v.micro})"


def check_core_deps():
    missing = [m for m in ("pandas", "numpy") if importlib.util.find_spec(m) is None]
    if missing:
        return FAIL, f"missing: {', '.join(missing)} — run: pip install -r requirements.txt"
    return OK, "pandas, numpy importable"


def check_web_deps():
    missing = [m for m in ("fastapi", "uvicorn") if importlib.util.find_spec(m) is None]
    if missing:
        return FAIL, f"missing: {', '.join(missing)} — run: pip install -r server/requirements.txt"
    return OK, "fastapi, uvicorn importable"


def check_notebook_deps():
    missing = [m for m in ("nbconvert", "nbformat", "ipykernel") if importlib.util.find_spec(m) is None]
    if missing:
        return WARN, f"missing (only needed to re-run the notebook): {', '.join(missing)}"
    return OK, "nbconvert/nbformat/ipykernel importable"


def check_corpus():
    p = ROOT / "data" / "processed" / "master_emails_v2.csv"
    if not p.exists():
        return FAIL, f"missing: {p.relative_to(ROOT)}"
    # Must use a real CSV parse, not a line count: email bodies contain raw newlines,
    # so `wc -l`-style counting overstates rows by roughly 1.5x on this file.
    import csv
    with open(p, encoding="utf-8", newline="") as f:
        n = sum(1 for _ in csv.reader(f)) - 1
    if n < 1500:
        return WARN, f"{n} rows found, expected ~1,595 — see requirements.txt note on silent source drops"
    return OK, f"{n:,} emails"


def check_simulation_results():
    p = ROOT / "data" / "simulation_results_v2.csv"
    if not p.exists():
        return WARN, "missing — notebook 06 needs to be (re-)run to produce it"
    return OK, f"{p.stat().st_size / 1e6:.1f} MB"


def check_gemma_cache():
    p = ROOT / "data" / "cue_cache_v2" / "gemma4-12b"
    if not p.exists():
        return FAIL, f"missing: {p.relative_to(ROOT)}"
    n = len(list(p.glob("cue_*.json")))
    return (OK if n >= 1500 else WARN), f"{n:,} cached cue files"


def check_ollama():
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        if any("gemma4" in m for m in models):
            return OK, "reachable, gemma4 present — LOCAL extraction available"
        return WARN, f"reachable but gemma4 not pulled (have: {', '.join(models[:3])}...)"
    except Exception:
        return WARN, "not reachable — will use HOSTED extraction instead (this is fine, no GPU needed)"


def check_hosted_keys():
    try:
        from src import llm_providers as lp
        chain = [p["name"] for p in lp.available()]
    except Exception as e:
        return FAIL, f"could not import src.llm_providers: {e}"
    if not chain:
        return FAIL, "no usable key in .env — add GROQ_API_KEY or CEREBRAS_API_KEY (see .env.example / README)"
    return OK, f"fallback chain: {' -> '.join(chain)}"


def check_swapper_end_to_end():
    """The one check that actually matters on a no-GPU machine: does extraction WORK,
    not just 'is a key present'. Makes one tiny real call."""
    try:
        from server.scorer import extract_cues
        out = extract_cues("Test subject", "test@example.com", "This is a short test body.")
        return OK, f"live extraction OK via {out['mode']} · {out['engine']}"
    except Exception as e:
        return FAIL, f"extraction failed end-to-end: {e}"


def check_showcase():
    p = ROOT / "showcase" / "index.html"
    return (OK if p.exists() else FAIL), str(p.relative_to(ROOT))


def check_server_files():
    needed = ["server/app.py", "server/scorer.py", "showcase/quiz.html", "showcase/quiz_items.json"]
    missing = [f for f in needed if not (ROOT / f).exists()]
    if missing:
        return FAIL, f"missing: {', '.join(missing)}"
    return OK, "app.py, scorer.py, quiz.html, quiz_items.json present"


def check_git_state():
    try:
        out = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT,
                              capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True, text=True, timeout=5).stdout.strip()
        n_dirty = len(dirty.splitlines()) if dirty else 0
        return OK, f"branch '{out}', {n_dirty} uncommitted change(s)"
    except Exception as e:
        return WARN, f"git not available: {e}"


CHECKS = [
    ("Python interpreter", check_python),
    ("Core deps (pandas/numpy)", check_core_deps),
    ("Web deps (fastapi/uvicorn)", check_web_deps),
    ("Notebook deps", check_notebook_deps),
    ("Corpus (master_emails_v2.csv)", check_corpus),
    ("Simulation results", check_simulation_results),
    ("Gemma cue cache (committed)", check_gemma_cache),
    ("Server files", check_server_files),
    ("Showcase page", check_showcase),
    ("Ollama (local GPU path)", check_ollama),
    ("Hosted keys (.env)", check_hosted_keys),
    ("Swapper end-to-end (real call)", check_swapper_end_to_end),
    ("Git state", check_git_state),
]


def main():
    print(f"Bootstrap check — {ROOT}\n" + "-" * 64)
    for label, fn in CHECKS:
        check(label, fn)
    print("-" * 64)

    fails = [r for r in _results if r[1] == FAIL]
    warns = [r for r in _results if r[1] == WARN]
    if fails:
        print(f"\n{len(fails)} FAILING check(s) — fix these before demoing:")
        for label, _, detail in fails:
            print(f"  - {label}: {detail}")
    if warns:
        print(f"\n{len(warns)} warning(s) (non-blocking):")
        for label, _, detail in warns:
            print(f"  - {label}: {detail}")
    if not fails:
        print("\nAll critical checks passed. The project can be demoed as-is.")

    if "--serve" in sys.argv or "--open" in sys.argv:
        if fails:
            print("\nRefusing to launch the server: fix the FAIL items above first.")
            sys.exit(1)
        print("\nLaunching server at http://localhost:8000 ...")
        if "--open" in sys.argv:
            def _open():
                time.sleep(1.5)
                webbrowser.open("http://localhost:8000")
            import threading
            threading.Thread(target=_open, daemon=True).start()
        os.chdir(ROOT)
        subprocess.run([sys.executable, "-m", "uvicorn", "server.app:app", "--port", "8000"])
    else:
        print("\nRun with --serve to launch the server, or --open to also open a browser tab.")

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
