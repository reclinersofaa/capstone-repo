# Dataset Provenance & Transparency

> Auto-generated from `data\processed\master_emails_v2.csv` on 2026-07-16 19:11. Do not edit by hand — regenerate with `python -m src.provenance`.

**Corpus:** 1595 emails — 797 benign / 798 phishing. 10 segregated sources.

Every email is tagged with its `source` in `master_emails_v2.csv`; sources are never blended, so cue behaviour and click rates can always be sliced per origin.


## Sources currently in the dataset

| source | class | kind | n | origin | license | retrieved |
|---|---|---|---:|---|---|---|
| `spamassassin_ham` | benign | benign | 447 | Apache SpamAssassin public corpus | Apache SpamAssassin public corpus (free for research) ✅ | 2026-07-16 |
| `enron_clean` | benign | benign | 200 | CMU/FERC Enron corpus, parsed | Enron corpus is public (CMU/FERC); HF card omits explicit license — cite, do not re-host ⚠️ | 2026-07-16 |
| `multi_llm` | phishing | synthetic_llm | 150 | Gutierrez, Villegas-Ch & Govea (2026), Universidad de las Américas, Quito — accompanies Frontiers in Big Data 10.3389/fdata.2026.1883452 | CC BY 4.0 (data) / MIT (code) — record states: intended exclusively for defensive security research and academic study ✅ | 2026-07-16 |
| `trec07_ham` | benign | benign | 150 | TREC 2007 Spam Track (Cormack & Lynam, Univ. of Waterloo), via the curated Zenodo release | CC BY 4.0 asserted on the Zenodo record by Champa et al. (NOT by Cormack/Waterloo) — cite the original TREC track ⚠️ | 2026-07-16 |
| `ceas08` | phishing | real_phishing | 130 | CEAS 2008 conference corpus | Merged Kaggle listing unclear — cite original CEAS-08 source ⚠️ | 2026-07-16 |
| `hybrid_vtriad` | phishing | synthetic_llm | 120 | Self-generated with V-Triad persuasion framework + Groq additions | Own work — CC-BY or project license ✅ | 2026-07-16 |
| `plain_llm` | phishing | synthetic_llm | 110 | Self-generated (GPT / Claude / Gemini, unguided) + Groq additions | Own work — CC-BY or project license ✅ | 2026-07-16 |
| `nazario` | phishing | real_phishing | 110 | J. Nazario in-the-wild phishing collection | Academic-use collection — cite original, verify redistribution ⚠️ | 2026-07-16 |
| `nigerian_fraud` | phishing | real_phishing | 90 | Advance-fee (419) fraud email collection | Public-domain-style academic corpus — verify ⚠️ | 2026-07-16 |
| `phishbowl` | phishing | real_phishing | 88 | Cornell University IT Security Phish Bowl archive | Cornell IT public phish archive — verify redistribution terms ⚠️ | 2026-07-16 |

### Per-source detail

**`spamassassin_ham` — SpamAssassin Public Corpus (easy_ham + hard_ham)** (447 emails)
- Origin: Apache SpamAssassin public corpus
- URL / access: https://spamassassin.apache.org/old/publiccorpus/  (mirror: `kaggle:beatoa/spamassassin-public-corpus`)
- License: Apache SpamAssassin public corpus (free for research)  *(verified)*
- Retrieved: 2026-07-16
- Cleaning applied: RFC822 parsed; From/Subject/plain-text body extracted; spam_2 excluded; __MACOSX filtered; body capped 4000 chars
- Cite as: The Apache SpamAssassin Project, Public Corpus.

**`enron_clean` — Enron emails (pre-cleaned)** (200 emails)
- Origin: CMU/FERC Enron corpus, parsed
- URL / access: https://huggingface.co/datasets/corbt/enron-emails
- License: Enron corpus is public (CMU/FERC); HF card omits explicit license — cite, do not re-host  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: HF corbt/enron-emails parquet (from/subject/body); body>=40 chars; whitespace-normalized; capped 6000; seeded sample; deduped on body hash
- Cite as: Klimt & Yang (2004), The Enron Corpus.

**`multi_llm` — Cross-model Multi-LLM Phishing Corpus (GPT-4.1 / DeepSeek-3.2 / Llama-3.3-70b)** (150 emails)
- Origin: Gutierrez, Villegas-Ch & Govea (2026), Universidad de las Américas, Quito — accompanies Frontiers in Big Data 10.3389/fdata.2026.1883452
- URL / access: https://doi.org/10.5281/zenodo.20250116
- License: CC BY 4.0 (data) / MIT (code) — record states: intended exclusively for defensive security research and academic study  *(verified)*
- Retrieved: 2026-07-16
- Cleaning applied: VERIFIED raw bodies: llm_corpus_sampled.csv (4,986 rows) ships real subject+body, separate from corpus_features.csv. LLM half ONLY — the 5,000 human rows duplicate CEAS-08/Nazario/419/Enron already present. Sampled evenly across the 3 generating models; whitespace-normalized; body capped 6000; deduped on body hash.
- ⚠️ Caveat: Ships NO sender field, so the `suspicious_sender` cue can never fire for these emails — their cue count is not perfectly comparable with sources that carry senders.
- Cite as: Gutierrez, Villegas-Ch & Govea (2026), Cross-model evaluation of phishing detectors against LLM-generated emails, Zenodo, doi:10.5281/zenodo.20250116 (CC BY 4.0).

