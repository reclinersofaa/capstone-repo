# Dataset Provenance & Transparency

> Auto-generated from `data\processed\master_emails_v2.csv` on 2026-09-22 10:56. Do not edit by hand — regenerate with `python -m src.provenance`.

**Corpus:** 618 emails — 300 benign / 318 phishing. 5 segregated sources.

Every email is tagged with its `source` in `master_emails_v2.csv`; sources are never blended, so cue behaviour and click rates can always be sliced per origin.


## Sources currently in the dataset

| source | class | kind | n | origin | license | retrieved |
|---|---|---|---:|---|---|---|
| `enron_clean` | benign | benign | 200 | CMU/FERC Enron corpus, parsed | Enron corpus is public (CMU/FERC); HF card omits explicit license — cite, do not re-host ⚠️ | 2026-07-16 |
| `hybrid_vtriad` | phishing | synthetic_llm | 120 | Self-generated with V-Triad persuasion framework + Groq additions | Own work — CC-BY or project license ✅ | 2026-07-16 |
| `plain_llm` | phishing | synthetic_llm | 110 | Self-generated (GPT / Claude / Gemini, unguided) + Groq additions | Own work — CC-BY or project license ✅ | 2026-07-16 |
| `spamassassin_ham` | benign | benign | 100 | Apache SpamAssassin public corpus | Apache SpamAssassin public corpus (free for research) ✅ | 2026-07-16 |
| `phishbowl` | phishing | real_phishing | 88 | Cornell University IT Security Phish Bowl archive | Cornell IT public phish archive — verify redistribution terms ⚠️ | 2026-07-16 |

### Per-source detail

**`enron_clean` — Enron emails (pre-cleaned)** (200 emails)
- Origin: CMU/FERC Enron corpus, parsed
- URL / access: https://huggingface.co/datasets/corbt/enron-emails
- License: Enron corpus is public (CMU/FERC); HF card omits explicit license — cite, do not re-host  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: HF corbt/enron-emails parquet (from/subject/body); body>=40 chars; whitespace-normalized; capped 6000; seeded sample; deduped on body hash
- Cite as: Klimt & Yang (2004), The Enron Corpus.

**`hybrid_vtriad` — Hybrid V-Triad phishing (guided, self-generated)** (120 emails)
- Origin: Self-generated with V-Triad persuasion framework + Groq additions
- URL / access: n/a (generated in-project)
- License: Own work — CC-BY or project license  *(verified)*
- Retrieved: 2026-07-16
- Cleaning applied: V-Triad-guided prompts (visceral/tribal/danger); corporate tone, minimal overt cues; fictional entities only
- Cite as: This project — synthetic V-Triad phishing (no public V-Triad corpus exists).

**`plain_llm` — Plain LLM phishing (naive, self-generated)** (110 emails)
- Origin: Self-generated (GPT / Claude / Gemini, unguided) + Groq additions
- URL / access: n/a (generated in-project)
- License: Own work — CC-BY or project license  *(verified)*
- Retrieved: 2026-07-16
- Cleaning applied: Prompted for obvious phishing cues; fictional entities only; no real brands/people/domains
- Cite as: This project — synthetic naive-LLM phishing.

**`spamassassin_ham` — SpamAssassin Public Corpus (easy_ham + hard_ham)** (100 emails)
- Origin: Apache SpamAssassin public corpus
- URL / access: https://spamassassin.apache.org/old/publiccorpus/  (mirror: `kaggle:beatoa/spamassassin-public-corpus`)
- License: Apache SpamAssassin public corpus (free for research)  *(verified)*
- Retrieved: 2026-07-16
- Cleaning applied: RFC822 parsed; From/Subject/plain-text body extracted; spam_2 excluded; __MACOSX filtered; body capped 4000 chars
- Cite as: The Apache SpamAssassin Project, Public Corpus.

**`phishbowl` — Cornell University Phish Bowl (real phishing)** (88 emails)
- Origin: Cornell University IT Security Phish Bowl archive
- URL / access: https://it.cornell.edu/phish-bowl
- License: Cornell IT public phish archive — verify redistribution terms  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: Stripped Cornell IT warning-notice <div> boilerplate; recovered spoofed sender from notice; HTML/entities stripped; dropped records <40 chars
- Cite as: Cornell University, IT@Cornell Phish Bowl.


## Planned additions (target composition — not yet ingested)

| source | class | kind | origin | access | url / DOI | license |
|---|---|---|---|---|---|---|
| `nazario` | phishing | real_phishing | J. Nazario in-the-wild phishing collection | kaggle_csv | https://monkey.org/~jose/phishing/ | Academic-use collection — cite original, verify redistribution ⚠️ |
| `ceas08` | phishing | real_phishing | CEAS 2008 conference corpus | kaggle_csv | https://www.kaggle.com/datasets/naserabdullahalam/phishing-email-dataset | Merged Kaggle listing unclear — cite original CEAS-08 source ⚠️ |
| `nigerian_fraud` | phishing | real_phishing | Advance-fee (419) fraud email collection | kaggle_csv | https://www.kaggle.com/datasets/rtatman/fraudulent-email-corpus | Public-domain-style academic corpus — verify ⚠️ |
| `multi_llm` | phishing | synthetic_llm | Gutierrez, Villegas-Ch & Govea (2026), Universidad de las Américas, Quito — accompanies Frontiers in Big Data 10.3389/fdata.2026.1883452 | zenodo | https://doi.org/10.5281/zenodo.20250116 | CC BY 4.0 (data) / MIT (code) — record states: intended exclusively for defensive security research and academic study ✅ |
| `trec07_ham` | benign | benign | TREC 2007 Spam Track (Cormack & Lynam, Univ. of Waterloo), via the curated Zenodo release | zenodo | https://doi.org/10.5281/zenodo.8339691 | CC BY 4.0 asserted on the Zenodo record by Champa et al. (NOT by Cormack/Waterloo) — cite the original TREC track ⚠️ |

