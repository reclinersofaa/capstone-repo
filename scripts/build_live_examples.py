"""Rebuild showcase/live_examples.json: preloaded, precomputed examples for the
live-scorer demo page, drawn from the CURRENT (post-fix) corpus and the committed
cue cache, cache-first so this never makes a network or GPU call.

Mirrors the old server/static/examples.json (3 categories x 5 real emails), but the
old file was generated before the V-Triad labeling-defect fix and the .test ->
example.com link fix, so its bodies are stale. This rebuilds the same shape from
data/processed/master_emails_v2.csv + the committed cue cache instead of reusing it.
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EMAILS = ROOT / "data" / "processed" / "master_emails_v2.csv"
CACHE_DIR = ROOT / "data" / "cue_cache_v2" / "gemma4-12b"
OUT = ROOT / "showcase" / "live_examples.json"
N_PER_CATEGORY = 5

CATEGORIES = [
    ("vtriad", "V-Triad style", "hybrid_vtriad"),
    ("naive", "naive phish", "plain_llm"),
    ("benign", "benign", None),  # benign: mix of benign sources
]
BENIGN_SOURCES = ["spamassassin_ham", "enron_clean", "trec07_ham"]


def main():
    if not EMAILS.exists():
        sys.exit(f"missing {EMAILS}")
    sys.path.insert(0, str(ROOT))
    from src.ollama_extractor import OllamaExtractor
    sys.path.insert(0, str(ROOT / "server"))
    from scorer import score_email  # same scoring path /api/score uses

    df = pd.read_csv(EMAILS)
    ext = OllamaExtractor(model="gemma4:12b", cache_dir=str(CACHE_DIR))

    out = {}
    for key, label, source in CATEGORIES:
        if source:
            rows = df[df["source"] == source].sort_values("email_id").head(N_PER_CATEGORY)
        else:
            rows = (df[df["source"].isin(BENIGN_SOURCES)]
                    .sort_values(["source", "email_id"])
                    .groupby("source").head(2).sort_values("email_id").head(N_PER_CATEGORY))
        if rows.empty:
            sys.exit(f"no rows for category {key} (source={source})")

        cues_by_id = ext.extract_batch(rows)  # cache-first; the committed cache covers the whole corpus
        examples = []
        for _, r in rows.iterrows():
            cues = cues_by_id.get(r["email_id"], [])
            scored = score_email(cues, n_agents=30)
            examples.append({
                "source": r["source"],
                "sender": r["sender"],
                "subject": r["subject"],
                "body": r["body"],
                "cues": cues,
                "n_cues": len(cues),
                "engine": "gemma4:12b",
                "mode": "cached",
                "overall_click_rate": scored["overall_click_rate"],
                "per_hour": scored["per_hour"],
                "workday_delta": scored["workday_delta"],
            })
        out[key] = {"label": label, "examples": examples}

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for key, v in out.items():
        print(f"{key:8s} {v['label']:14s} {len(v['examples'])} examples, "
              f"cues: {[len(e['cues']) for e in v['examples']]}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
