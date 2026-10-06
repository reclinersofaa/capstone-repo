"""Build showcase/evidence_items.json: every phishing email in the corpus with the cue list the
extractor assigned (the same cues the simulation used). Run from the repo root."""
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cue_cache_v2" / "gemma4-12b"
OUT = ROOT / "showcase" / "evidence_items.json"


def cues_for(subject, body):
    blob = re.sub(r"\s+", " ", f"{subject}\n{body}".lower()).strip()
    p = CACHE / f"cue_{hashlib.md5(blob.encode('utf-8', 'ignore')).hexdigest()}.json"
    if not p.exists():
        raise SystemExit(f"missing cue cache entry for: {subject[:60]}")
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    m = pd.read_csv(ROOT / "data" / "processed" / "master_emails_v2.csv")
    items = []
    for r in m[m.actual_class == 1].itertuples():
        items.append({"email_id": int(r.email_id), "source": str(r.source), "sender": str(r.sender),
                      "subject": str(r.subject), "body": str(r.body), "is_phishing": 1,
                      "cues": cues_for(str(r.subject), str(r.body))})
    OUT.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(items)} phishing items to {OUT}")


if __name__ == "__main__":
    main()