## Evaluated and NOT ingested

Recording rejects — with the reason — shows the corpus is a *chosen* set, not whatever was easiest to download.

**IWSPA-AP 2018 shared-task corpus** — https://dasavisha.github.io/IWSPA-sharedtask/
- NOT OBTAINABLE. Registration-only via EasyChair since 2018; site frozen at the 2018 workshop; backing GitHub repo contains only Jekyll site files, no data. Both candidate mirrors are duds (one a 91-byte empty README; one adversarial GPT-2-synthetic derivatives of IWSPA 2.0, not the corpus). Only remaining route is emailing two 8-year-stale personal Gmail addresses — not demo-safe.

**TREC 2007 — spam half (29,399 emails)** — https://doi.org/10.5281/zenodo.8339691
- DELIBERATELY EXCLUDED, not unavailable. Spam is not targeted phishing; labelling it actual_class=1 would corrupt the construct this simulation measures. Only the ham half is ingested.

**Cross-model corpus — human half (5,000 emails)** — https://doi.org/10.5281/zenodo.20250116
- DELIBERATELY EXCLUDED. Drawn from CEAS-08 / Nazario / Nigerian-Fraud / Enron, which are already ingested as first-class sources — including it would duplicate them and inflate counts.

**MeAJOR Corpus (Zenodo 18471483 / arXiv 2507.17978)** — https://arxiv.org/abs/2507.17978
- REJECTED for ingestion. Bodies are token-anonymized ([NAME], [EMAIL_ADDRESS], [URL], [IP_ADDRESS]), which destroys the URL- and sender-based cues this model depends on. Cite as related work instead.

**Zenodo 13474746 ('phishing' dataset)** — https://zenodo.org/records/13474746
- REJECTED. Inspection showed synthetic, duplicated one-line templates despite attractive framing — a trap for anyone shopping by title.

**PhishTank / APWG feeds** — https://phishtank.org
- REJECTED as out-of-scope. These are URL/blocklist feeds, not full email bodies; this pipeline extracts cues from message text.


## Pipeline models (method provenance)

The models that *processed* the corpus are part of the method — the extraction model measurably changes cue counts, so it is recorded here alongside the data sources.

**cue_extraction** — `gemma4:12b (Ollama, local — RTX 4060 Ti 16GB)`
- Why: reproducible (open weights, runs offline), no rate limits, ~0.55s/email; the whole 1,595-email corpus is extracted by ONE model in ~13 min
- Batching: 8 emails/call, per-email fallback on malformed batch response (fell back on 13 batches of ~200 — model returned 7 arrays for 8 emails)
- Note: REPLICATION (pending re-verification): llama-4-scout-17b (Groq) independently produced the same source ranking on the PRE-FIX corpus. That check has not been re-run since the Sept 2026 hybrid_vtriad validity fix (see notebooks/07_vtriad_validity_fix.ipynb) — treat cross-extractor replication as stale, not confirmed, until it is. Scout's cues are retained in data/cue_cache_v2/groq-scout/ for comparison. Cache is scoped per model: cue counts from different extractors are NOT comparable and must never be mixed within one corpus. Rejected for extraction: llama-3.1-8b (over-flags benign, ~1.7 cues vs ~0.0); llama-3.3-70b (free daily cap 429s mid-corpus, since retired by Groq entirely); gpt-oss-120b / zai-glm-4.7 / qwen3 base (reasoning-only, return no content field).

**synthetic_generation** — `qwen/qwen3.8-27b (Groq)`
- Why: best writing quality; only ~24 calls needed at batch_size=4, well under the model's 1000 output-tokens-per-minute cap
- Note: used ONLY for plain_llm / hybrid_vtriad generation. Fictional entities only. Prior model llama-3.3-70b-versatile was retired by Groq (Sept 2026, confirmed via a live 404) and replaced; groq/compound-mini and gpt-oss-120b were tried first and refuse the phishing-generation prompt outright, even under an academic-research framing.


## Publication policy

- **Ship loader code + DOIs/URLs, not re-hosted corpora.** This repo's `src/dataset_v2.py` reconstructs the corpus from the original sources; we do not redistribute third-party email data.
- Sources marked ⚠️ (`verify`) have unclear or inherited licenses — **confirm on the source page before any public release**, and cite the ORIGINAL corpus, not a merged mirror.
- Real phishing may contain live-looking malicious URLs; the pipeline extracts text only and never renders HTML or fetches links.
- Personal data: benign corpora (Enron/SpamAssassin) contain real names/addresses from public research corpora — used for research, not re-published beyond the original terms.
