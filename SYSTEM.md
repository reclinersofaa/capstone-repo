# SYSTEM.md — Technical Codebase Reference

The complete technical map of the codebase: every module, its inputs/outputs, data contracts, and how components connect. Read alongside `README.md` before changing anything.

The repo holds **two generations side by side**. v1 is the original, untouched and still runnable. v2 is the current work.

| | v1 | v2 |
|---|---|---|
| Model | `src/agent.py` | `src/agent_v2.py` |
| Corpus | `master_emails.csv` (250) | `master_emails_v2.csv` (1,595) |
| Cue cache | `data/cue_cache/` | `data/cue_cache_v2/` |
| Results | `simulation_results.csv` (37,500) | `simulation_results_v2.csv` (239,250) |
| Notebook | `05_agent_simulation.ipynb` | `06_agent_simulation_v2.ipynb` |
| Entry point | notebook | `run_demo.py` |

---

## Data flow — v2 (current)

```
data/raw/spamassassin_full/       (Apache corpus, ~2,800 ham)
data/raw/phishing_email_dataset/  (Kaggle: CEAS_08, Nazario, Nigerian_Fraud)
HF corbt/enron-emails             (fetched at runtime, cached)
data/raw/phishbowl.csv            (240 raw Cornell records)
data/raw/*_groq.csv               (self-generated synthetic phishing)
      │
      ▼  src/dataset_v2.py
  clean_phishbowl()          strips Cornell IT warning boilerplate, recovers spoofed sender
  parse_spamassassin_ham()   RFC822 → subject/sender/body
  load_kaggle_phishing()     label==1 filter, mbox-junk filter, seeded sample
  load_enron_clean()         HF parquet → from/subject/body
  build_target_corpus()      concat → quality filter → dedupe_bodies() → email_id → URLs
      → data/processed/master_emails_v2.csv   (1,595 rows, `source` kept segregated)
      │
      ▼  src/provenance.py
      → DATA_PROVENANCE.md + data/processed/sources_manifest.json
      → results/v2_dataset_composition.png
      │
      ▼  src/ollama_extractor.py (default, local) | src/groq_client.py (hosted)
         batched, cache-first, cache scoped per extraction model
      → data/cue_cache_v2/<model-slug>/cue_<md5>.json   (JSON array of cue names)
      │
      ▼  src/agent_v2.py
  build_correlated_agents()  Gaussian copula → coherent traits
  run_simulation_v2()        agent × hour × email → src/decision_loop.simulate_email()
      → data/simulation_results_v2.csv   (239,250 rows)
      │
      ▼  notebooks/06_agent_simulation_v2.ipynb   (17 sections + caveats)
```

`run_demo.py` runs the whole thing end to end.

---

## Data flow — v1 (original)

```
data/raw/*.csv → normalization.ipynb → data/processed/master_emails.csv (250)
  → src/ollama_extractor.py (or cue_extractor.py / regex_extractor.py) → data/cue_cache/
  → src/agent.py → src/decision_loop.py → src/simulation.py
  → data/simulation_results.csv (37,500) → notebooks/05_agent_simulation.ipynb
```

---

## Data contracts

### `master_emails_v2.csv` (and v1 `master_emails.csv` — same schema)

| Column | Type | Description |
|---|---|---|
| `email_id` | int | Sequential ID, 1..N |
| `subject` / `sender` / `body` | str | Email content (headers stripped) |
| `extracted_urls` | str (list repr) | URLs found in body |
| `source` | str | v2 (10): `spamassassin_ham`, `enron_clean`, `trec07_ham`, `ceas08`, `nazario`, `nigerian_fraud`, `phishbowl`, `plain_llm`, `hybrid_vtriad`, `multi_llm` |
| `actual_class` | int | 0 = benign, 1 = phishing |

**Sources are never blended** — `source` is the segregation key for every downstream slice.

### `data/cue_cache_v2/<model-slug>/cue_<md5>.json`

A JSON array of cue names, e.g. `["urgency","generic_greeting"]`. `[]` means *genuinely no cues*.

**Two properties of the key, each fixing a real bug:**

1. **Keyed by content hash, not `email_id`.** `email_id` is positional — adding one source
   renumbers the whole corpus, so every cached entry would silently map to a *different*
   email. The key is `md5(normalized(subject + body))`, so entries survive recomposition.
2. **Scoped per extraction model.** Keys contain no model, so a shared directory lets one
   model inherit another's cues. Cue count *is* the headline measure, so a corpus extracted
   by two models is confounded — a source's count would partly reflect which model saw it.
   `run_demo.py` derives the slug from `--extractor`/`--ollama-model`
   (`gemma4-12b/`, `groq-scout/`). **Never merge these directories.**

> **Contract:** a failure must **never** be cached as `[]` — indistinguishable from "no cues
> found", and it silently corrupts the corpus. Enforced in two places: `GroqExtractor._call()`
> raises on API error, and `OllamaExtractor._call_batch()` raises when the model reports
> `eval_count > 0` but returns an empty string (the reasoning-model trap — see below).
> Both rules exist because both failures actually happened here and were nearly missed.