**`trec07_ham` — TREC 2007 Public Corpus — benign half (named benchmark)** (150 emails)
- Origin: TREC 2007 Spam Track (Cormack & Lynam, Univ. of Waterloo), via the curated Zenodo release
- URL / access: https://doi.org/10.5281/zenodo.8339691  (mirror: `zenodo:8339691 (TREC_07.csv — 53,757 rows: 24,358 ham / 29,399 spam)`)
- License: CC BY 4.0 asserted on the Zenodo record by Champa et al. (NOT by Cormack/Waterloo) — cite the original TREC track  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: label==0 (ham) only; whitespace-normalized; body capped 6000; seeded sample; deduped on body hash. The TREC SPAM half is deliberately EXCLUDED — spam is not targeted phishing, and labelling it class 1 would corrupt the construct.
- Cite as: Cormack & Lynam (2007), TREC 2007 Spam Track Overview. Curated release: Champa, Rabbi & Zibran, Zenodo doi:10.5281/zenodo.8339691.

**`ceas08` — CEAS 2008 Live Spam Challenge (phishing subset)** (130 emails)
- Origin: CEAS 2008 conference corpus
- URL / access: https://www.kaggle.com/datasets/naserabdullahalam/phishing-email-dataset  (mirror: `kaggle:naserabdullahalam/phishing-email-dataset (CEAS_08.csv)`)
- License: Merged Kaggle listing unclear — cite original CEAS-08 source  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: CEAS_08.csv filtered to label==1; whitespace-normalized; body capped 6000; seeded sample; deduped on body hash
- Cite as: CEAS 2008 Live Spam Challenge Corpus.

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

**`nazario` — Nazario Phishing Corpus** (110 emails)
- Origin: J. Nazario in-the-wild phishing collection
- URL / access: https://monkey.org/~jose/phishing/  (mirror: `kaggle:naserabdullahalam/phishing-email-dataset (Nazario.csv)`)
- License: Academic-use collection — cite original, verify redistribution  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: Nazario.csv (label==1); dropped MAILER-DAEMON/folder-internal-data junk rows; whitespace-normalized; body capped 6000; seeded sample; deduped on body hash
- Cite as: J. Nazario, Phishing Corpus.

**`nigerian_fraud` — Nigerian / 419 Fraudulent Email Corpus** (90 emails)
- Origin: Advance-fee (419) fraud email collection
- URL / access: https://www.kaggle.com/datasets/rtatman/fraudulent-email-corpus  (mirror: `kaggle:naserabdullahalam/phishing-email-dataset (Nigerian_Fraud.csv)`)
- License: Public-domain-style academic corpus — verify  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: Nigerian_Fraud.csv (label==1); whitespace-normalized; body capped 6000; seeded sample; deduped on body hash
- Cite as: Fraudulent E-mail Corpus (Nigerian/419).

**`phishbowl` — Cornell University Phish Bowl (real phishing)** (88 emails)
- Origin: Cornell University IT Security Phish Bowl archive
- URL / access: https://it.cornell.edu/phish-bowl
- License: Cornell IT public phish archive — verify redistribution terms  *(verify)*
- Retrieved: 2026-07-16
- Cleaning applied: Stripped Cornell IT warning-notice <div> boilerplate; recovered spoofed sender from notice; HTML/entities stripped; dropped records <40 chars
- Cite as: Cornell University, IT@Cornell Phish Bowl.


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
- Note: REPLICATION: llama-4-scout-17b (Groq) independently produces the same source ranking — V-Triad lowest cues / highest clicks — so the headline result is not an artifact of one extractor. Scout's cues are retained in data/cue_cache_v2/groq-scout/ for comparison. Cache is scoped per model: cue counts from different extractors are NOT comparable and must never be mixed within one corpus. Rejected: llama-3.1-8b (over-flags benign, ~1.7 cues vs ~0.0); llama-3.3-70b (free daily cap 429s mid-corpus); gpt-oss-120b / zai-glm-4.7 (reasoning-only, return no content field).

**synthetic_generation** — `llama-3.3-70b-versatile (Groq)`
- Why: best writing quality; only ~24 calls needed, so the small daily cap is not binding
- Note: used ONLY for plain_llm / hybrid_vtriad generation. Fictional entities only.


## Publication policy

- **Ship loader code + DOIs/URLs, not re-hosted corpora.** This repo's `src/dataset_v2.py` reconstructs the corpus from the original sources; we do not redistribute third-party email data.
- Sources marked ⚠️ (`verify`) have unclear or inherited licenses — **confirm on the source page before any public release**, and cite the ORIGINAL corpus, not a merged mirror.
- Real phishing may contain live-looking malicious URLs; the pipeline extracts text only and never renders HTML or fetches links.
- Personal data: benign corpora (Enron/SpamAssassin) contain real names/addresses from public research corpora — used for research, not re-published beyond the original terms.
