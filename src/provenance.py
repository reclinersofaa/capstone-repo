"""
provenance.py — dataset segregation + provenance/transparency for publication.

Two outputs, both generated FROM the actual assembled master (so they can never
drift from what is really in the corpus):

  1. DATA_PROVENANCE.md          — human-readable datasheet (per-source origin, URL/DOI,
                                    license, retrieval date, cleaning steps, raw->final counts)
  2. data/processed/sources_manifest.json  — machine-readable version

Plus results/v2_dataset_composition.png — a visual of the per-source segregation.

Every email row keeps its own `source` value; sources are never merged. Adding a new
dataset = one SOURCE_REGISTRY entry + a loader in dataset_v2.py; the datasheet and the
chart regenerate automatically.

Publication policy baked in: ship loader CODE + DOIs, NOT re-hosted corpora. Licenses
marked "verify" MUST be confirmed on the source page before any public release.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

MASTER = Path("data/processed/master_emails_v2.csv")
OUT_MD = Path("DATA_PROVENANCE.md")
OUT_JSON = Path("data/processed/sources_manifest.json")
OUT_PNG = Path("results/v2_dataset_composition.png")

# ---------------------------------------------------------------------------
# The single catalogue of truth for where every source comes from.
# status: "in_dataset" (currently assembled) | "planned" (target composition)
# license_status: "verified" | "verify"  (verify = confirm on source page before publishing)
# ---------------------------------------------------------------------------
SOURCE_REGISTRY = {
    "spamassassin_ham": {
        "display_name": "SpamAssassin Public Corpus (easy_ham + hard_ham)",
        "kind": "benign", "actual_class": 0, "status": "in_dataset",
        "origin": "Apache SpamAssassin public corpus", "access": "kaggle_mirror",
        "url": "https://spamassassin.apache.org/old/publiccorpus/",
        "mirror": "kaggle:beatoa/spamassassin-public-corpus",
        "license": "Apache SpamAssassin public corpus (free for research)",
        "license_status": "verified", "retrieved": "2026-07-16",
        "cleaning": "RFC822 parsed; From/Subject/plain-text body extracted; spam_2 excluded; __MACOSX filtered; body capped 4000 chars",
        "citation": "The Apache SpamAssassin Project, Public Corpus.",
    },
    "phishbowl": {
        "display_name": "Cornell University Phish Bowl (real phishing)",
        "kind": "real_phishing", "actual_class": 1, "status": "in_dataset",
        "origin": "Cornell University IT Security Phish Bowl archive", "access": "provided_csv",
        "url": "https://it.cornell.edu/phish-bowl",
        "license": "Cornell IT public phish archive — verify redistribution terms",
        "license_status": "verify", "retrieved": "2026-07-16",
        "cleaning": "Stripped Cornell IT warning-notice <div> boilerplate; recovered spoofed sender from notice; HTML/entities stripped; dropped records <40 chars",
        "citation": "Cornell University, IT@Cornell Phish Bowl.",
    },
    "plain_llm": {
        "display_name": "Plain LLM phishing (naive, self-generated)",
        "kind": "synthetic_llm", "actual_class": 1, "status": "in_dataset",
        "origin": "Self-generated (GPT / Claude / Gemini, unguided) + Groq additions", "access": "self_generated",
        "url": "n/a (generated in-project)",
        "license": "Own work — CC-BY or project license", "license_status": "verified",
        "retrieved": "2026-07-16",
        "cleaning": "Prompted for obvious phishing cues; fictional entities only; no real brands/people/domains",
        "citation": "This project — synthetic naive-LLM phishing.",
    },
    "hybrid_vtriad": {
        "display_name": "Hybrid V-Triad phishing (guided, self-generated)",
        "kind": "synthetic_llm", "actual_class": 1, "status": "in_dataset",
        "origin": "Self-generated with V-Triad persuasion framework + Groq additions", "access": "self_generated",
        "url": "n/a (generated in-project)",
        "license": "Own work — CC-BY or project license", "license_status": "verified",
        "retrieved": "2026-07-16",
        "cleaning": "V-Triad-guided prompts (visceral/tribal/danger); corporate tone, minimal overt cues; fictional entities only",
        "citation": "This project — synthetic V-Triad phishing (no public V-Triad corpus exists).",
    },
    # ---- planned additions (from the dataset-expansion research) ----
    "nazario": {
        "display_name": "Nazario Phishing Corpus", "kind": "real_phishing", "actual_class": 1,
        "status": "planned", "origin": "J. Nazario in-the-wild phishing collection",
        "access": "kaggle_csv", "url": "https://monkey.org/~jose/phishing/",
        "mirror": "kaggle:naserabdullahalam/phishing-email-dataset (Nazario.csv)",
        "license": "Academic-use collection — cite original, verify redistribution",
        "license_status": "verify", "retrieved": "2026-07-16",
        "cleaning": "Nazario.csv (label==1); dropped MAILER-DAEMON/folder-internal-data junk rows; whitespace-normalized; body capped 6000; seeded sample; deduped on body hash",
        "citation": "J. Nazario, Phishing Corpus.",
    },
    "ceas08": {
        "display_name": "CEAS 2008 Live Spam Challenge (phishing subset)", "kind": "real_phishing",
        "actual_class": 1, "status": "planned", "origin": "CEAS 2008 conference corpus",
        "access": "kaggle_csv", "url": "https://www.kaggle.com/datasets/naserabdullahalam/phishing-email-dataset",
        "mirror": "kaggle:naserabdullahalam/phishing-email-dataset (CEAS_08.csv)",
        "license": "Merged Kaggle listing unclear — cite original CEAS-08 source",
        "license_status": "verify", "retrieved": "2026-07-16",
        "cleaning": "CEAS_08.csv filtered to label==1; whitespace-normalized; body capped 6000; seeded sample; deduped on body hash",
        "citation": "CEAS 2008 Live Spam Challenge Corpus.",
    },
    "nigerian_fraud": {
        "display_name": "Nigerian / 419 Fraudulent Email Corpus", "kind": "real_phishing",
        "actual_class": 1, "status": "planned", "origin": "Advance-fee (419) fraud email collection",
        "access": "kaggle_csv", "url": "https://www.kaggle.com/datasets/rtatman/fraudulent-email-corpus",
        "mirror": "kaggle:naserabdullahalam/phishing-email-dataset (Nigerian_Fraud.csv)",
        "license": "Public-domain-style academic corpus — verify", "license_status": "verify",
        "retrieved": "2026-07-16", "cleaning": "Nigerian_Fraud.csv (label==1); whitespace-normalized; body capped 6000; seeded sample; deduped on body hash",
        "citation": "Fraudulent E-mail Corpus (Nigerian/419).",
    },
    "enron_clean": {
        "display_name": "Enron emails (pre-cleaned)", "kind": "benign", "actual_class": 0,
        "status": "planned", "origin": "CMU/FERC Enron corpus, parsed",
        "access": "huggingface", "url": "https://huggingface.co/datasets/corbt/enron-emails",
        "license": "Enron corpus is public (CMU/FERC); HF card omits explicit license — cite, do not re-host",
        "license_status": "verify", "retrieved": "2026-07-16",
        "cleaning": "HF corbt/enron-emails parquet (from/subject/body); body>=40 chars; whitespace-normalized; capped 6000; seeded sample; deduped on body hash",
        "citation": "Klimt & Yang (2004), The Enron Corpus.",
    },
    "multi_llm": {
        "display_name": "Cross-model Multi-LLM Phishing Corpus (GPT-4.1 / DeepSeek-3.2 / Llama-3.3-70b)",
        "kind": "synthetic_llm", "actual_class": 1, "status": "in_dataset",
        "origin": "Gutierrez, Villegas-Ch & Govea (2026), Universidad de las Américas, Quito — accompanies Frontiers in Big Data 10.3389/fdata.2026.1883452",
        "access": "zenodo", "url": "https://doi.org/10.5281/zenodo.20250116",
        "license": "CC BY 4.0 (data) / MIT (code) — record states: intended exclusively for defensive security research and academic study",
        "license_status": "verified", "retrieved": "2026-07-16",
        "cleaning": "VERIFIED raw bodies: llm_corpus_sampled.csv (4,986 rows) ships real subject+body, separate from corpus_features.csv. LLM half ONLY — the 5,000 human rows duplicate CEAS-08/Nazario/419/Enron already present. Sampled evenly across the 3 generating models; whitespace-normalized; body capped 6000; deduped on body hash.",
        "citation": "Gutierrez, Villegas-Ch & Govea (2026), Cross-model evaluation of phishing detectors against LLM-generated emails, Zenodo, doi:10.5281/zenodo.20250116 (CC BY 4.0).",
        "caveat": "Ships NO sender field, so the `suspicious_sender` cue can never fire for these emails — their cue count is not perfectly comparable with sources that carry senders.",
    },
    "trec07_ham": {
        "display_name": "TREC 2007 Public Corpus — benign half (named benchmark)",
        "kind": "benign", "actual_class": 0, "status": "in_dataset",
        "origin": "TREC 2007 Spam Track (Cormack & Lynam, Univ. of Waterloo), via the curated Zenodo release",
        "access": "zenodo", "url": "https://doi.org/10.5281/zenodo.8339691",
        "mirror": "zenodo:8339691 (TREC_07.csv — 53,757 rows: 24,358 ham / 29,399 spam)",
        "license": "CC BY 4.0 asserted on the Zenodo record by Champa et al. (NOT by Cormack/Waterloo) — cite the original TREC track",
        "license_status": "verify", "retrieved": "2026-07-16",
        "cleaning": "label==0 (ham) only; whitespace-normalized; body capped 6000; seeded sample; deduped on body hash. The TREC SPAM half is deliberately EXCLUDED — spam is not targeted phishing, and labelling it class 1 would corrupt the construct.",
        "citation": "Cormack & Lynam (2007), TREC 2007 Spam Track Overview. Curated release: Champa, Rabbi & Zibran, Zenodo doi:10.5281/zenodo.8339691.",
    },
}

# Sources we evaluated and did NOT ingest. Recording the rejects — with the reason and the
# evidence — is what makes a datasheet defensible: it shows the corpus is a chosen set, not
# whatever happened to be easy to download.
REJECTED_SOURCES = [
    {"name": "IWSPA-AP 2018 shared-task corpus",
     "url": "https://dasavisha.github.io/IWSPA-sharedtask/",
     "reason": "NOT OBTAINABLE. Registration-only via EasyChair since 2018; site frozen at the 2018 workshop; "
               "backing GitHub repo contains only Jekyll site files, no data. Both candidate mirrors are duds "
               "(one a 91-byte empty README; one adversarial GPT-2-synthetic derivatives of IWSPA 2.0, not the corpus). "
               "Only remaining route is emailing two 8-year-stale personal Gmail addresses — not demo-safe."},
    {"name": "TREC 2007 — spam half (29,399 emails)",
     "url": "https://doi.org/10.5281/zenodo.8339691",
     "reason": "DELIBERATELY EXCLUDED, not unavailable. Spam is not targeted phishing; labelling it actual_class=1 "
               "would corrupt the construct this simulation measures. Only the ham half is ingested."},
    {"name": "Cross-model corpus — human half (5,000 emails)",
     "url": "https://doi.org/10.5281/zenodo.20250116",
     "reason": "DELIBERATELY EXCLUDED. Drawn from CEAS-08 / Nazario / Nigerian-Fraud / Enron, which are already "
               "ingested as first-class sources — including it would duplicate them and inflate counts."},
    {"name": "MeAJOR Corpus (Zenodo 18471483 / arXiv 2507.17978)",
     "url": "https://arxiv.org/abs/2507.17978",
     "reason": "REJECTED for ingestion. Bodies are token-anonymized ([NAME], [EMAIL_ADDRESS], [URL], [IP_ADDRESS]), "
               "which destroys the URL- and sender-based cues this model depends on. Cite as related work instead."},
    {"name": "Zenodo 13474746 ('phishing' dataset)",
     "url": "https://zenodo.org/records/13474746",
     "reason": "REJECTED. Inspection showed synthetic, duplicated one-line templates despite attractive framing — "
               "a trap for anyone shopping by title."},
    {"name": "PhishTank / APWG feeds",
     "url": "https://phishtank.org",
     "reason": "REJECTED as out-of-scope. These are URL/blocklist feeds, not full email bodies; this pipeline "
               "extracts cues from message text."},
]

_CLASS_NAME = {0: "benign", 1: "phishing"}

# The models that PROCESSED the corpus are part of the method's provenance: the
# extraction model materially changes cue counts (llama-3.1-8b over-flags benign at
# ~1.7 cues/email vs llama-4-scout at ~0.0), so it must be recorded alongside the data.
PIPELINE_MODELS = {
    "cue_extraction": {
        "model": "gemma4:12b (Ollama, local — RTX 4060 Ti 16GB)",
        "why": "reproducible (open weights, runs offline), no rate limits, ~0.55s/email; "
               "the whole 1,595-email corpus is extracted by ONE model in ~13 min",
        "note": "REPLICATION: llama-4-scout-17b (Groq) independently produces the same "
                "source ranking — V-Triad lowest cues / highest clicks — so the headline "
                "result is not an artifact of one extractor. Scout's cues are retained in "
                "data/cue_cache_v2/groq-scout/ for comparison. Cache is scoped per model: "
                "cue counts from different extractors are NOT comparable and must never be "
                "mixed within one corpus. Rejected: llama-3.1-8b (over-flags benign, ~1.7 "
                "cues vs ~0.0); llama-3.3-70b (free daily cap 429s mid-corpus); "
                "gpt-oss-120b / zai-glm-4.7 (reasoning-only, return no content field).",
        "batching": "8 emails/call, per-email fallback on malformed batch response "
                    "(fell back on 13 batches of ~200 — model returned 7 arrays for 8 emails)",
        "gotcha": "Reasoning models REQUIRE 'think': False. Without it Ollama spends the whole "
                  "num_predict budget on hidden reasoning, strips it from 'response', and "
                  "returns an empty string — indistinguishable from 'no cues found'.",
    },
    "synthetic_generation": {
        "model": "llama-3.3-70b-versatile (Groq)",
        "why": "best writing quality; only ~24 calls needed, so the small daily cap is not binding",
        "note": "used ONLY for plain_llm / hybrid_vtriad generation. Fictional entities only.",
    },
}


def build_manifest(master: Path = MASTER) -> dict:
    df = pd.read_csv(master)
    counts = df.groupby("source").size().to_dict()
    present, planned = [], []
    for src, meta in SOURCE_REGISTRY.items():
        row = {"source": src, "n": int(counts.get(src, 0)), **meta}
        (present if src in counts else planned).append(row)
    present.sort(key=lambda r: (-r["n"]))
    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "master_file": str(master), "total_emails": int(len(df)),
        "benign": int((df.actual_class == 0).sum()), "phishing": int((df.actual_class == 1).sum()),
        "sources_in_dataset": present, "planned_additions": planned,
        "pipeline_models": PIPELINE_MODELS,
    }


def write_manifest_json(manifest: dict, out: Path = OUT_JSON):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))


def write_datasheet(manifest: dict, out: Path = OUT_MD):
    m = manifest
    L = []
    L.append("# Dataset Provenance & Transparency\n")
    L.append(f"> Auto-generated from `{m['master_file']}` on {m['generated']}. "
             "Do not edit by hand — regenerate with `python -m src.provenance`.\n")
    L.append(f"**Corpus:** {m['total_emails']} emails — {m['benign']} benign / {m['phishing']} phishing. "
             f"{len(m['sources_in_dataset'])} segregated sources.\n")
    L.append("Every email is tagged with its `source` in `master_emails_v2.csv`; sources are never blended, "
             "so cue behaviour and click rates can always be sliced per origin.\n")

    L.append("\n## Sources currently in the dataset\n")
    L.append("| source | class | kind | n | origin | license | retrieved |")
    L.append("|---|---|---|---:|---|---|---|")
    for r in m["sources_in_dataset"]:
        lic = r["license"] + (" ⚠️" if r["license_status"] == "verify" else " ✅")
        L.append(f"| `{r['source']}` | {_CLASS_NAME[r['actual_class']]} | {r['kind']} | {r['n']} | "
                 f"{r['origin']} | {lic} | {r['retrieved']} |")

    L.append("\n### Per-source detail\n")
    for r in m["sources_in_dataset"]:
        L.append(f"**`{r['source']}` — {r['display_name']}** ({r['n']} emails)")
        L.append(f"- Origin: {r['origin']}")
        L.append(f"- URL / access: {r['url']}" + (f"  (mirror: `{r['mirror']}`)" if r.get("mirror") else ""))
        L.append(f"- License: {r['license']}  *({r['license_status']})*")
        L.append(f"- Retrieved: {r['retrieved']}")
        L.append(f"- Cleaning applied: {r['cleaning']}")
        if r.get("caveat"):
            L.append(f"- ⚠️ Caveat: {r['caveat']}")
        L.append(f"- Cite as: {r['citation']}\n")

    if m["planned_additions"]:
        L.append("\n## Planned additions (target composition — not yet ingested)\n")
        L.append("| source | class | kind | origin | access | url / DOI | license |")
        L.append("|---|---|---|---|---|---|---|")
        for r in m["planned_additions"]:
            lic = r["license"] + (" ⚠️" if r["license_status"] == "verify" else " ✅")
            L.append(f"| `{r['source']}` | {_CLASS_NAME[r['actual_class']]} | {r['kind']} | "
                     f"{r['origin']} | {r['access']} | {r['url']} | {lic} |")

    L.append("\n## Evaluated and NOT ingested\n")
    L.append("Recording rejects — with the reason — shows the corpus is a *chosen* set, not whatever "
             "was easiest to download.\n")
    for r in REJECTED_SOURCES:
        L.append(f"**{r['name']}** — {r['url']}")
        L.append(f"- {r['reason']}\n")

    L.append("\n## Pipeline models (method provenance)\n")
    L.append("The models that *processed* the corpus are part of the method — the extraction model "
             "measurably changes cue counts, so it is recorded here alongside the data sources.\n")
    for stage, mm in m["pipeline_models"].items():
        L.append(f"**{stage}** — `{mm['model']}`")
        L.append(f"- Why: {mm['why']}")
        if mm.get("batching"):
            L.append(f"- Batching: {mm['batching']}")
        L.append(f"- Note: {mm['note']}\n")

    L.append("\n## Publication policy\n")
    L.append("- **Ship loader code + DOIs/URLs, not re-hosted corpora.** This repo's `src/dataset_v2.py` "
             "reconstructs the corpus from the original sources; we do not redistribute third-party email data.")
    L.append("- Sources marked ⚠️ (`verify`) have unclear or inherited licenses — **confirm on the source page "
             "before any public release**, and cite the ORIGINAL corpus, not a merged mirror.")
    L.append("- Real phishing may contain live-looking malicious URLs; the pipeline extracts text only and never "
             "renders HTML or fetches links.")
    L.append("- Personal data: benign corpora (Enron/SpamAssassin) contain real names/addresses from public "
             "research corpora — used for research, not re-published beyond the original terms.\n")
    out.write_text("\n".join(L), encoding="utf-8")


def plot_composition(master: Path = MASTER, out: Path = OUT_PNG):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = pd.read_csv(master)
    g = df.groupby(["source", "actual_class"]).size().unstack(fill_value=0)
    for c in (0, 1):
        if c not in g.columns:
            g[c] = 0
    g = g.sort_values(by=[1, 0], ascending=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(g.index, g[0], color="#2ecc71", label="benign")
    ax.barh(g.index, g[1], left=g[0], color="#e74c3c", label="phishing")
    for i, src in enumerate(g.index):
        total = int(g.loc[src, 0] + g.loc[src, 1])
        ax.text(total + 3, i, str(total), va="center", fontsize=9)
    ax.set_xlabel("emails"); ax.set_title("Dataset composition by source (segregated)")
    ax.legend(loc="lower right")
    plt.tight_layout(); out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150); plt.close()


def generate_all(master: Path = MASTER):
    manifest = build_manifest(master)
    write_manifest_json(manifest)
    write_datasheet(manifest)
    plot_composition(master)
    return manifest


if __name__ == "__main__":
    mani = generate_all()
    print(f"sources in dataset: {len(mani['sources_in_dataset'])} | planned: {len(mani['planned_additions'])}")
    print(f"wrote {OUT_MD}, {OUT_JSON}, {OUT_PNG}")