### `simulation_results_v2.csv`

One row per (agent × hour × email). v1 columns plus: `base_suspicion_threshold`, `suspicion_threshold` (dynamic), `perceived_vulnerability`, `energy_depletion`, `f_dynamic`, `p_click`.

---

## Module reference — v2

### `src/agent_v2.py`

`AgentV2` dataclass + copula agent generation + the simulation runner. All quantities in `[0,1]`.

| Method | Returns | Notes |
|---|---|---|
| `compute_energy_depletion()` | [0,1] | **dynamic** — workload/time-pressure ramp across the day |
| `compute_f_base()` | [0,0.6] | sleep debt (duration + quality) |
| `compute_total_fatigue()` | [0,1] | **noisy-OR** of F_base and F_dynamic — no circadian term |
| `compute_job_performance()` | [0,1] | weighted geometric mean, exponents sum to 1 |
| `compute_flawed_perception_level()` | [0,1] | `Fatigue·(1−JP)·(1−λ_PV·PV)` |
| `get_cue_fpl(cue)` | [0.02,0.90] | `FPL·(1−CueStrength)` + URL age/edu penalty, exposure bonus |
| `compute_p_click()` | [0,1] | **reporting index only** — centred sigmoid, does not drive decisions |
| `advance_workday(hour)` | None | integrates F_dynamic from 8am → `hour`; sets dynamic threshold |

**Key design notes**
- `advance_workday` **recomputes F_dynamic from scratch** each call (integrates 8am→hour). This makes it order-independent and free of the double-count a stateful accumulator suffers. `F_dynamic == 0` exactly at 8am.
- `base_suspicion_threshold` is drawn **continuous** in [1.0, 5.5], not integer. The decision loop compares an integer counter with `>=`, so the *effective* morning threshold is `ceil(base)` (spanning 2–6 as in v1) — but the fractional part makes different agents cross their next integer at different hours, smearing discrete steps into a smooth aggregate curve.
- Module-level constants (`ED_W_*`, `FDYN_DT`, `JP_EXP_*`, `FPL_LAMBDA_PV`, `THRESHOLD_DRIFT_K`) are **modeling choices**, not paper values. Monkey-patch them for sensitivity sweeps (see notebook §15).

**Functions:** `build_correlation_matrix()`, `build_correlated_agents(n, seed)`, `run_simulation_v2(...)`.

### `src/dataset_v2.py`

Corpus assembly. Non-destructive — never touches `master_emails.csv`.

| Function | Purpose |
|---|---|
| `clean_phishbowl()` | strips the Cornell warning `<div>`, recovers spoofed sender, drops <40-char records |
| `parse_spamassassin_ham(n, seed)` | RFC822 parse of easy_ham + hard_ham (excludes `spam_2`, filters `__MACOSX`) |
| `load_kaggle_phishing(which, n, seed)` | `nazario` / `ceas08` / `nigerian_fraud`; filters `label==1` + mbox junk |
| `load_enron_clean(n, seed)` | HF `corbt/enron-emails` parquet. **Needs `huggingface_hub` + `pyarrow`** — without both it returns an empty frame and the corpus silently drops to 1,395. Warns loudly; install via `requirements.txt`. |
| `dedupe_bodies(df)` | drops cross-source duplicates on a normalized body hash |
| `build_target_corpus(...)` | assembles everything with per-source caps |

### `src/groq_client.py`

| Item | Notes |
|---|---|
| `DEFAULT_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` — extraction (replication path; default is now local `gemma4:12b`) |
| `GEN_MODEL` | `llama-3.3-70b-versatile` — generation only |
| `GroqExtractor.extract_batch(df, batch_size=10)` | cache-first + **batched** (10 emails/call) |
| `GroqExtractor._call_batch()` | per-email fallback if the batch response is malformed |
| `generate_phishing(style, n)` | `plain_llm` (obvious) / `hybrid_vtriad` (subtle) — fictional entities only |

**Model choice matters and is recorded in `DATA_PROVENANCE.md`:**
- `gemma4:12b` (Ollama, local) — **the default and the published path.** Reproducible, no
  rate limit, no key, ~0.55s/email, whole corpus in ~13 min. Requires `"think": False`.
- `llama-4-scout-17b` (Groq) — clean JSON, used for the **replication** run. Reproduces the
  same source ranking, which is why the headline is not an extractor artifact.
- `llama-3.3-70b-versatile` — equivalent quality, but its small free daily token cap 429s partway through a full corpus.
- `llama-3.1-8b-instant` — fast but **over-flags benign** (~1.7 cues/email vs ~0.0) and muddies the V-Triad signal.
- `openai/gpt-oss-*`, `qwen3`, `zai-glm-4.7` — reasoning-only: return no `content` field at all.

