"""Build showcase/quiz_items.json: 10 corpus emails (5 phishing, 5 legitimate) for the
human phishing quiz. Deterministic (fixed seed). Each item carries the cue list the
extractor assigned, so the post-answer reveal matches what the simulation saw.

Run from the repo root:  .venv/Scripts/python.exe scripts/build_quiz_items.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE = ROOT / "data" / "cue_cache_v2" / "gemma4-12b"
OUT = ROOT / "showcase" / "quiz_items.json"
SEED = 2026


def cues_for(subject, body):
    blob = re.sub(r"\s+", " ", f"{subject}\n{body}".lower()).strip()
    p = CACHE / f"cue_{hashlib.md5(blob.encode('utf-8', 'ignore')).hexdigest()}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def main():
    m = pd.read_csv(ROOT / "data" / "processed" / "master_emails_v2.csv")
    phish_sources = ["hybrid_vtriad", "ceas08", "nazario", "plain_llm", "multi_llm"]

    # One item per phishing source (hybrid_vtriad included, it is the headline condition),
    # and five distinct legitimate emails drawn across the three benign sources.
    picks = []
    for i, src in enumerate(phish_sources[:5]):
        pool = m[(m.source == src) & (m.actual_class == 1)]
        picks.append(pool.sample(n=1, random_state=SEED + i).iloc[0])
    benign_plan = [("spamassassin_ham", 2), ("trec07_ham", 2), ("enron_clean", 1)]
    for j, (src, k) in enumerate(benign_plan):
        pool = m[(m.source == src) & (m.actual_class == 0)]
        for t in range(k):
            picks.append(pool.sample(n=1, random_state=SEED + 50 + j * 10 + t).iloc[0])

    items = []
    for r in picks:
        cues = cues_for(str(r.subject), str(r.body))
        # [] is a real result (a clean legitimate email); None means the cache entry is missing.
        assert cues is not None, f"no cached cue list for email_id {r.email_id}; run extraction first"
        if int(r.actual_class) == 1:
            hosts = re.findall(r"https?://([^/\s]+)", str(r.body))
            assert all(h == "example.com" or h.endswith(".example.com") for h in hosts), f"non-example.com link in phishing email_id {r.email_id}"
        items.append({
            "email_id": int(r.email_id),
            "sender": str(r.sender),
            "subject": str(r.subject),
            "body": str(r.body),
            "is_phishing": int(r.actual_class),
            "source": str(r.source),
            "model_cues": cues,
        })
    # Order is shuffled per participant in the browser; the file keeps a stable order.
    ordered = items
    OUT.write_text(json.dumps(ordered, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} with {len(ordered)} items")


if __name__ == "__main__":
    main()
