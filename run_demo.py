"""
run_demo.py — THE entry point for the v2 pipeline.

Builds the expanded multi-source corpus, regenerates the provenance datasheet,
extracts cues, runs the v2 simulation, and prints per-source results with the
V-Triad cue/click story. Non-destructive: writes only *_v2 artefacts.

Usage
-----
  python run_demo.py                    # build + extract (cache-first) + simulate + report
  python run_demo.py --generate 120     # ALSO generate 120 more of each synthetic class via Groq
  python run_demo.py --charts           # also write the presentation charts
  python run_demo.py --extractor ollama --ollama-model gemma4:12b    # local extraction instead

Notes
-----
* Cue extraction is cache-first (`data/cue_cache_v2/`). Once populated the demo replays
  instantly with no API calls — safe to run live in front of an audience.
* `--generate` needs GROQ_API_KEY in .env and CLEARS the cue cache (composition changes).
* For the full analysis + charts, use `notebooks/06_agent_simulation_v2.ipynb`.
"""
import argparse
import os
import re
import shutil
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

import pandas as pd
from src import dataset_v2 as ds, groq_client, provenance
from src.agent_v2 import run_simulation_v2

CACHE = "data/cue_cache_v2"
MASTER = "data/processed/master_emails_v2.csv"
RESULTS = "data/simulation_results_v2.csv"
HL = "hybrid_vtriad"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", type=int, default=0,
                    help="generate N more of EACH synthetic class (plain_llm, hybrid_vtriad) via Groq")
    ap.add_argument("--ham", type=int, default=450, help="SpamAssassin ham to sample")
    ap.add_argument("--agents", type=int, default=30)
    # Default to local: reproducible, no rate limits, no key, and ~5x faster in practice
    # than the hosted free tier (which throttles to ~44s/call once its token bucket drains).
    ap.add_argument("--extractor", choices=["groq", "ollama"], default="ollama")
    ap.add_argument("--ollama-model", default="gemma4:12b")
    ap.add_argument("--charts", action="store_true", help="also write presentation charts")
    args = ap.parse_args()

    # 1. optional synthetic generation
    if args.generate > 0:
        if not groq_client.is_available():
            print("Groq unavailable — add GROQ_API_KEY to .env. Skipping generation.")
            return
        for style in ("plain_llm", "hybrid_vtriad"):
            print(f"Generating {args.generate} more '{style}' via Groq...")
            groq_client.save_generated(groq_client.generate_phishing(style, args.generate), style)
        shutil.rmtree(CACHE, ignore_errors=True)
        print("cleared cue cache (dataset composition changed)")

    # 2. build the expanded, segregated, deduped corpus
    df = ds.build_target_corpus(seed=42, ham_n=args.ham, enron_n=200, ceas_n=130,
                                nazario_n=110, nigerian_n=90, phishbowl_cap=90,
                                plain_cap=110, vtriad_cap=120)
    print(f"\nCorpus: {len(df)} emails "
          f"({(df.actual_class==0).sum()} benign / {(df.actual_class==1).sum()} phishing)")
    print(df.groupby(["source", "actual_class"]).size().to_string())

    # 3. keep the datasheet + composition chart in sync with what was actually built
    provenance.generate_all()
    print("regenerated DATA_PROVENANCE.md + sources_manifest.json + composition chart")

    # 4. extract cues + simulate
    #
    # Cache is scoped PER EXTRACTOR MODEL. Cache keys are content hashes with no model in
    # them, so a shared directory would let one model reuse another's cues — e.g. an ollama
    # run silently inheriting groq's ham entries. Cue counts are the headline measure, so a
    # corpus extracted by two different models is confounded: a source's cue count would
    # partly reflect *which model happened to see it*. One model per cache = comparable.
    model_slug = (args.ollama_model if args.extractor == "ollama" else "groq-scout")
    model_slug = re.sub(r"[^a-z0-9]+", "-", model_slug.lower()).strip("-")
    cache_dir = os.path.join(CACHE, model_slug)
    print(f"\ncue cache: {cache_dir}  (per-model — no cross-extractor mixing)")

    res = run_simulation_v2(emails_csv=MASTER, n_agents=args.agents, seed=42, cache_dir=cache_dir,
                            correlated=True, extractor=args.extractor,
                            ollama_model=args.ollama_model)
    res.to_csv(RESULTS, index=False)

    # 5. report
    res["clicked"] = (res.decision == "clicked").astype(int)
    ph, bn = res[res.actual_class == 1], res[res.actual_class == 0]
    cues = res.drop_duplicates("email_id").groupby("source")["cues_extracted"].mean()
    rate = ph.groupby("source")["clicked"].mean().sort_values(ascending=False)
    print("\n=== PER-SOURCE: avg cues -> phishing click rate ===")
    for s in rate.index:
        print(f"  {s:<18} cues={cues.get(s, float('nan')):.2f}   click={rate[s]:.1%}"
              + ("   <-- fewest cues, most clicks" if s == HL else ""))
    print(f"\nbenign FPR: {1 - bn['clicked'].mean():.1%}")
    wd = ph.pivot_table("clicked", "agent_id", "workday_hour")
    if 16.0 in wd.columns and 8.0 in wd.columns:
        print(f"within-agent workday effect (4pm-8am): {(wd[16.0] - wd[8.0]).mean():+.1%}")
    print(f"\nsaved {RESULTS} ({len(res):,} rows)")

    if args.charts:
        _charts(ph, bn, cues, rate)


def _charts(ph, bn, cues, rate):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    col = lambda s: "#c0392b" if s == HL else "#7f8c8d"

    fig, ax = plt.subplots(figsize=(8.5, 6))
    for s in rate.index:
        ax.scatter(cues[s], rate[s], s=190, color=col(s), zorder=3, edgecolor="white", linewidth=1.5)
        ax.annotate(s, (cues[s], rate[s]), xytext=(7, 7), textcoords="offset points",
                    fontsize=10, fontweight=("bold" if s == HL else "normal"))
    ax.set_xlabel("Avg detectable cues per email  (lower = harder to detect)")
    ax.set_ylabel("Phishing click rate")
    ax.set_title("Fewer detectable cues -> more clicks. V-Triad = fewest cues, most clicks.")
    ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig("results/v2_demo_cues_vs_click.png", dpi=150); plt.close()

    o = rate.sort_values()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(o.index, o.values, color=[col(s) for s in o.index])
    for s, v in o.items():
        ax.text(v + 0.008, s, f"{v:.0%}", va="center", fontsize=9)
    ax.set_xlim(0, 1); ax.set_xlabel("phishing click rate")
    ax.set_title("Phishing click rate by source (V-Triad in red)")
    plt.tight_layout(); plt.savefig("results/v2_demo_click_by_source.png", dpi=150); plt.close()

    curve = ph.pivot_table("clicked", "source", "workday_hour")
    fig, ax = plt.subplots(figsize=(9, 5))
    for s in curve.index:
        ax.plot(curve.columns, curve.loc[s], marker="o", label=s,
                linewidth=(3 if s == HL else 1.4), color=col(s))
    ax.set_xticks([8, 10, 12, 14, 16]); ax.set_xticklabels(["8am", "10am", "12pm", "2pm", "4pm"])
    ax.set_ylabel("phishing click rate"); ax.set_title("Click rate across the workday, by source")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig("results/v2_demo_workday.png", dpi=150); plt.close()
    print("charts -> results/v2_demo_*.png")


if __name__ == "__main__":
    main()