> **Two traps that cost this project real time — both fail *silently*, yielding zero cues
> that look exactly like "no cues found":**
> 1. **Reasoning models need `"think": False`.** Otherwise Ollama spends the entire
>    `num_predict` budget on hidden reasoning, strips it, and returns `""` — with
>    `eval_count=270, done_reason='length'`. gemma4:12b was wrongly written off for months
>    because of this.
> 2. **Never mix extractors in one corpus.** Cache keys are content hashes with no model in
>    them, so a shared cache dir lets one model inherit another's cues. Cue count *is* the
>    headline measure; mixing makes it partly a function of which model saw which source.
>    Cache is scoped per model: `data/cue_cache_v2/<model-slug>/`.

**Groq's binding limit is tokens-per-minute, not the daily cap.** Measured:
`x-ratelimit-limit-tokens: 30000` (per minute, ~12s reset) against 1000 requests/day. A 4K-token
batch every 50ms is ~4.8M tokens/min, so unpaced runs 429 within seconds — which reads as
"budget exhausted" and is not. `llm_providers` now paces to 85% of TPM and retries on 429
using the reset header instead of falling through.

The API client is created **lazily** inside `_call`/`_call_batch`, so a fully cached corpus needs no key, no network, and not even the `groq` package.

### `src/provenance.py`

`SOURCE_REGISTRY` (per-source origin/URL/licence/cleaning/citation) + `PIPELINE_MODELS` (which models processed the corpus). `generate_all()` regenerates `DATA_PROVENANCE.md`, `sources_manifest.json` and the composition chart **from the actual assembled data**, so the datasheet cannot drift. Licences are flagged `verified` ✅ or `verify` ⚠️.

---

## Module reference — v1

### `src/agent.py`
`Agent` dataclass. `compute_kss()` (Åkerstedt Three-Process Model, circadian peaks 16.8h), `compute_energy_depletion()` = `0.65·job_complexity − 0.20·intrinsic_motivation + 1.80` (Tian et al.; gender deliberately excluded), `compute_total_fatigue()` = `(KSS_norm + ED)/2 + f_dynamic` clamped [1,5], `compute_job_performance()` (Rehman + Basit&Hassan, minus `0.34·fatigue`), `compute_flawed_perception_level()` = `0.5·fatigue_norm·(1−jp_norm)` [0,0.5], `get_cue_fpl(cue)` (URL cues: age/edu penalty; account-threat cues: **−0.04** for desk workers with job_complexity>3).

### `src/decision_loop.py` — **shared by v1 and v2**
```python
simulate_email(agent, cues, rng) -> dict
```
Shuffle cues → iterate up to `max_cues_processed` → `rng.random() > agent.get_cue_fpl(cue)` means perceived → `suspicion_counter += 1` → stop early at `suspicion_threshold` → `"reported"`, else `"clicked"`. `i` starts at `-1` so empty cue lists give `cues_scanned=0` and always `"clicked"`.

Works with `AgentV2` unchanged because v2 mirrors the same public method names.

### `src/simulation.py` (v1), `src/cue_extractor.py` (Gemini, deprecated — free tier 20 req/day), `src/regex_extractor.py` (no-API fallback), `src/ollama_extractor.py` (local; now also **batched**).

> **Ollama note:** the code default is `llama3.1:8b`, but this machine currently has only `gemma4:*` pulled — and `gemma4:12b` does **not** follow the JSON contract (returns unparseable output → empty cues). Do not use it for extraction without verifying output first.

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | for extraction/generation | Groq API — get one free at console.groq.com |
| `KAGGLE_USERNAME` / `KAGGLE_KEY` | for corpus download | SpamAssassin + phishing dataset pulls |
| `GEMINI_KEY` | legacy | v1 `cue_extractor.py` only |

A fully cached run needs **none** of these.

---

## Known limitations & extension points

- **Coefficients are modeling choices**, tuned for `[0,1]` bounds and monotonicity — not paper values. Literature motivates structure and signs only.
- **Suspicion threshold still dominates between agents** (r ≈ 0.98). Fatigue is a *within-person* effect (+13.6% across the day); the partial correlation controlling for threshold is the honest measure (notebook §12).
- **Extraction model changes results** — see the model table above. Always record which model produced a cache.
- **Damage index is circular** — built from its own JP/Fatigue/PV inputs; it tracks actual clicks at only r ≈ +0.08. Report as an index, not validation. The `−5.584` PV coefficient still needs verifying against the primary Shin-Carley paper.
- **`multi_llm` (Zenodo)** remains `planned` in the registry — verify it ships raw email bodies before ingesting.

**To add a new data source:** write a loader in `dataset_v2.py` returning `subject/sender/body/source/actual_class` → add it to `build_target_corpus()` → add a `SOURCE_REGISTRY` entry in `provenance.py`. The datasheet and composition chart update themselves.

**To add a new cue:** add the name to `VALID_CUES` in `groq_client.py` (+ `ollama_extractor.py` / `regex_extractor.py`), add its definition to the prompts, give it a `CueStrength` in `agent_v2.py`, then clear `data/cue_cache_v2/`.

**To add an agent trait:** add the field to `AgentV2` → sample it in `random_agent()` **and** `build_correlated_agents()` (add to `_COPULA_TRAITS`/`_COPULA_RANGES`/`_COPULA_CORR` if it should co-vary) → use it in a formula → log it in `run_simulation_v2()`'s record dict.
