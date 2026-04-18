"""
Standalone Ollama cue extraction script.

Runs OllamaExtractor on master_emails.csv, optionally wiping phishing email
caches first so they get re-extracted with the local LLM instead of regex.

Usage:
  # Re-extract all phishing emails (101-250) with Ollama, keep ham cache intact:
  python extract_cues_ollama.py

  # Re-extract everything (nuke entire cache):
  python extract_cues_ollama.py --nuke-all

  # Dry run — just show what would be deleted, don't call Ollama:
  python extract_cues_ollama.py --dry-run

  # Use a different model:
  python extract_cues_ollama.py --model qwen2.5:7b

  # Point at a different emails CSV (for new dataset after merging agent-sim2):
  python extract_cues_ollama.py --emails data/processed/master_emails.csv
"""

import argparse
import json
import sys
import time
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import pandas as pd
from src.ollama_extractor import OllamaExtractor

DEFAULT_CACHE = ROOT / "data" / "cue_cache"
DEFAULT_EMAILS = ROOT / "data" / "processed" / "master_emails.csv"


def wipe_phishing_caches(emails_df: pd.DataFrame, cache_dir: Path, dry_run: bool = False):
    """Delete cache files for phishing emails (actual_class == 1)."""
    phishing_ids = emails_df[emails_df["actual_class"] == 1]["email_id"].tolist()
    deleted = 0
    for eid in phishing_ids:
        p = cache_dir / f"email_{eid}.json"
        if p.exists():
            if not dry_run:
                p.unlink()
            deleted += 1
    return deleted, len(phishing_ids)


def wipe_all_caches(cache_dir: Path, dry_run: bool = False):
    """Delete all cache files."""
    files = list(cache_dir.glob("email_*.json"))
    if not dry_run:
        for f in files:
            f.unlink()
    return len(files)


def print_summary(email_cues: dict, emails_df: pd.DataFrame):
    """Print per-source cue extraction summary."""
    id_to_source = dict(zip(emails_df["email_id"], emails_df["source"]))
    by_source = defaultdict(list)
    for eid, cues in email_cues.items():
        src = id_to_source.get(eid, "unknown")
        by_source[src].append(len(cues))

    print("\n=== Cue extraction summary (Ollama) ===")
    print(f"{'Source':<20}  {'Count':>5}  {'Mean cues':>9}  {'Min':>3}  {'Max':>3}  {'Empty':>5}")
    print("-" * 55)
    for src in sorted(by_source):
        vals = by_source[src]
        empty = sum(1 for v in vals if v == 0)
        print(f"{src:<20}  {len(vals):>5}  {sum(vals)/len(vals):>9.2f}  "
              f"{min(vals):>3}  {max(vals):>3}  {empty:>5}")


def main():
    parser = argparse.ArgumentParser(description="Run Ollama cue extraction on email dataset")
    parser.add_argument("--emails", default=str(DEFAULT_EMAILS), help="Path to master_emails.csv")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE), help="Path to cue_cache dir")
    parser.add_argument("--model", default="llama3.1:8b", help="Ollama model to use")
    parser.add_argument("--nuke-all", action="store_true", help="Delete ALL cache files, not just phishing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen, don't call Ollama")
    args = parser.parse_args()

    emails_path = Path(args.emails)
    cache_dir = Path(args.cache)

    if not emails_path.exists():
        print(f"ERROR: emails CSV not found at {emails_path}")
        sys.exit(1)

    emails_df = pd.read_csv(emails_path)
    print(f"Loaded {len(emails_df)} emails from {emails_path}")
    print(emails_df["source"].value_counts().to_string())

    # -- Check Ollama --------------------------------------------------------
    extractor = OllamaExtractor(model=args.model, cache_dir=str(cache_dir))
    if not args.dry_run:
        if not extractor.is_available():
            print(f"\nERROR: Ollama not available or model '{args.model}' not pulled.")
            print(f"Run: ollama pull {args.model}")
            sys.exit(1)
        print(f"\nOllama OK — using model: {args.model}")
    else:
        print(f"\n[DRY RUN] Would use model: {args.model}")

    # -- Wipe caches ---------------------------------------------------------
    if args.nuke_all:
        n = wipe_all_caches(cache_dir, dry_run=args.dry_run)
        print(f"{'[DRY RUN] Would delete' if args.dry_run else 'Deleted'} {n} cache files (all).")
    else:
        deleted, total_phishing = wipe_phishing_caches(emails_df, cache_dir, dry_run=args.dry_run)
        print(f"{'[DRY RUN] Would delete' if args.dry_run else 'Deleted'} {deleted}/{total_phishing} "
              f"phishing email caches. Ham caches kept intact.")

    if args.dry_run:
        print("\n[DRY RUN] Skipping extraction. Remove --dry-run to run for real.")
        return

    # -- Run extraction ------------------------------------------------------
    print(f"\nStarting extraction for {len(emails_df)} emails (cache-first)...")
    print("Benign emails: will use existing cache. Phishing: will call Ollama.\n")

    t0 = time.time()
    email_cues = extractor.extract_batch(emails_df)
    elapsed = time.time() - t0

    # -- Save summary --------------------------------------------------------
    print(f"\nExtraction done in {elapsed:.1f}s")
    print_summary(email_cues, emails_df)

    # Spot-check a few phishing emails
    phishing_ids = emails_df[emails_df["actual_class"] == 1]["email_id"].tolist()[:5]
    print("\n=== Spot-check (first 5 phishing emails) ===")
    for eid in phishing_ids:
        src = emails_df[emails_df["email_id"] == eid]["source"].values[0]
        cues = email_cues.get(eid, [])
        subj = emails_df[emails_df["email_id"] == eid]["subject"].values[0][:60]
        print(f"  email_{eid} ({src}): {cues}")
        print(f"    subject: {subj}")


if __name__ == "__main__":
    main()
